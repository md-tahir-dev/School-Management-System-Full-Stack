"""Settings-module business logic: academic years, classes, sections, subjects, class-subject mapping,
and the (minimal) per-class monthly fee."""

import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, invalid, not_found
from app.models import (
    AcademicYear,
    ClassSubject,
    FeeStructure,
    SchoolClass,
    Section,
    Student,
    Subject,
    Teacher,
    TeacherAssignment,
    User,
)
from app.schemas.academic import (
    AcademicYearIn,
    ClassIn,
    ClassOut,
    ClassSubjectIn,
    ClassSubjectOut,
    FeeStructureIn,
    FeeStructureOut,
    SectionIn,
    SectionOut,
    SubjectIn,
)
from app.schemas.common import Page, PageParams
from app.services.audit import log_action
from app.services.dbutil import flush_or_conflict as _flush_or_conflict
from app.services.settings import get_school_settings
from app.utils.money import money
from app.utils.pagination import like_pattern, paginate


# ------------------------------------------------------------ academic years
async def list_years(db: AsyncSession, params: PageParams) -> Page:
    from app.schemas.academic import AcademicYearOut

    stmt = select(AcademicYear).order_by(AcademicYear.start_date.desc())
    if params.q:
        stmt = stmt.where(AcademicYear.label.ilike(like_pattern(params.q)))
    return await paginate(db, stmt, params, AcademicYearOut)


async def create_year(db: AsyncSession, actor: User, body: AcademicYearIn, ip: str | None) -> AcademicYear:
    year = AcademicYear(label=body.label, start_date=body.start_date, end_date=body.end_date, is_current=False)
    db.add(year)
    await _flush_or_conflict(db, f"An academic year labelled {body.label} already exists.", field="label")
    log_action(actor, "create", "academic_year", year.id, {"label": body.label}, db=db, ip=ip)
    await db.commit()
    return year


async def update_year(
    db: AsyncSession, actor: User, year_id: uuid.UUID, body: AcademicYearIn, ip: str | None
) -> AcademicYear:
    year = await db.get(AcademicYear, year_id)
    if year is None:
        raise not_found("Academic year")
    diff = {
        k: {"old": str(getattr(year, k)), "new": str(v)} for k, v in body.model_dump().items() if getattr(year, k) != v
    }
    for k, v in body.model_dump().items():
        setattr(year, k, v)
    await _flush_or_conflict(db, f"An academic year labelled {body.label} already exists.", field="label")
    if diff:
        log_action(actor, "update", "academic_year", year.id, diff, db=db, ip=ip)
    await db.commit()
    return year


async def set_current_year(db: AsyncSession, actor: User, year_id: uuid.UUID, ip: str | None) -> AcademicYear:
    year = await db.get(AcademicYear, year_id)
    if year is None:
        raise not_found("Academic year")
    # unset the others first: a partial unique index allows only one current year at any moment
    await db.execute(
        update(AcademicYear)
        .where(AcademicYear.is_current.is_(True), AcademicYear.id != year.id)
        .values(is_current=False)
    )
    year.is_current = True
    (await get_school_settings(db)).current_academic_year_id = year.id
    log_action(actor, "set_current", "academic_year", year.id, {"label": year.label}, db=db, ip=ip)
    await db.commit()
    return year


# ------------------------------------------------------------------- classes
def _class_dict(row) -> dict:
    klass, sections, students = row
    return {
        "id": klass.id,
        "name": klass.name,
        "order": klass.sort_order,
        "section_count": sections,
        "student_count": students,
    }


def _class_stmt():
    sec = select(Section.class_id, func.count().label("n")).group_by(Section.class_id).subquery()
    stu = (
        select(Student.class_id, func.count().label("n"))
        .where(Student.is_deleted.is_(False))
        .group_by(Student.class_id)
        .subquery()
    )
    return (
        select(SchoolClass, func.coalesce(sec.c.n, 0), func.coalesce(stu.c.n, 0))
        .outerjoin(sec, sec.c.class_id == SchoolClass.id)
        .outerjoin(stu, stu.c.class_id == SchoolClass.id)
        .order_by(SchoolClass.sort_order, SchoolClass.name)
    )


