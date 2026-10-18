"""Bell schedule, weekly class timetable and class teachers.

Assigning a lecture is how a teacher gets assigned to a class: saving a cell creates the matching
TeacherAssignment if none covers it, and taking a teacher off their last such lecture removes it, so
attendance/marks scoping follows the timetable. The database
enforces one lecture per slot per class/section and no double-booked teacher (`uq_timetable_*`)."""

import uuid

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import conflict, invalid, not_found
from app.core.permissions import SCHOOL_WIDE
from app.models import (
    ClassSubject,
    ClassTeacher,
    Period,
    Role,
    SchoolClass,
    Section,
    Student,
    Subject,
    Teacher,
    TeacherAssignment,
    TimetableEntry,
    User,
)
from app.schemas.timetable import CellIn, ClassTeacherIn, ClassTeacherOut, EntryOut, PeriodIn, PeriodOut, TimetableOut
from app.services.audit import log_action
from app.services.dbutil import flush_or_conflict
from app.services.scoping import get_student_in_scope, teacher_assigned_to_section, teacher_id_for

# --- periods -------------------------------------------------------------------------------------


async def list_periods(db: AsyncSession) -> list[Period]:
    return list(await db.scalars(select(Period).order_by(Period.sort_order, Period.start_time)))


async def create_period(db: AsyncSession, actor: User, body: PeriodIn, ip: str | None) -> Period:
    period = Period(**body.model_dump())
    db.add(period)
    await db.flush()
    log_action(actor, "create", "period", period.id, {"name": body.name}, db=db, ip=ip)
    await db.commit()
    return period


async def update_period(db: AsyncSession, actor: User, period_id: uuid.UUID, body: PeriodIn, ip: str | None) -> Period:
    period = await db.get(Period, period_id)
    if period is None:
        raise not_found("Period")
    for k, v in body.model_dump().items():
        setattr(period, k, v)
    if body.is_break and await db.scalar(select(exists().where(TimetableEntry.period_id == period_id))):
        raise conflict("Lectures are scheduled in this period; remove them before making it a break.")
    log_action(actor, "update", "period", period.id, {"name": body.name}, db=db, ip=ip)
    await db.commit()
    return period


async def delete_period(db: AsyncSession, actor: User, period_id: uuid.UUID, ip: str | None) -> None:
    period = await db.get(Period, period_id)
    if period is None:
        raise not_found("Period")
    await db.delete(period)  # cascades its lectures
    log_action(actor, "delete", "period", period_id, {"name": period.name}, db=db, ip=ip)
    await db.commit()


# --- timetable -----------------------------------------------------------------------------------


def _entries_stmt():
    return (
        select(TimetableEntry, SchoolClass.name, Section.name, Subject.name, Teacher.full_name)
        .join(SchoolClass, SchoolClass.id == TimetableEntry.class_id)
        .outerjoin(Section, Section.id == TimetableEntry.section_id)
        .join(Subject, Subject.id == TimetableEntry.subject_id)
        .join(Teacher, Teacher.id == TimetableEntry.teacher_id)
        .order_by(TimetableEntry.weekday)
    )


async def _timetable(db: AsyncSession, *conditions) -> TimetableOut:
    rows = await db.execute(_entries_stmt().where(*conditions))
    entries = [
        EntryOut(
            id=e.id,
            weekday=e.weekday,
            period_id=e.period_id,
            class_id=e.class_id,
            class_name=cn,
            section_id=e.section_id,
            section_name=sn,
            subject_id=e.subject_id,
            subject_name=subj,
            teacher_id=e.teacher_id,
            teacher_name=tn,
            room=e.room,
        )
        for e, cn, sn, subj, tn in rows.all()
    ]
    periods = [PeriodOut.model_validate(p) for p in await list_periods(db)]
    return TimetableOut(periods=periods, entries=entries)


def _section_clause(section_id: uuid.UUID | None):
    """Lectures for a section include whole-class lectures (section_id null)."""
    if section_id is None:
        return TimetableEntry.section_id.is_(None)
    return or_(TimetableEntry.section_id == section_id, TimetableEntry.section_id.is_(None))


