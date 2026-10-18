"""Student module: transactional registration, listing, profile, edit, status, discount, soft delete."""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from fastapi import UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, invalid, not_found
from app.core.security import ahash_password, generate_temp_password
from app.models import (
    AcademicYear,
    FeeLedger,
    Guardian,
    Role,
    SchoolClass,
    Section,
    Student,
    StudentFeeSetting,
    StudentGuardian,
    User,
)
from app.models.enums import StudentStatus
from app.schemas.common import Page, PageParams
from app.schemas.fields import Credential
from app.schemas.students import (
    GuardianOut,
    LedgerOut,
    LedgerRow,
    LedgerTotals,
    StatusUpdate,
    StudentCreate,
    StudentDetail,
    StudentListItem,
    StudentUpdate,
)
from app.services.audit import log_action
from app.services.counters import next_roll_no
from app.services.fees import generate_fee_ledger, recalculate_unpaid_ledger, sync_admission_months
from app.services.payments import apply_due_fines, reprice_unpaid_months, school_today
from app.services.scoping import get_student_in_scope, student_scope_clause
from app.services.settings import get_school_settings
from app.services.storage import StorageBackend
from app.services.users import revoke_sessions
from app.utils.money import money
from app.utils.pagination import like_pattern, paginate

_GUARDIAN_FIELDS = (
    "father_name",
    "father_cnic",
    "father_phone",
    "father_occupation",
    "mother_name",
    "mother_cnic",
    "mother_phone",
    "guardian_name",
    "guardian_phone",
    "guardian_relation",
)


@dataclass
class LoginOverrides:
    """(username, password) pairs that replace the random ones. Used only by the demo seed so the documented
    demo logins work; normal registration always generates random temporary passwords."""

    parent: tuple[str, str] | None = None
    student: tuple[str, str] | None = None


@dataclass
class RegistrationResult:
    student: Student
    guardian: Guardian
    parent_credential: Credential | None = None
    student_credential: Credential | None = None
    warnings: list[str] = field(default_factory=list)


def _squash(name: str) -> str:
    return " ".join(name.split())


# --------------------------------------------------------------- registration
async def register_student(
    db: AsyncSession,
    payload: StudentCreate,
    actor: User | None,
    *,
    ip: str | None = None,
    logins: LoginOverrides | None = None,
) -> RegistrationResult:
    """All-or-nothing: one transaction, committed once at the end. Any failure rolls back the roll number,
    guardian, users, student, and ledger rows together."""
    try:
        result = await _register(db, payload, actor, ip, logins or LoginOverrides())
        await db.commit()
        return result
    except BaseException:
        await db.rollback()
        raise


