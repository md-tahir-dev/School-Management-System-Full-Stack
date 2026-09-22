"""Fee ledger generation and recalculation (Decimal everywhere, never floats)."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AcademicYear, FeeLedger, FeeStructure, SchoolClass, Student
from app.models.enums import FeeStatus
from app.utils.money import discount_amount, money


def academic_year_months(start: date) -> list[date]:
    """First day of each of the 12 months, beginning with the month the academic year starts."""
    months = []
    y, m = start.year, start.month
    for _ in range(12):
        months.append(date(y, m, 1))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return months


def due_date_for(month: date, due_day: int) -> date:
    return date(month.year, month.month, due_day)  # due_day is limited to 1..28 by the settings validation


def ledger_amounts(base_fee: Decimal, discount_percent: Decimal, fine: Decimal = Decimal(0)) -> tuple[Decimal, Decimal]:
    """Returns (discount, total_payable)."""
    discount = discount_amount(base_fee, discount_percent)
    return discount, money(base_fee - discount + fine)


async def generate_fee_ledger(
    db: AsyncSession,
    student: Student,
    academic_year: AcademicYear,
    *,
    discount_percent: Decimal = Decimal(0),
    fee_due_day: int = 10,
) -> tuple[list[FeeLedger], list[str]]:
    """Creates the 12 monthly ledger rows for `student`. Returns (rows, warnings).
    Without a fee structure for the class the rows are created with 0 and a warning is returned."""
    warnings: list[str] = []
    monthly = await db.scalar(select(FeeStructure.monthly_fee).where(FeeStructure.class_id == student.class_id))
    if monthly is None:
        class_name = await db.scalar(select(SchoolClass.name).where(SchoolClass.id == student.class_id))
        warnings.append(
            f"No monthly fee is set for {class_name}. Fee rows were created with 0; "
            "set the fee under Settings > Fees & Rules."
        )
        monthly = Decimal(0)
    base = money(monthly)
    discount, total = ledger_amounts(base, discount_percent)

    rows = [
        FeeLedger(
            id=uuid.uuid4(),
            student_id=student.id,
            academic_year_id=academic_year.id,
            month=month,
            base_fee=base,
            discount=discount,
            fine=Decimal(0),
            total_payable=total,
            paid_amount=Decimal(0),
            due_date=due_date_for(month, fee_due_day),
            status=FeeStatus.UNPAID,
        )
        for month in academic_year_months(academic_year.start_date)
    ]
    db.add_all(rows)
    await db.flush()
    return rows, warnings


async def recalculate_unpaid_ledger(db: AsyncSession, student_id: uuid.UUID, discount_percent: Decimal) -> int:
    """Applies a new discount to UNPAID rows only. Paid and partially paid rows are historical
    records and are never rewritten. Returns the number of rows changed."""
    rows = (
        await db.scalars(
            select(FeeLedger).where(
                FeeLedger.student_id == student_id,
                FeeLedger.status == FeeStatus.UNPAID,
                FeeLedger.paid_amount == 0,
            )
        )
    ).all()
    for row in rows:
        row.discount, row.total_payable = ledger_amounts(row.base_fee, discount_percent, row.fine)
    await db.flush()
    return len(rows)