async def list_classes(db: AsyncSession, params: PageParams) -> Page:
    stmt = _class_stmt()
    if params.q:
        stmt = stmt.where(SchoolClass.name.ilike(like_pattern(params.q)))
    return await paginate(db, stmt, params, ClassOut, row_mapper=_class_dict)


async def _class_out(db: AsyncSession, class_id: uuid.UUID) -> ClassOut:
    row = (await db.execute(_class_stmt().where(SchoolClass.id == class_id))).one_or_none()
    if row is None:
        raise not_found("Class")
    return ClassOut.model_validate(_class_dict(row))


async def create_class(db: AsyncSession, actor: User, body: ClassIn, ip: str | None) -> ClassOut:
    klass = SchoolClass(name=body.name, sort_order=body.order)
    db.add(klass)
    await _flush_or_conflict(db, f"A class named {body.name} already exists.", field="name")
    log_action(actor, "create", "class", klass.id, {"name": body.name}, db=db, ip=ip)
    await db.commit()
    return await _class_out(db, klass.id)


async def update_class(db: AsyncSession, actor: User, class_id: uuid.UUID, body: ClassIn, ip: str | None) -> ClassOut:
    klass = await db.get(SchoolClass, class_id)
    if klass is None:
        raise not_found("Class")
    diff = {}
    if klass.name != body.name:
        diff["name"] = {"old": klass.name, "new": body.name}
    if klass.sort_order != body.order:
        diff["order"] = {"old": str(klass.sort_order), "new": str(body.order)}
    klass.name, klass.sort_order = body.name, body.order
    await _flush_or_conflict(db, f"A class named {body.name} already exists.", field="name")
    if diff:
        log_action(actor, "update", "class", klass.id, diff, db=db, ip=ip)
    await db.commit()
    return await _class_out(db, klass.id)


async def delete_class(db: AsyncSession, actor: User, class_id: uuid.UUID, ip: str | None) -> None:
    klass = await db.get(SchoolClass, class_id)
    if klass is None:
        raise not_found("Class")
    # count every row, including soft-deleted students: they still reference the class
    students = await db.scalar(select(func.count()).select_from(Student).where(Student.class_id == class_id))
    if students:
        raise AppError(
            409,
            "CLASS_HAS_STUDENTS",
            f"{klass.name} has {students} student record{'s' if students != 1 else ''}. "
            "Move the students to another class first, or rename the class instead of deleting it.",
            details={"student_count": students},
        )
    name = klass.name
    try:
        await db.delete(klass)
        log_action(actor, "delete", "class", class_id, {"name": name}, db=db, ip=ip)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(
            409, "CLASS_IN_USE", f"{name} is still used by exams, tests or materials and can't be deleted."
        ) from exc


# ------------------------------------------------------------------ sections
async def _class_or_404(db: AsyncSession, class_id: uuid.UUID) -> SchoolClass:
    klass = await db.get(SchoolClass, class_id)
    if klass is None:
        raise not_found("Class")
    return klass


def _section_stmt():
    stu = (
        select(Student.section_id, func.count().label("n"))
        .where(Student.is_deleted.is_(False))
        .group_by(Student.section_id)
        .subquery()
    )
    return select(Section, func.coalesce(stu.c.n, 0)).outerjoin(stu, stu.c.section_id == Section.id)


def _section_dict(row) -> dict:
    section, students = row
    return {"id": section.id, "class_id": section.class_id, "name": section.name, "student_count": students}


async def list_sections(db: AsyncSession, class_id: uuid.UUID, params: PageParams) -> Page:
    await _class_or_404(db, class_id)
    stmt = _section_stmt().where(Section.class_id == class_id).order_by(Section.name)
    if params.q:
        stmt = stmt.where(Section.name.ilike(like_pattern(params.q)))
    return await paginate(db, stmt, params, SectionOut, row_mapper=_section_dict)


async def create_section(
    db: AsyncSession, actor: User, class_id: uuid.UUID, body: SectionIn, ip: str | None
) -> SectionOut:
    await _class_or_404(db, class_id)
    section = Section(class_id=class_id, name=body.name)
    db.add(section)
    await _flush_or_conflict(db, f"This class already has a section named {body.name}.", field="name")
    log_action(actor, "create", "section", section.id, {"name": body.name, "class_id": str(class_id)}, db=db, ip=ip)
    await db.commit()
    return SectionOut(id=section.id, class_id=class_id, name=section.name, student_count=0)