async def _register(
    db: AsyncSession, payload: StudentCreate, actor: User | None, ip: str | None, logins: LoginOverrides
) -> RegistrationResult:
    # 1. validate payload against the current data
    year = await db.scalar(select(AcademicYear).where(AcademicYear.is_current.is_(True)))
    if year is None:
        raise AppError(
            409,
            "NO_CURRENT_ACADEMIC_YEAR",
            "Set a current academic year (Settings > Academic Years) before registering students.",
        )
    school = await get_school_settings(db)
    klass = await db.get(SchoolClass, payload.class_id)
    if klass is None:
        raise invalid("Class not found.", {"class_id": "Class not found"})
    await _check_section(db, klass, payload.section_id)

    admission = payload.admission_date or date.today()
    name = _squash(payload.full_name)
    g = payload.guardian

    guardian = await db.scalar(select(Guardian).where(Guardian.father_cnic == g.father_cnic))
    if guardian is not None:
        dup = (
            await db.execute(
                select(Student.id, Student.roll_no)
                .join(StudentGuardian, StudentGuardian.student_id == Student.id)
                .where(
                    StudentGuardian.guardian_id == guardian.id,
                    func.lower(Student.full_name) == name.lower(),
                    Student.dob == payload.dob,
                    Student.is_deleted.is_(False),
                )
            )
        ).first()
        if dup:
            raise AppError(
                409,
                "DUPLICATE_STUDENT",
                f"This student is already registered with roll number {dup.roll_no}.",
                details={"roll_no": dup.roll_no, "student_id": str(dup.id)},
            )

    # Password hashing is slow; do it before taking the roll-number row lock so registrations don't queue on it.
    parent_login = await _prepare_parent_login(db, guardian, g.father_phone, logins)
    student_login = None
    if payload.create_student_login:
        student_login = await _prepare_login(logins.student, None)  # username is the roll number, set below

    # 2. roll number (row-locked counter)
    roll_no = await next_roll_no(db, admission.year)

    # 3. guardian: reuse (sibling) or create
    guardian_created = False
    if guardian is None:
        guardian = Guardian(**{f: getattr(g, f) for f in _GUARDIAN_FIELDS})
        try:
            async with db.begin_nested():  # a concurrent sibling registration may win the race; then we reuse theirs
                db.add(guardian)
                await db.flush()
            guardian_created = True
        except IntegrityError:
            guardian = await db.scalar(select(Guardian).where(Guardian.father_cnic == g.father_cnic))
            if guardian is None:
                raise

    # 4. parent user (only if the guardian has none)
    parent_credential = None
    if guardian.user_id is None:
        if parent_login is None:  # race path: the guardian existed without a user after all
            parent_login = await _prepare_parent_login(db, guardian, g.father_phone, logins)
        assert parent_login is not None
        username, password, password_hash, must_change = parent_login
        parent_user = User(
            username=username,
            password_hash=password_hash,
            role=Role.PARENT,
            full_name=guardian.father_name,
            must_change_password=must_change,
        )
        db.add(parent_user)
        try:
            async with db.begin_nested():
                await db.flush()
        except IntegrityError as exc:
            raise AppError(
                409,
                "PHONE_ALREADY_USED",
                "This phone number is already used as a login by another account.",
                fields={"guardian.father_phone": "Already used as a login by another account"},
            ) from exc
        guardian.user_id = parent_user.id
        parent_credential = Credential(username=username, temp_password=password)

    # student row + guardian link
    student = Student(
        roll_no=roll_no,
        full_name=name,
        dob=payload.dob,
        gender=payload.gender,
        religion=payload.religion,
        nationality=payload.nationality,
        blood_group=payload.blood_group,
        class_id=klass.id,
        section_id=payload.section_id,
        admission_date=admission,
        previous_school=payload.previous_school,
        address=payload.address,
        city=payload.city,
        emergency_name=payload.emergency_name,
        emergency_phone=payload.emergency_phone,
        status=StudentStatus.ACTIVE,
    )
    db.add(student)
    await db.flush()
    db.add(StudentGuardian(student_id=student.id, guardian_id=guardian.id))

    # 5. optional student login (username = roll number)
    student_credential = None
    if student_login is not None:
        _, password, password_hash, must_change = student_login
        student_user = User(
            username=(logins.student[0] if logins.student else roll_no.lower()),
            password_hash=password_hash,
            role=Role.STUDENT,
            full_name=name,
            must_change_password=must_change,
        )
        db.add(student_user)
        try:
            async with db.begin_nested():
                await db.flush()
        except IntegrityError as exc:
            raise AppError(409, "USERNAME_TAKEN", f"The login name {student_user.username} is already taken.") from exc
        student.user_id = student_user.id
        student_credential = Credential(username=student_user.username, temp_password=password)

    db.add(StudentFeeSetting(student_id=student.id, discount_percent=payload.discount_percent, transport_fee=0))

    # 6. fee ledger: one row per month from the admission month to the end of the academic year
    _, warnings = await generate_fee_ledger(
        db, student, year, discount_percent=payload.discount_percent, fee_due_day=school.fee_due_day
    )

    # 7. audit
    log_action(
        actor,
        "create",
        "student",
        student.id,
        {
            "roll_no": roll_no,
            "class": klass.name,
            "guardian_id": str(guardian.id),
            "guardian_created": guardian_created,
            "parent_account_created": parent_credential is not None,
            "student_account_created": student_credential is not None,
        },
        db=db,
        ip=ip,
    )
    return RegistrationResult(student, guardian, parent_credential, student_credential, warnings)


async def _prepare_login(override: tuple[str, str] | None, username: str | None):
    """Returns (username, password, hash, must_change_password)."""
    if override:
        return override[0], override[1], await ahash_password(override[1]), False
    password = generate_temp_password()
    return username, password, await ahash_password(password), True