async def class_timetable(
    db: AsyncSession, user: User, class_id: uuid.UUID, section_id: uuid.UUID | None
) -> TimetableOut:
    if user.role not in SCHOOL_WIDE:
        if user.role != Role.TEACHER:
            raise not_found("Timetable")  # students/parents use /timetable/me
        teacher_id = await teacher_id_for(db, user)
        if teacher_id is None or not await teacher_assigned_to_section(db, teacher_id, class_id, section_id):
            raise not_found("Timetable")
    return await _timetable(db, TimetableEntry.class_id == class_id, _section_clause(section_id))


async def my_timetable(db: AsyncSession, user: User, student_id: uuid.UUID | None) -> TimetableOut:
    if user.role == Role.TEACHER:
        teacher_id = await teacher_id_for(db, user)
        if teacher_id is None:
            raise not_found("Teacher profile")
        return await _timetable(db, TimetableEntry.teacher_id == teacher_id)
    if user.role == Role.STUDENT:
        student = await db.scalar(select(Student).where(Student.user_id == user.id, Student.is_deleted.is_(False)))
        if student is None:
            raise not_found("Student profile")
    elif user.role == Role.PARENT:
        if student_id is None:
            raise invalid("Choose a child.", {"student_id": "Required"})
        student = await get_student_in_scope(db, user, student_id)
    else:
        raise not_found("Timetable")  # school-wide roles pick a class instead
    return await _timetable(db, TimetableEntry.class_id == student.class_id, _section_clause(student.section_id))


async def _validate_cell(db: AsyncSession, body: CellIn) -> None:
    if await db.get(SchoolClass, body.class_id) is None:
        raise invalid("Unknown class.", {"class_id": "Unknown class"})
    if body.section_id is not None:
        section = await db.get(Section, body.section_id)
        if section is None or section.class_id != body.class_id:
            raise invalid("That section isn't in this class.", {"section_id": "Not in this class"})
    elif await db.scalar(select(exists().where(Section.class_id == body.class_id))):
        raise invalid("This class has sections; choose one.", {"section_id": "Required"})
    period = await db.get(Period, body.period_id)
    if period is None:
        raise invalid("Unknown period.", {"period_id": "Unknown period"})
    if period.is_break:
        raise invalid("Lectures can't be scheduled in a break.", {"period_id": "This period is a break"})
    taught = await db.scalar(
        select(exists().where(ClassSubject.class_id == body.class_id, ClassSubject.subject_id == body.subject_id))
    )
    if not taught:
        raise invalid("This subject isn't taught in this class.", {"subject_id": "Not a subject of this class"})
    teacher = await db.get(Teacher, body.teacher_id)
    if teacher is None or teacher.is_deleted:
        raise invalid("Unknown teacher.", {"teacher_id": "Unknown teacher"})


async def _ensure_assignment(db: AsyncSession, body: CellIn) -> None:
    covered = await db.scalar(
        select(
            exists().where(
                TeacherAssignment.teacher_id == body.teacher_id,
                TeacherAssignment.class_id == body.class_id,
                TeacherAssignment.subject_id == body.subject_id,
                or_(TeacherAssignment.section_id.is_(None), TeacherAssignment.section_id == body.section_id),
            )
        )
    )
    if not covered:
        db.add(
            TeacherAssignment(
                teacher_id=body.teacher_id,
                class_id=body.class_id,
                section_id=body.section_id,
                subject_id=body.subject_id,
            )
        )


async def _prune_assignment(
    db: AsyncSession, teacher_id: uuid.UUID, class_id: uuid.UUID, section_id: uuid.UUID | None, subject_id: uuid.UUID
) -> None:
    """A teacher taken off their last lecture of a subject in a class/section loses that teaching assignment
    (and with it marks/attendance access there). ponytail: also drops a matching hand-made assignment; add an
    `auto_created` flag if schools mix both ways of assigning."""
    still_teaches = await db.scalar(
        select(
            exists().where(
                TimetableEntry.teacher_id == teacher_id,
                TimetableEntry.class_id == class_id,
                TimetableEntry.subject_id == subject_id,
                TimetableEntry.section_id.is_(None) if section_id is None else TimetableEntry.section_id == section_id,
            )
        )
    )
    if not still_teaches:
        await db.execute(
            delete(TeacherAssignment).where(
                TeacherAssignment.teacher_id == teacher_id,
                TeacherAssignment.class_id == class_id,
                TeacherAssignment.subject_id == subject_id,
                TeacherAssignment.section_id.is_(None)
                if section_id is None
                else TeacherAssignment.section_id == section_id,
            )
        )


