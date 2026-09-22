"""Teacher module: transactional registration, profile, assignments, salary structure, soft delete."""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from fastapi import UploadFile
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, forbidden, invalid, not_found
from app.core.security import ahash_password, generate_temp_password
from app.models import (
    ClassSubject,
    Role,
    SalaryStructure,
    SchoolClass,
    Section,
    Subject,
    Teacher,
    TeacherAssignment,
    User,
)
from app.models.enums import Designation, EmploymentType
from app.schemas.common import Page, PageParams
from app.schemas.fields import Credential
from app.schemas.teachers import (
    AssignmentIn,
    AssignmentOut,
    SalaryIn,
    SalaryOut,
    TeacherCreate,
    TeacherDetail,
    TeacherListItem,
    TeacherUpdate,
)
from app.services.audit import log_action
from app.services.counters import next_employee_id
from app.services.storage import StorageBackend
from app.utils.money import money
from app.utils.pagination import like_pattern, paginate


@dataclass
class TeacherRegistration:
    teacher: Teacher
    credential: Credential


def salary_out(s: SalaryStructure) -> SalaryOut:
    """Gross is always computed here, from the components; it is never stored or accepted from clients."""
    gross = money(s.basic + s.house + s.transport + s.medical)
    return SalaryOut(
        basic=money(s.basic), house=money(s.house), transport=money(s.transport), medical=money(s.medical), gross=gross
    )


# ---------------------------------------------------------------- validation
async def _validate_assignments(db: AsyncSession, items: list[AssignmentIn]) -> None:
    keys = [(i.class_id, i.section_id, i.subject_id) for i in items]
    if len(set(keys)) != len(keys):
        raise invalid("The same class, section and subject is listed twice.", {"assignments": "Duplicate assignment"})
    if not items:
        return
    pairs = {(i.class_id, i.subject_id) for i in items}
    have = set(
        (
            await db.execute(
                select(ClassSubject.class_id, ClassSubject.subject_id).where(
                    ClassSubject.class_id.in_({c for c, _ in pairs})
                )
            )
        ).all()
    )
    missing = pairs - {(c, s) for c, s in have}
    if missing:
        names = []
        for class_id, subject_id in sorted(missing, key=str):
            c = await db.scalar(select(SchoolClass.name).where(SchoolClass.id == class_id))
            s = await db.scalar(select(Subject.name).where(Subject.id == subject_id))
            names.append(f"{s or 'Unknown subject'} is not taught in {c or 'an unknown class'}")
        raise invalid("Some assignments aren't valid for the class.", {"assignments": "; ".join(names)})
    section_ids = {i.section_id for i in items if i.section_id}
    if section_ids:
        sections = {
            s.id: s.class_id for s in (await db.scalars(select(Section).where(Section.id.in_(section_ids)))).all()
        }
        for i in items:
            if i.section_id and sections.get(i.section_id) != i.class_id:
                raise invalid(
                    "A section doesn't belong to its class.", {"assignments": "Section does not belong to the class"}
                )


async def _cnic_taken(db: AsyncSession, cnic: str, *, exclude: uuid.UUID | None = None) -> bool:
    stmt = select(Teacher.id).where(Teacher.cnic == cnic)
    if exclude:
        stmt = stmt.where(Teacher.id != exclude)
    return await db.scalar(stmt) is not None


def _cnic_conflict() -> AppError:
    return AppError(
        409,
        "CNIC_ALREADY_REGISTERED",
        "A teacher with this CNIC is already registered.",
        fields={"cnic": "Already registered to another teacher"},
    )


# -------------------------------------------------------------- registration
async def register_teacher(
    db: AsyncSession,
    payload: TeacherCreate,
    actor: User | None,
    *,
    ip: str | None = None,
    login: tuple[str, str] | None = None,
) -> TeacherRegistration:
    """All-or-nothing: employee ID, user, teacher, salary structure and assignments in one transaction.
    `login` (username, password) is for the demo seed only."""
    try:
        result = await _register(db, payload, actor, ip, login)
        await db.commit()
        return result
    except BaseException:
        await db.rollback()
        raise