async def _prepare_parent_login(db: AsyncSession, guardian: Guardian | None, phone: str, logins: LoginOverrides):
    if guardian is not None and guardian.user_id is not None:
        return None  # sibling case: reuse the existing parent account, no new password
    username = (
        logins.parent[0] if logins.parent else (guardian.father_phone if guardian and guardian.father_phone else phone)
    )
    if await db.scalar(select(User.id).where(User.username == username.lower())):
        raise AppError(
            409,
            "PHONE_ALREADY_USED",
            "This phone number is already used as a login by another account.",
            fields={"guardian.father_phone": "Already used as a login by another account"},
        )
    return await _prepare_login(logins.parent, username.lower())


async def _check_section(db: AsyncSession, klass: SchoolClass, section_id: uuid.UUID | None) -> None:
    if section_id is not None:
        section = await db.get(Section, section_id)
        if section is None or section.class_id != klass.id:
            raise invalid(
                "Section does not belong to this class.", {"section_id": "Section does not belong to this class"}
            )
        return
    has_sections = await db.scalar(select(func.count()).select_from(Section).where(Section.class_id == klass.id))
    if has_sections:
        raise invalid("Choose a section.", {"section_id": "Select a section"})


# ------------------------------------------------------------------- reading
_SORTS = {
    "name": lambda: (Student.full_name, Student.roll_no),
    "roll_no": lambda: (Student.roll_no,),
    "class": lambda: (SchoolClass.sort_order, SchoolClass.name, Section.name, Student.full_name),
}


def _list_item(row) -> dict:
    student, class_name, section_name, father_name, father_phone = row
    return {
        "id": student.id,
        "roll_no": student.roll_no,
        "full_name": student.full_name,
        "photo_url": student.photo_url,
        "class_id": student.class_id,
        "class_name": class_name,
        "section_id": student.section_id,
        "section_name": section_name,
        "father_name": father_name,
        "father_phone": father_phone,
        "status": student.status,
    }


async def list_students(
    db: AsyncSession,
    user: User,
    params: PageParams,
    *,
    class_id: uuid.UUID | None = None,
    section_id: uuid.UUID | None = None,
    status: StudentStatus | None = None,
    sort: str = "name",
) -> Page:
    stmt = (
        select(Student, SchoolClass.name, Section.name, Guardian.father_name, Guardian.father_phone)
        .join(SchoolClass, SchoolClass.id == Student.class_id)
        .outerjoin(Section, Section.id == Student.section_id)
        .outerjoin(StudentGuardian, StudentGuardian.student_id == Student.id)
        .outerjoin(Guardian, Guardian.id == StudentGuardian.guardian_id)
        .where(Student.is_deleted.is_(False), await student_scope_clause(db, user))
    )
    if params.q:
        pattern = like_pattern(params.q)
        stmt = stmt.where(
            or_(Student.full_name.ilike(pattern), Student.roll_no.ilike(pattern), Guardian.father_name.ilike(pattern))
        )
    if class_id:
        stmt = stmt.where(Student.class_id == class_id)
    if section_id:
        stmt = stmt.where(Student.section_id == section_id)
    if status:
        stmt = stmt.where(Student.status == status)
    stmt = stmt.order_by(*_SORTS[sort](), Student.id)
    return await paginate(db, stmt, params, StudentListItem, row_mapper=_list_item)


async def get_guardian(db: AsyncSession, student_id: uuid.UUID) -> Guardian | None:
    return await db.scalar(
        select(Guardian)
        .join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
        .where(StudentGuardian.student_id == student_id)
    )


async def build_detail(db: AsyncSession, student: Student) -> StudentDetail:
    klass = await db.get(SchoolClass, student.class_id)
    section = await db.get(Section, student.section_id) if student.section_id else None
    guardian = await get_guardian(db, student.id)
    discount = await db.scalar(
        select(StudentFeeSetting.discount_percent).where(StudentFeeSetting.student_id == student.id)
    )
    from app.services.attendance import attendance_percentage_for_student
    from app.services.exams import latest_grade_for_student

    return StudentDetail(
        id=student.id,
        roll_no=student.roll_no,
        full_name=student.full_name,
        dob=student.dob,
        gender=student.gender,
        religion=student.religion,
        nationality=student.nationality,
        blood_group=student.blood_group,
        photo_url=student.photo_url,
        class_id=student.class_id,
        class_name=klass.name if klass else "",
        section_id=student.section_id,
        section_name=section.name if section else None,
        admission_date=student.admission_date,
        previous_school=student.previous_school,
        address=student.address,
        city=student.city,
        emergency_name=student.emergency_name,
        emergency_phone=student.emergency_phone,
        status=student.status,
        status_reason=student.status_reason,
        discount_percent=money(discount if discount is not None else 0),
        has_login=student.user_id is not None,
        guardian=GuardianOut.model_validate(guardian) if guardian else None,
        created_at=student.created_at,
        attendance_percentage=await attendance_percentage_for_student(db, student),
        latest_result_grade=await latest_grade_for_student(db, student.id),
    )