async def update_section(
    db: AsyncSession, actor: User, section_id: uuid.UUID, body: SectionIn, ip: str | None
) -> SectionOut:
    section = await db.get(Section, section_id)
    if section is None:
        raise not_found("Section")
    old = section.name
    section.name = body.name
    await _flush_or_conflict(db, f"This class already has a section named {body.name}.", field="name")
    if old != body.name:
        log_action(actor, "update", "section", section.id, {"name": {"old": old, "new": body.name}}, db=db, ip=ip)
    await db.commit()
    row = (await db.execute(_section_stmt().where(Section.id == section_id))).one()
    return SectionOut.model_validate(_section_dict(row))


async def delete_section(db: AsyncSession, actor: User, section_id: uuid.UUID, ip: str | None) -> None:
    section = await db.get(Section, section_id)
    if section is None:
        raise not_found("Section")
    students = await db.scalar(select(func.count()).select_from(Student).where(Student.section_id == section_id))
    if students:
        raise AppError(
            409,
            "SECTION_HAS_STUDENTS",
            f"Section {section.name} has {students} student record{'s' if students != 1 else ''}. "
            "Move them to another section first, or rename the section instead of deleting it.",
            details={"student_count": students},
        )
    try:
        await db.delete(section)
        log_action(actor, "delete", "section", section_id, {"name": section.name}, db=db, ip=ip)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "SECTION_IN_USE", f"Section {section.name} is still in use and can't be deleted.") from exc


# ------------------------------------------------------------------ subjects
async def list_subjects(db: AsyncSession, params: PageParams) -> Page:
    from app.schemas.academic import SubjectOut

    stmt = select(Subject).order_by(Subject.name)
    if params.q:
        stmt = stmt.where(Subject.name.ilike(like_pattern(params.q)))
    return await paginate(db, stmt, params, SubjectOut)


async def create_subject(db: AsyncSession, actor: User, body: SubjectIn, ip: str | None) -> Subject:
    subject = Subject(name=body.name)
    db.add(subject)
    await _flush_or_conflict(db, f"A subject named {body.name} already exists.", field="name")
    log_action(actor, "create", "subject", subject.id, {"name": body.name}, db=db, ip=ip)
    await db.commit()
    return subject


async def update_subject(
    db: AsyncSession, actor: User, subject_id: uuid.UUID, body: SubjectIn, ip: str | None
) -> Subject:
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise not_found("Subject")
    old = subject.name
    subject.name = body.name
    await _flush_or_conflict(db, f"A subject named {body.name} already exists.", field="name")
    if old != body.name:
        log_action(actor, "update", "subject", subject.id, {"name": {"old": old, "new": body.name}}, db=db, ip=ip)
    await db.commit()
    return subject


async def delete_subject(db: AsyncSession, actor: User, subject_id: uuid.UUID, ip: str | None) -> None:
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise not_found("Subject")
    classes = await db.scalar(
        select(func.count()).select_from(ClassSubject).where(ClassSubject.subject_id == subject_id)
    )
    if classes:
        raise AppError(
            409,
            "SUBJECT_IN_USE",
            f"{subject.name} is taught in {classes} class{'es' if classes != 1 else ''}. "
            "Remove it from those classes first (Settings > Class Subjects).",
            details={"class_count": classes},
        )
    try:
        await db.delete(subject)
        log_action(actor, "delete", "subject", subject_id, {"name": subject.name}, db=db, ip=ip)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "SUBJECT_IN_USE", f"{subject.name} is still referenced by other records.") from exc


# ------------------------------------------------------------ class subjects
async def get_class_subjects(db: AsyncSession, class_id: uuid.UUID) -> list[ClassSubjectOut]:
    await _class_or_404(db, class_id)
    rows = await db.execute(
        select(ClassSubject, Subject.name)
        .join(Subject, Subject.id == ClassSubject.subject_id)
        .where(ClassSubject.class_id == class_id)
        .order_by(Subject.name)
    )
    return [
        ClassSubjectOut(
            subject_id=cs.subject_id,
            subject_name=name,
            total_marks=money(cs.total_marks),
            passing_marks=money(cs.passing_marks),
        )
        for cs, name in rows.all()
    ]