async def _register(
    db: AsyncSession, payload: TeacherCreate, actor: User | None, ip: str | None, login: tuple[str, str] | None
) -> TeacherRegistration:
    # 1. validate
    if await _cnic_taken(db, payload.cnic):
        raise _cnic_conflict()
    await _validate_assignments(db, payload.assignments)
    password = login[1] if login else generate_temp_password()
    password_hash = await ahash_password(password)

    # 2. employee id
    employee_id = await next_employee_id(db)

    # 3. user
    username = login[0] if login else employee_id.lower()
    user = User(
        username=username,
        password_hash=password_hash,
        role=Role.TEACHER,
        full_name=" ".join(payload.full_name.split()),
        must_change_password=login is None,
    )
    db.add(user)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        raise AppError(409, "USERNAME_TAKEN", f"The login name {username} is already taken.") from exc

    teacher = Teacher(
        user_id=user.id,
        employee_id=employee_id,
        full_name=user.full_name,
        father_name=payload.father_name,
        dob=payload.dob,
        gender=payload.gender,
        cnic=payload.cnic,
        phone=payload.phone,
        emergency_contact=payload.emergency_contact,
        blood_group=payload.blood_group,
        religion=payload.religion,
        designation=payload.designation.value,
        qualification=payload.qualification.value,
        joining_date=payload.joining_date,
        employment_type=payload.employment_type,
        address=payload.address,
        city=payload.city,
    )
    db.add(teacher)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        raise _cnic_conflict() from exc

    # 4. salary structure  5. assignments
    db.add(SalaryStructure(teacher_id=teacher.id, **payload.salary.model_dump()))
    for a in payload.assignments:
        db.add(
            TeacherAssignment(
                teacher_id=teacher.id, class_id=a.class_id, section_id=a.section_id, subject_id=a.subject_id
            )
        )
    await db.flush()

    # 6. audit (salary figures are audited as the total only)
    gross = money(sum(payload.salary.model_dump().values(), Decimal(0)))
    log_action(
        actor,
        "create",
        "teacher",
        teacher.id,
        {"employee_id": employee_id, "assignments": len(payload.assignments), "gross_salary": str(gross)},
        db=db,
        ip=ip,
    )
    return TeacherRegistration(teacher, Credential(username=username, temp_password=password))


# ------------------------------------------------------------------- reading
async def current_teacher(db: AsyncSession, user: User) -> Teacher | None:
    return await db.scalar(select(Teacher).where(Teacher.user_id == user.id, Teacher.is_deleted.is_(False)))


async def get_teacher_in_scope(db: AsyncSession, user: User, teacher_id: uuid.UUID) -> Teacher:
    """Admin/CEO: any teacher. Teacher: only their own profile (anything else is 'not found')."""
    if user.role in (Role.ADMIN, Role.CEO):
        teacher = await db.scalar(select(Teacher).where(Teacher.id == teacher_id, Teacher.is_deleted.is_(False)))
    elif user.role == Role.TEACHER:
        teacher = await db.scalar(
            select(Teacher).where(Teacher.id == teacher_id, Teacher.user_id == user.id, Teacher.is_deleted.is_(False))
        )
    else:
        raise forbidden()
    if teacher is None:
        raise not_found("Teacher")
    return teacher


async def _assignment_rows(db: AsyncSession, teacher_ids: list[uuid.UUID]):
    return (
        await db.execute(
            select(TeacherAssignment, SchoolClass.name, Section.name, Subject.name)
            .join(SchoolClass, SchoolClass.id == TeacherAssignment.class_id)
            .outerjoin(Section, Section.id == TeacherAssignment.section_id)
            .join(Subject, Subject.id == TeacherAssignment.subject_id)
            .where(TeacherAssignment.teacher_id.in_(teacher_ids))
            .order_by(SchoolClass.sort_order, SchoolClass.name, Section.name, Subject.name)
        )
    ).all()