async def get_detail(db: AsyncSession, user: User, student_id: uuid.UUID) -> StudentDetail:
    return await build_detail(db, await get_student_in_scope(db, user, student_id))


# ------------------------------------------------------------------- editing
def _diff(obj, changes: dict) -> dict:
    return {
        k: {"old": None if getattr(obj, k) is None else str(getattr(obj, k)), "new": None if v is None else str(v)}
        for k, v in changes.items()
        if getattr(obj, k) != v
    }


async def update_student(
    db: AsyncSession, actor: User, student_id: uuid.UUID, body: StudentUpdate, *, ip: str | None = None
) -> Student:
    student = await get_student_in_scope(db, actor, student_id)
    changes = body.model_dump(exclude_unset=True, exclude={"roll_no", "guardian"})
    if "full_name" in changes and changes["full_name"]:
        changes["full_name"] = _squash(changes["full_name"])
    for required in ("full_name", "dob", "class_id", "gender"):
        if required in changes and changes[required] is None:
            raise invalid(f"{required} can't be empty.", {required: "This field is required"})

    if "class_id" in changes or "section_id" in changes:
        class_id = changes.get("class_id", student.class_id)
        klass = await db.get(SchoolClass, class_id)
        if klass is None:
            raise invalid("Class not found.", {"class_id": "Class not found"})
        section_id = (
            changes["section_id"]
            if "section_id" in changes
            else (student.section_id if class_id == student.class_id else None)
        )
        await _check_section(db, klass, section_id)
        changes["section_id"] = section_id

    diff = _diff(student, changes)
    for k, v in changes.items():
        setattr(student, k, v)
    if "class_id" in diff:
        diff["repriced_months"] = await reprice_unpaid_months(db, student)
    if "admission_date" in diff:
        percent = await db.scalar(
            select(StudentFeeSetting.discount_percent).where(StudentFeeSetting.student_id == student.id)
        )
        school = await get_school_settings(db)
        removed, added = await sync_admission_months(
            db, student, discount_percent=percent or Decimal(0), fee_due_day=school.fee_due_day
        )
        diff["ledger_months"] = {"removed": removed, "added": added}

    if body.guardian is not None:
        g_changes = body.guardian.model_dump(exclude_unset=True)
        guardian = await get_guardian(db, student.id)
        if guardian is not None and g_changes:
            g_diff = {f"guardian.{k}": v for k, v in _diff(guardian, g_changes).items()}
            for k, v in g_changes.items():
                setattr(guardian, k, v)
            diff.update(g_diff)
    if diff:
        log_action(actor, "update", "student", student.id, diff, db=db, ip=ip)
    await db.commit()
    return student


async def _set_login(db: AsyncSession, user_id: uuid.UUID | None, active: bool) -> str | None:
    user = await db.get(User, user_id) if user_id else None
    if user is None or user.is_active == active:
        return None
    user.is_active = active
    if not active:
        await revoke_sessions(db, user.id)
    return user.username


async def _sync_logins(db: AsyncSession, student: Student, *, active: bool) -> dict:
    """Called when a student enters or leaves ACTIVE (or is deleted). Their own login follows; a parent login
    is disabled only once none of the parent's children is active, and re-enabled when one becomes active.
    Returns the usernames changed, for the audit entry."""
    changed = {"student": await _set_login(db, student.user_id, active), "parents": []}
    parent_ids = (
        await db.scalars(
            select(Guardian.user_id)
            .join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
            .where(StudentGuardian.student_id == student.id, Guardian.user_id.is_not(None))
        )
    ).all()
    for parent_id in parent_ids:
        if not active:
            # lock the parent so two siblings deactivated at once can't each still see the other as active
            await db.execute(select(User.id).where(User.id == parent_id).with_for_update())
            active_child = await db.scalar(
                select(Student.id)
                .join(StudentGuardian, StudentGuardian.student_id == Student.id)
                .join(Guardian, Guardian.id == StudentGuardian.guardian_id)
                .where(
                    Guardian.user_id == parent_id,
                    Student.status == StudentStatus.ACTIVE,
                    Student.is_deleted.is_(False),
                )
                .limit(1)
            )
            if active_child is not None:
                continue
        if username := await _set_login(db, parent_id, active):
            changed["parents"].append(username)
    return changed