async def replace_class_subjects(
    db: AsyncSession, actor: User, class_id: uuid.UUID, items: list[ClassSubjectIn], ip: str | None
) -> list[ClassSubjectOut]:
    klass = await _class_or_404(db, class_id)
    ids = [i.subject_id for i in items]
    if len(set(ids)) != len(ids):
        raise invalid("The same subject is listed twice.", {"items": "Duplicate subjects"})
    known = set((await db.scalars(select(Subject.id).where(Subject.id.in_(ids)))).all()) if ids else set()
    if missing := set(ids) - known:
        raise invalid("Unknown subject.", {"items": f"{len(missing)} subject(s) do not exist"})

    existing = {
        cs.subject_id: cs
        for cs in (await db.scalars(select(ClassSubject).where(ClassSubject.class_id == class_id))).all()
    }
    removed = set(existing) - set(ids)
    if removed:
        # a subject that a teacher is assigned to in this class can't silently disappear from the class
        taught = (
            (
                await db.execute(
                    select(Subject.name)
                    .join(TeacherAssignment, TeacherAssignment.subject_id == Subject.id)
                    .join(Teacher, Teacher.id == TeacherAssignment.teacher_id)
                    .where(
                        TeacherAssignment.class_id == class_id,
                        TeacherAssignment.subject_id.in_(removed),
                        Teacher.is_deleted.is_(False),
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        if taught:
            raise AppError(
                409,
                "SUBJECT_HAS_TEACHERS",
                f"{', '.join(sorted(taught))} can't be removed from {klass.name} while teachers are assigned to it.",
                details={"subjects": sorted(taught)},
            )
        await db.execute(
            delete(ClassSubject).where(ClassSubject.class_id == class_id, ClassSubject.subject_id.in_(removed))
        )

    for item in items:
        row = existing.get(item.subject_id)
        if row:
            row.total_marks, row.passing_marks = item.total_marks, item.passing_marks
        else:
            db.add(
                ClassSubject(
                    class_id=class_id,
                    subject_id=item.subject_id,
                    total_marks=item.total_marks,
                    passing_marks=item.passing_marks,
                )
            )
    log_action(actor, "update", "class_subjects", class_id, {"subjects": len(items), "class": klass.name}, db=db, ip=ip)
    await db.commit()
    return await get_class_subjects(db, class_id)


# ------------------------------------------------------------- fee structures
async def list_fee_structures(db: AsyncSession) -> list[FeeStructureOut]:
    rows = await db.execute(
        select(SchoolClass.id, SchoolClass.name, FeeStructure.monthly_fee)
        .outerjoin(FeeStructure, FeeStructure.class_id == SchoolClass.id)
        .order_by(SchoolClass.sort_order, SchoolClass.name)
    )
    return [
        FeeStructureOut(class_id=cid, class_name=name, monthly_fee=money(fee if fee is not None else 0))
        for cid, name, fee in rows.all()
    ]


async def replace_fee_structures(
    db: AsyncSession, actor: User, items: list[FeeStructureIn], ip: str | None
) -> list[FeeStructureOut]:
    ids = [i.class_id for i in items]
    if len(set(ids)) != len(ids):
        raise invalid("A class is listed twice.", {"items": "Duplicate classes"})
    known = set((await db.scalars(select(SchoolClass.id).where(SchoolClass.id.in_(ids)))).all()) if ids else set()
    if missing := set(ids) - known:
        raise invalid("Unknown class.", {"items": f"{len(missing)} class(es) do not exist"})
    existing = {
        f.class_id: f for f in (await db.scalars(select(FeeStructure).where(FeeStructure.class_id.in_(ids)))).all()
    }
    diff = {}
    for item in items:
        row = existing.get(item.class_id)
        if row is None:
            db.add(FeeStructure(class_id=item.class_id, monthly_fee=item.monthly_fee))
            diff[str(item.class_id)] = {"old": None, "new": str(item.monthly_fee)}
        elif row.monthly_fee != item.monthly_fee:
            diff[str(item.class_id)] = {"old": str(row.monthly_fee), "new": str(item.monthly_fee)}
            row.monthly_fee = item.monthly_fee
    if diff:
        log_action(actor, "update", "fee_structure", None, diff, db=db, ip=ip)
    await db.commit()
    return await list_fee_structures(db)
