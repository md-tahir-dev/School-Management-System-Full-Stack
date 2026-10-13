"""Fee collection: late fines, payments allocated to the oldest unpaid months, receipts, voids and reports.

Money is Decimal throughout. A payment and its ledger updates are one transaction with the ledger rows
locked (SELECT ... FOR UPDATE), so two cashiers can't allocate the same month twice. Payments are never
deleted: a mistake is voided with a reason, which reverses its allocations and keeps the receipt number."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import conflict, forbidden, invalid, not_found
from app.models import (
    FeeLedger,
    FeeStructure,
    Guardian,
    Payment,
    PaymentAllocation,
    Role,
    SchoolClass,
    Section,
    Student,
    StudentFeeSetting,
    StudentGuardian,
    User,
)
from app.models.enums import FeeStatus
from app.schemas.common import Page, PageParams
from app.schemas.fees import (
    AllocationOut,
    ClassCollection,
    DefaulterOut,
    FeeSummaryOut,
    PaymentIn,
    PaymentOut,
)
from app.services.attendance import _today
from app.services.audit import log_action
from app.services.counters import next_receipt_no
from app.services.fees import ledger_amounts
from app.services.notify import family_user_ids, notify
from app.services.scoping import get_student_in_scope, student_scope_clause
from app.services.settings import get_school_settings
from app.utils.money import money
from app.utils.pagination import like_pattern, paginate

ZERO = Decimal(0)


class _IdRow(BaseModel):
    id: uuid.UUID


def _restatus(row: FeeLedger) -> None:
    if row.paid_amount > 0 and row.paid_amount >= row.total_payable:
        row.status = FeeStatus.PAID
    elif row.paid_amount > 0:
        row.status = FeeStatus.PARTIAL
    else:
        row.status = FeeStatus.UNPAID


async def apply_due_fines(db: AsyncSession, today: date, student_id: uuid.UUID | None = None) -> int:
    """Adds the school's late fine once to every month still not paid after its due date. One atomic
    UPDATE guarded by `fine_applied_at IS NULL`, so it is idempotent and safe under concurrency; it runs
    lazily before reads and payments instead of on a schedule. Status is unchanged (an unpaid or partial
    month stays so). The caller commits."""
    fine = money((await get_school_settings(db)).late_fine_amount or 0)
    if fine <= 0:
        return 0
    stmt = (
        update(FeeLedger)
        .where(
            FeeLedger.due_date < today,
            FeeLedger.status != FeeStatus.PAID,
            FeeLedger.fine_applied_at.is_(None),
            FeeLedger.total_payable > 0,
        )
        .values(
            fine=FeeLedger.fine + fine,
            total_payable=FeeLedger.total_payable + fine,
            fine_applied_at=datetime.now(UTC),
        )
        .execution_options(synchronize_session=False)
    )
    if student_id is not None:
        stmt = stmt.where(FeeLedger.student_id == student_id)
    return (await db.execute(stmt)).rowcount


async def school_today(db: AsyncSession) -> date:
    return _today(await get_school_settings(db))


# --- payments ------------------------------------------------------------------------------------


async def _payment_out(db: AsyncSession, payment_id: uuid.UUID) -> PaymentOut:
    row = (
        await db.execute(
            select(Payment, Student.full_name, Student.roll_no, SchoolClass.name, User.full_name)
            .join(Student, Student.id == Payment.student_id)
            .join(SchoolClass, SchoolClass.id == Student.class_id)
            .outerjoin(User, User.id == Payment.received_by)
            .where(Payment.id == payment_id)
        )
    ).one()
    p, name, roll, class_name, cashier = row
    allocations = (
        await db.execute(
            select(FeeLedger.month, PaymentAllocation.amount)
            .join(FeeLedger, FeeLedger.id == PaymentAllocation.ledger_id)
            .where(PaymentAllocation.payment_id == p.id)
            .order_by(FeeLedger.month)
        )
    ).all()
    return PaymentOut(
        id=p.id,
        receipt_no=p.receipt_no,
        student_id=p.student_id,
        student_name=name,
        roll_no=roll,
        class_name=class_name,
        amount=p.amount,
        method=p.method,
        note=p.note,
        paid_at=p.paid_at,
        received_by_name=cashier,
        voided_at=p.voided_at,
        void_reason=p.void_reason,
        allocations=[AllocationOut(month=m, amount=a) for m, a in allocations],
    )


async def collect_payment(db: AsyncSession, actor: User, body: PaymentIn, ip: str | None) -> PaymentOut:
    student = await get_student_in_scope(db, actor, body.student_id)
    today = await school_today(db)
    await apply_due_fines(db, today, student.id)
    rows = (
        await db.scalars(
            select(FeeLedger)
            .where(FeeLedger.student_id == student.id, FeeLedger.status != FeeStatus.PAID)
            .order_by(FeeLedger.month)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    due = money(sum((r.total_payable - r.paid_amount for r in rows), ZERO))
    amount = money(body.amount)
    if due <= 0:
        raise conflict("Nothing is due for this student.", code="nothing_due")
    if amount > due:
        raise invalid(f"Only {due} is due.", {"amount": f"At most {due}"})

    receipt_no = await next_receipt_no(db, today)
    payment = Payment(
        student_id=student.id,
        receipt_no=receipt_no,
        amount=amount,
        method=body.method,
        note=body.note,
        received_by=actor.id,
    )
    db.add(payment)
    await db.flush()
    left = amount
    for row in rows:  # oldest month first
        if left <= 0:
            break
        part = min(left, money(row.total_payable - row.paid_amount))
        if part <= 0:
            continue
        db.add(PaymentAllocation(payment_id=payment.id, ledger_id=row.id, amount=part))
        row.paid_amount = money(row.paid_amount + part)
        row.paid_date, row.receipt_no = today, receipt_no
        _restatus(row)
        left -= part
    log_action(
        actor,
        "create",
        "payment",
        payment.id,
        {"receipt_no": receipt_no, "student_id": str(student.id), "amount": str(amount), "method": body.method},
        db=db,
        ip=ip,
    )
    await notify(
        db,
        await family_user_ids(db, Student.id == student.id),
        f"Fee payment of {amount:,.2f} received for {student.full_name} (receipt {receipt_no}).",
        "fees",
    )
    await db.commit()
    return await _payment_out(db, payment.id)


async def void_payment(db: AsyncSession, actor: User, payment_id: uuid.UUID, reason: str, ip: str | None) -> PaymentOut:
    payment = await db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment is None:
        raise not_found("Payment")
    if payment.voided_at is not None:
        raise conflict("This payment is already void.", code="already_void")
    allocations = (
        await db.execute(
            select(PaymentAllocation, FeeLedger)
            .join(FeeLedger, FeeLedger.id == PaymentAllocation.ledger_id)
            .where(PaymentAllocation.payment_id == payment.id)
            .order_by(FeeLedger.month)  # same lock order as collect_payment
            .with_for_update(of=FeeLedger)
        )
    ).all()
    for alloc, row in allocations:
        row.paid_amount = money(row.paid_amount - alloc.amount)
        if row.paid_amount <= 0:
            row.paid_amount, row.paid_date = ZERO, None
        if row.receipt_no == payment.receipt_no:
            row.receipt_no = None
        _restatus(row)
    payment.voided_at, payment.voided_by, payment.void_reason = datetime.now(UTC), actor.id, reason
    log_action(actor, "void", "payment", payment.id, {"receipt_no": payment.receipt_no, "reason": reason}, db=db, ip=ip)
    await db.commit()
    return await _payment_out(db, payment.id)


def _no_teachers(user: User) -> None:
    if user.role == Role.TEACHER:
        raise forbidden()  # fee records are for the office and the family


async def get_payment(db: AsyncSession, user: User, payment_id: uuid.UUID) -> PaymentOut:
    _no_teachers(user)
    exists_in_scope = await db.scalar(
        select(Payment.id)
        .join(Student, Student.id == Payment.student_id)
        .where(Payment.id == payment_id, await student_scope_clause(db, user))
    )
    if exists_in_scope is None:
        raise not_found("Payment")
    return await _payment_out(db, payment_id)


async def list_payments(
    db: AsyncSession,
    user: User,
    params: PageParams,
    *,
    student_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> Page:
    _no_teachers(user)
    stmt = (
        select(Payment.id)
        .join(Student, Student.id == Payment.student_id)
        .where(await student_scope_clause(db, user))
        .order_by(Payment.paid_at.desc())
    )
    if student_id:
        stmt = stmt.where(Payment.student_id == student_id)
    if params.q:
        stmt = stmt.where(Payment.receipt_no.ilike(like_pattern(params.q)))
    if date_from:
        stmt = stmt.where(func.date(Payment.paid_at) >= date_from)
    if date_to:
        stmt = stmt.where(func.date(Payment.paid_at) <= date_to)
    page = await paginate(db, stmt, params, _IdRow, row_mapper=lambda r: {"id": r[0]})
    page.items = [await _payment_out(db, row.id) for row in page.items]  # ponytail: N+1, page_size is small
    return page


# --- reports -------------------------------------------------------------------------------------


async def defaulters(db: AsyncSession, params: PageParams, *, class_id: uuid.UUID | None) -> Page:
    today = await school_today(db)
    await apply_due_fines(db, today)
    await db.commit()
    owed = FeeLedger.total_payable - FeeLedger.paid_amount
    phone = (
        select(func.min(Guardian.father_phone))
        .join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
        .where(StudentGuardian.student_id == Student.id)
        .scalar_subquery()
    )
    stmt = (
        select(
            Student.id,
            Student.full_name,
            Student.roll_no,
            SchoolClass.name,
            Section.name,
            phone,
            func.count(FeeLedger.id),
            func.sum(owed),
            func.min(FeeLedger.due_date),
        )
        .join(FeeLedger, FeeLedger.student_id == Student.id)
        .join(SchoolClass, SchoolClass.id == Student.class_id)
        .outerjoin(Section, Section.id == Student.section_id)
        .where(
            Student.is_deleted.is_(False),
            FeeLedger.due_date < today,
            FeeLedger.status != FeeStatus.PAID,
            owed > 0,
        )
        .group_by(Student.id, SchoolClass.name, SchoolClass.sort_order, Section.name)
        .order_by(func.sum(owed).desc(), Student.roll_no)
    )
    if class_id:
        stmt = stmt.where(Student.class_id == class_id)
    if params.q:
        stmt = stmt.where(Student.full_name.ilike(like_pattern(params.q)))

    def _row(r) -> dict:
        sid, name, roll, cls, sec, ph, months, amount, oldest = r
        return {
            "student_id": sid,
            "full_name": name,
            "roll_no": roll,
            "class_name": cls,
            "section_name": sec,
            "father_phone": ph,
            "months_due": months,
            "amount_due": money(amount),
            "oldest_due_date": oldest,
        }

    return await paginate(db, stmt, params, DefaulterOut, row_mapper=_row)


async def fee_summary(db: AsyncSession, month: date) -> FeeSummaryOut:
    month = month.replace(day=1)
    today = await school_today(db)
    await apply_due_fines(db, today)
    await db.commit()
    live = Student.is_deleted.is_(False)
    by_class = (
        await db.execute(
            select(SchoolClass.name, func.sum(FeeLedger.total_payable), func.sum(FeeLedger.paid_amount))
            .join(Student, Student.id == FeeLedger.student_id)
            .join(SchoolClass, SchoolClass.id == Student.class_id)
            .where(FeeLedger.month == month, live)
            .group_by(SchoolClass.name, SchoolClass.sort_order)
            .order_by(SchoolClass.sort_order, SchoolClass.name)
        )
    ).all()
    classes = [
        ClassCollection(
            class_name=n, billed=money(b or 0), collected=money(c or 0), outstanding=money((b or 0) - (c or 0))
        )
        for n, b, c in by_class
    ]
    next_month = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    received = await db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.voided_at.is_(None),
            Payment.paid_at >= datetime.combine(month, datetime.min.time(), tzinfo=UTC),
            Payment.paid_at < datetime.combine(next_month, datetime.min.time(), tzinfo=UTC),
        )
    )
    overdue = await db.scalar(
        select(func.coalesce(func.sum(FeeLedger.total_payable - FeeLedger.paid_amount), 0))
        .join(Student, Student.id == FeeLedger.student_id)
        .where(live, FeeLedger.due_date < today, FeeLedger.status != FeeStatus.PAID)
    )
    billed = sum((c.billed for c in classes), ZERO)
    collected = sum((c.collected for c in classes), ZERO)
    return FeeSummaryOut(
        month=month,
        billed=money(billed),
        collected=money(collected),
        outstanding=money(billed - collected),
        received_in_month=money(received),
        overdue_total=money(overdue),
        by_class=classes,
    )


async def reprice_unpaid_months(db: AsyncSession, student: Student) -> int:
    """After a class change: untouched months take the new class's fee (paid/partial months are history)."""
    fee = await db.scalar(select(FeeStructure.monthly_fee).where(FeeStructure.class_id == student.class_id))
    percent = await db.scalar(
        select(StudentFeeSetting.discount_percent).where(StudentFeeSetting.student_id == student.id)
    )
    rows = (
        await db.scalars(
            select(FeeLedger).where(
                FeeLedger.student_id == student.id, FeeLedger.status == FeeStatus.UNPAID, FeeLedger.paid_amount == 0
            )
        )
    ).all()
    for row in rows:
        row.base_fee = money(fee or 0)
        row.discount, row.total_payable = ledger_amounts(row.base_fee, percent or ZERO, row.fine)
    await db.flush()
    return len(rows)