async def set_status(
    db: AsyncSession, actor: User, student_id: uuid.UUID, body: StatusUpdate, *, ip: str | None = None
) -> Student:
    student = await get_student_in_scope(db, actor, student_id)
    old = student.status
    student.status = body.status
    student.status_reason = body.reason if body.status == StudentStatus.EXPELLED else (body.reason or None)
    diff: dict = {"status": {"old": old.value, "new": body.status.value}, "reason": body.reason}
    was_active, is_active = old == StudentStatus.ACTIVE, body.status == StudentStatus.ACTIVE
    if was_active != is_active:
        await db.flush()  # the parent check below counts siblings' statuses in SQL
        diff["logins"] = await _sync_logins(db, student, active=is_active)
    log_action(actor, "status", "student", student.id, diff, db=db, ip=ip)
    await db.commit()
    return student


async def set_discount(
    db: AsyncSession, actor: User, student_id: uuid.UUID, percent: Decimal, *, ip: str | None = None
) -> tuple[Decimal, int]:
    """Stores the discount and recalculates UNPAID ledger rows only."""
    student = await get_student_in_scope(db, actor, student_id)
    setting = await db.scalar(select(StudentFeeSetting).where(StudentFeeSetting.student_id == student.id))
    old = setting.discount_percent if setting else Decimal(0)
    if setting is None:
        db.add(StudentFeeSetting(student_id=student.id, discount_percent=percent, transport_fee=0))
    else:
        setting.discount_percent = percent
    changed = await recalculate_unpaid_ledger(db, student.id, percent)
    log_action(
        actor,
        "discount",
        "student",
        student.id,
        {"discount_percent": {"old": str(old), "new": str(percent)}, "rows_recalculated": changed},
        db=db,
        ip=ip,
    )
    await db.commit()
    return money(percent), changed


async def set_photo(
    db: AsyncSession, actor: User, student_id: uuid.UUID, upload: UploadFile, storage: StorageBackend, *, ip=None
) -> Student:
    student = await get_student_in_scope(db, actor, student_id)
    url = await storage.save_image(upload, "photos")
    old = student.photo_url
    student.photo_url = url
    log_action(actor, "photo", "student", student.id, {"photo_url": {"old": old, "new": url}}, db=db, ip=ip)
    await db.commit()
    await storage.delete(old)
    return student


async def soft_delete(db: AsyncSession, actor: User, student_id: uuid.UUID, *, ip: str | None = None) -> None:
    """is_deleted=true; status is left as it was; the student's own login (if any) is deactivated."""
    student = await get_student_in_scope(db, actor, student_id)
    student.is_deleted = True
    await db.flush()
    logins = await _sync_logins(db, student, active=False)
    diff = {"roll_no": student.roll_no, "soft": True, "logins": logins}
    log_action(actor, "delete", "student", student.id, diff, db=db, ip=ip)
    await db.commit()


async def get_ledger(db: AsyncSession, user: User, student_id: uuid.UUID) -> LedgerOut:
    student = await get_student_in_scope(db, user, student_id)
    if await apply_due_fines(db, await school_today(db), student.id):
        await db.commit()
    rows = (
        await db.scalars(select(FeeLedger).where(FeeLedger.student_id == student.id).order_by(FeeLedger.month))
    ).all()
    total = sum((r.total_payable for r in rows), Decimal(0))
    paid = sum((r.paid_amount for r in rows), Decimal(0))
    return LedgerOut(
        items=[LedgerRow.model_validate(r) for r in rows],
        totals=LedgerTotals(total_payable=money(total), paid_amount=money(paid), balance=money(total - paid)),
    )


async def find_by_guardian_cnic(db: AsyncSession, cnic: str) -> Guardian | None:
    """Used by the registration form to announce 'existing guardian found' before submitting."""
    return await db.scalar(select(Guardian).where(Guardian.father_cnic == cnic))


def not_found_student():
    return not_found("Student")