async def save_cell(db: AsyncSession, actor: User, body: CellIn, ip: str | None) -> EntryOut:
    await _validate_cell(db, body)
    slot = (
        TimetableEntry.class_id == body.class_id,
        TimetableEntry.weekday == body.weekday,
        TimetableEntry.period_id == body.period_id,
        TimetableEntry.section_id.is_(None)
        if body.section_id is None
        else TimetableEntry.section_id == body.section_id,
    )
    entry = await db.scalar(select(TimetableEntry).where(*slot))
    replaced = None
    if entry is None:
        entry = TimetableEntry(**body.model_dump())
        db.add(entry)
    else:
        replaced = (entry.teacher_id, entry.class_id, entry.section_id, entry.subject_id)
        entry.subject_id, entry.teacher_id, entry.room = body.subject_id, body.teacher_id, body.room
    await _ensure_assignment(db, body)
    await flush_or_conflict(
        db, "This teacher already has a lecture in this period on that day.", code="teacher_busy", field="teacher_id"
    )
    if replaced is not None:
        await _prune_assignment(db, *replaced)
    log_action(actor, "save", "timetable_entry", entry.id, body.model_dump(mode="json"), db=db, ip=ip)
    await db.commit()
    rows = (await _timetable(db, TimetableEntry.id == entry.id)).entries
    return rows[0]


async def delete_cell(db: AsyncSession, actor: User, entry_id: uuid.UUID, ip: str | None) -> None:
    entry = await db.get(TimetableEntry, entry_id)
    if entry is None:
        raise not_found("Lecture")
    await db.delete(entry)
    await db.flush()
    await _prune_assignment(db, entry.teacher_id, entry.class_id, entry.section_id, entry.subject_id)
    log_action(actor, "delete", "timetable_entry", entry_id, None, db=db, ip=ip)
    await db.commit()


# --- class teachers ------------------------------------------------------------------------------


async def list_class_teachers(db: AsyncSession) -> list[ClassTeacherOut]:
    rows = await db.execute(
        select(ClassTeacher, SchoolClass.name, Section.name, Teacher.full_name)
        .join(SchoolClass, SchoolClass.id == ClassTeacher.class_id)
        .outerjoin(Section, Section.id == ClassTeacher.section_id)
        .join(Teacher, Teacher.id == ClassTeacher.teacher_id)
        .order_by(SchoolClass.sort_order, SchoolClass.name, Section.name)
    )
    return [
        ClassTeacherOut(
            class_id=ct.class_id,
            class_name=cn,
            section_id=ct.section_id,
            section_name=sn,
            teacher_id=ct.teacher_id,
            teacher_name=tn,
        )
        for ct, cn, sn, tn in rows.all()
    ]


async def set_class_teacher(db: AsyncSession, actor: User, body: ClassTeacherIn, ip: str | None) -> None:
    if body.section_id is not None:
        section = await db.get(Section, body.section_id)
        if section is None or section.class_id != body.class_id:
            raise invalid("That section isn't in this class.", {"section_id": "Not in this class"})
    elif await db.get(SchoolClass, body.class_id) is None:
        raise invalid("Unknown class.", {"class_id": "Unknown class"})
    if body.teacher_id is not None:
        teacher = await db.get(Teacher, body.teacher_id)
        if teacher is None or teacher.is_deleted:
            raise invalid("Unknown teacher.", {"teacher_id": "Unknown teacher"})
    current = await db.scalar(
        select(ClassTeacher).where(
            ClassTeacher.class_id == body.class_id,
            ClassTeacher.section_id.is_(None)
            if body.section_id is None
            else ClassTeacher.section_id == body.section_id,
        )
    )
    if body.teacher_id is None:
        if current is not None:
            await db.delete(current)
    elif current is None:
        db.add(ClassTeacher(class_id=body.class_id, section_id=body.section_id, teacher_id=body.teacher_id))
    else:
        current.teacher_id = body.teacher_id
    log_action(
        actor, "set", "class_teacher", body.section_id or body.class_id, body.model_dump(mode="json"), db=db, ip=ip
    )
    await db.commit()