async def build_detail(db: AsyncSession, teacher: Teacher) -> TeacherDetail:
    rows = await _assignment_rows(db, [teacher.id])
    salary = await db.scalar(select(SalaryStructure).where(SalaryStructure.teacher_id == teacher.id))
    return TeacherDetail(
        id=teacher.id,
        employee_id=teacher.employee_id,
        full_name=teacher.full_name,
        father_name=teacher.father_name,
        dob=teacher.dob,
        gender=teacher.gender,
        cnic=teacher.cnic,
        phone=teacher.phone,
        emergency_contact=teacher.emergency_contact,
        photo_url=teacher.photo_url,
        blood_group=teacher.blood_group,
        religion=teacher.religion,
        designation=teacher.designation,
        qualification=teacher.qualification,
        joining_date=teacher.joining_date,
        employment_type=teacher.employment_type,
        address=teacher.address,
        city=teacher.city,
        assignments=[
            AssignmentOut(
                id=a.id,
                class_id=a.class_id,
                class_name=cn,
                section_id=a.section_id,
                section_name=sn,
                subject_id=a.subject_id,
                subject_name=subj,
            )
            for a, cn, sn, subj in rows
        ],
        salary_structure=salary_out(salary) if salary else None,
        created_at=teacher.created_at,
    )


async def list_teachers(
    db: AsyncSession,
    params: PageParams,
    *,
    subject_id: uuid.UUID | None = None,
    designation: Designation | None = None,
    employment_type: EmploymentType | None = None,
) -> Page:
    stmt = select(Teacher).where(Teacher.is_deleted.is_(False)).order_by(Teacher.full_name, Teacher.id)
    if params.q:
        pattern = like_pattern(params.q)
        stmt = stmt.where(
            or_(Teacher.full_name.ilike(pattern), Teacher.employee_id.ilike(pattern), Teacher.phone.ilike(pattern))
        )
    if subject_id:
        stmt = stmt.where(
            Teacher.id.in_(select(TeacherAssignment.teacher_id).where(TeacherAssignment.subject_id == subject_id))
        )
    if designation:
        stmt = stmt.where(Teacher.designation == designation.value)
    if employment_type:
        stmt = stmt.where(Teacher.employment_type == employment_type)

    def mapper(row) -> dict:
        t: Teacher = row[0]
        return {
            "id": t.id,
            "employee_id": t.employee_id,
            "full_name": t.full_name,
            "photo_url": t.photo_url,
            "designation": t.designation,
            "employment_type": t.employment_type,
            "phone": t.phone,
            "subjects": [],
            "classes": [],
        }

    page = await paginate(db, stmt, params, TeacherListItem, row_mapper=mapper)
    if page.items:
        subjects: dict[uuid.UUID, set[str]] = defaultdict(set)
        classes: dict[uuid.UUID, list[str]] = defaultdict(list)
        for a, class_name, section_name, subject_name in await _assignment_rows(db, [i.id for i in page.items]):
            subjects[a.teacher_id].add(subject_name)
            label = f"{class_name}-{section_name}" if section_name else class_name
            if label not in classes[a.teacher_id]:
                classes[a.teacher_id].append(label)
        for item in page.items:
            item.subjects = sorted(subjects[item.id])
            item.classes = classes[item.id]
    return page


# ------------------------------------------------------------------- editing
async def update_teacher(
    db: AsyncSession, actor: User, teacher_id: uuid.UUID, body: TeacherUpdate, *, ip: str | None = None
) -> Teacher:
    teacher = await get_teacher_in_scope(db, actor, teacher_id)
    changes = body.model_dump(exclude_unset=True, exclude={"employee_id"})
    for required in (
        "full_name",
        "gender",
        "cnic",
        "phone",
        "designation",
        "qualification",
        "joining_date",
        "employment_type",
    ):
        if required in changes and changes[required] is None:
            raise invalid(f"{required} can't be empty.", {required: "This field is required"})
    if "cnic" in changes and await _cnic_taken(db, changes["cnic"], exclude=teacher.id):
        raise _cnic_conflict()
    for enum_field in ("designation", "qualification"):
        if enum_field in changes:
            changes[enum_field] = changes[enum_field].value
    if "full_name" in changes:
        changes["full_name"] = " ".join(changes["full_name"].split())
    diff = {
        k: {
            "old": None if getattr(teacher, k) is None else str(getattr(teacher, k)),
            "new": None if v is None else str(v),
        }
        for k, v in changes.items()
        if getattr(teacher, k) != v
    }
    for k, v in changes.items():
        setattr(teacher, k, v)
    if "full_name" in changes and teacher.user_id:
        user = await db.get(User, teacher.user_id)
        if user:
            user.full_name = teacher.full_name
    if diff:
        log_action(actor, "update", "teacher", teacher.id, diff, db=db, ip=ip)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _cnic_conflict() from exc
    return teacher


async def replace_assignments(
    db: AsyncSession, actor: User, teacher_id: uuid.UUID, items: list[AssignmentIn], *, ip: str | None = None
) -> Teacher:
    teacher = await get_teacher_in_scope(db, actor, teacher_id)
    await _validate_assignments(db, items)
    await db.execute(delete(TeacherAssignment).where(TeacherAssignment.teacher_id == teacher.id))
    for a in items:
        db.add(
            TeacherAssignment(
                teacher_id=teacher.id, class_id=a.class_id, section_id=a.section_id, subject_id=a.subject_id
            )
        )
    log_action(actor, "assignments", "teacher", teacher.id, {"assignments": len(items)}, db=db, ip=ip)
    await db.commit()
    return teacher


async def set_salary_structure(
    db: AsyncSession, actor: User, teacher_id: uuid.UUID, body: SalaryIn, *, ip: str | None = None
) -> SalaryOut:
    teacher = await get_teacher_in_scope(db, actor, teacher_id)
    row = await db.scalar(select(SalaryStructure).where(SalaryStructure.teacher_id == teacher.id))
    old_gross = salary_out(row).gross if row else None
    if row is None:
        row = SalaryStructure(teacher_id=teacher.id, **body.model_dump())
        db.add(row)
    else:
        for k, v in body.model_dump().items():
            setattr(row, k, v)
    await db.flush()
    out = salary_out(row)
    log_action(
        actor,
        "salary_structure",
        "teacher",
        teacher.id,
        {"gross": {"old": None if old_gross is None else str(old_gross), "new": str(out.gross)}},
        db=db,
        ip=ip,
    )
    await db.commit()
    return out


async def set_photo(
    db: AsyncSession, actor: User, teacher_id: uuid.UUID, upload: UploadFile, storage: StorageBackend, *, ip=None
) -> Teacher:
    teacher = await get_teacher_in_scope(db, actor, teacher_id)
    url = await storage.save_image(upload, "photos")
    old = teacher.photo_url
    teacher.photo_url = url
    log_action(actor, "photo", "teacher", teacher.id, {"photo_url": {"old": old, "new": url}}, db=db, ip=ip)
    await db.commit()
    await storage.delete(old)
    return teacher


async def sole_assignments(db: AsyncSession, teacher: Teacher) -> list[str]:
    """Class-subjects where `teacher` is the only active teacher assigned."""
    mine = (
        await db.execute(
            select(TeacherAssignment.class_id, TeacherAssignment.subject_id, SchoolClass.name, Subject.name)
            .join(SchoolClass, SchoolClass.id == TeacherAssignment.class_id)
            .join(Subject, Subject.id == TeacherAssignment.subject_id)
            .where(TeacherAssignment.teacher_id == teacher.id)
        )
    ).all()
    sole: set[str] = set()
    for class_id, subject_id, class_name, subject_name in mine:
        others = await db.scalar(
            select(func.count())
            .select_from(TeacherAssignment)
            .join(Teacher, Teacher.id == TeacherAssignment.teacher_id)
            .where(
                TeacherAssignment.class_id == class_id,
                TeacherAssignment.subject_id == subject_id,
                TeacherAssignment.teacher_id != teacher.id,
                Teacher.is_deleted.is_(False),
            )
        )
        if not others:
            sole.add(f"{subject_name} ({class_name})")
    return sorted(sole)


async def soft_delete(
    db: AsyncSession, actor: User, teacher_id: uuid.UUID, *, force: bool = False, ip: str | None = None
) -> None:
    teacher = await get_teacher_in_scope(db, actor, teacher_id)
    sole = await sole_assignments(db, teacher)
    if sole and not force:
        raise AppError(
            409,
            "SOLE_TEACHER",
            f"{teacher.full_name} is the only teacher for: {', '.join(sole)}. "
            "Assign someone else first, or delete anyway with force=true.",
            details={"class_subjects": sole},
        )
    teacher.is_deleted = True
    if teacher.user_id:
        user = await db.get(User, teacher.user_id)
        if user:
            user.is_active = False
    log_action(
        actor,
        "delete",
        "teacher",
        teacher.id,
        {"employee_id": teacher.employee_id, "soft": True, "forced": bool(sole and force)},
        db=db,
        ip=ip,
    )
    await db.commit()
