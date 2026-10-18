"""Announcements, school events, the combined calendar, and the reader side of notifications.

An announcement targets an audience (all / teachers / students / parents) and optionally one class or
section. Managers post anywhere; a teacher posts only to a class/section they teach or are class teacher
of. Posting fans out one in-app notification per recipient."""

import uuid
from datetime import date

from sqlalchemy import ColumnElement, and_, exists, false, func, literal, null, or_, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden, invalid, not_found
from app.core.permissions import MANAGERS, SCHOOL_WIDE
from app.models import (
    Announcement,
    ClassTeacher,
    Event,
    Exam,
    Guardian,
    Notification,
    Role,
    SchoolClass,
    SchoolHoliday,
    Section,
    Student,
    StudentGuardian,
    Teacher,
    TeacherAssignment,
    User,
)
from app.models.enums import Audience
from app.schemas.common import Page, PageParams
from app.schemas.notices import AnnouncementIn, AnnouncementOut, CalendarItem, EventIn, EventOut, NotificationOut
from app.services.audit import log_action
from app.services.notify import family_user_ids, notify
from app.services.scoping import teacher_assigned_to_section, teacher_id_for
from app.utils.pagination import paginate

_ROLE_AUDIENCE = {Role.TEACHER: Audience.TEACHERS, Role.STUDENT: Audience.STUDENTS, Role.PARENT: Audience.PARENTS}


def _teacher_covers(teacher_id: uuid.UUID, class_col, section_col) -> ColumnElement[bool]:
    def one(table):
        return exists().where(
            table.teacher_id == teacher_id,
            table.class_id == class_col,
            or_(table.section_id.is_(None), section_col.is_(None), table.section_id == section_col),
        )

    return or_(one(TeacherAssignment), one(ClassTeacher))


def _student_matches(class_col, section_col) -> ColumnElement[bool]:
    return and_(Student.class_id == class_col, or_(section_col.is_(None), Student.section_id == section_col))


async def _children_clause(db: AsyncSession, user: User) -> ColumnElement[bool]:
    """Condition on Student: the reader themself (student) or their linked children (parent)."""
    if user.role == Role.STUDENT:
        return Student.user_id == user.id
    return Student.id.in_(
        select(StudentGuardian.student_id)
        .join(Guardian, Guardian.id == StudentGuardian.guardian_id)
        .where(Guardian.user_id == user.id)
    )


async def _announcement_clause(db: AsyncSession, user: User) -> ColumnElement[bool]:
    if user.role in SCHOOL_WIDE:
        return true()
    audience = Announcement.audience.in_([Audience.ALL, _ROLE_AUDIENCE[user.role]])
    if user.role == Role.TEACHER:
        teacher_id = await teacher_id_for(db, user)
        if teacher_id is None:
            return false()
        target = or_(
            Announcement.class_id.is_(None),
            _teacher_covers(teacher_id, Announcement.class_id, Announcement.section_id),
        )
        return or_(and_(audience, target), Announcement.created_by == user.id)
    mine = await _children_clause(db, user)
    target = or_(
        Announcement.class_id.is_(None),
        exists().where(
            mine, Student.is_deleted.is_(False), _student_matches(Announcement.class_id, Announcement.section_id)
        ),
    )
    return and_(audience, target)


def _ann_out(user: User, row) -> AnnouncementOut:
    a, class_name, section_name, author = row
    return AnnouncementOut(
        id=a.id,
        title=a.title,
        message=a.message,
        audience=a.audience,
        priority=a.priority,
        class_id=a.class_id,
        class_name=class_name,
        section_id=a.section_id,
        section_name=section_name,
        author_name=author,
        created_at=a.created_at,
        can_edit=user.role in MANAGERS or a.created_by == user.id,
    )


def _ann_stmt():
    return (
        select(Announcement, SchoolClass.name, Section.name, User.full_name)
        .outerjoin(SchoolClass, SchoolClass.id == Announcement.class_id)
        .outerjoin(Section, Section.id == Announcement.section_id)
        .outerjoin(User, User.id == Announcement.created_by)
    )


async def list_announcements(db: AsyncSession, user: User, params: PageParams) -> Page:
    stmt = _ann_stmt().where(await _announcement_clause(db, user)).order_by(Announcement.created_at.desc())
    return await paginate(db, stmt, params, AnnouncementOut, row_mapper=lambda r: _ann_out(user, r))


async def latest_announcements(db: AsyncSession, user: User, limit: int = 3) -> list[dict]:
    """Dashboard card: the newest announcements the user may see."""
    rows = await db.scalars(
        select(Announcement)
        .where(await _announcement_clause(db, user))
        .order_by(Announcement.created_at.desc())
        .limit(limit)
    )
    return [
        {"id": str(a.id), "title": a.title, "priority": a.priority, "created_at": a.created_at.isoformat()}
        for a in rows
    ]


async def _recipients(db: AsyncSession, a: Announcement) -> set[uuid.UUID]:
    want = {a.audience} if a.audience != Audience.ALL else {Audience.TEACHERS, Audience.STUDENTS, Audience.PARENTS}
    ids: set[uuid.UUID] = set()
    if Audience.TEACHERS in want:
        stmt = select(Teacher.user_id).where(Teacher.is_deleted.is_(False), Teacher.user_id.is_not(None))
        if a.class_id is not None:
            stmt = stmt.where(_teacher_covers(Teacher.id, _literal(a.class_id), _literal(a.section_id)))
        ids |= set(await db.scalars(stmt))
    if want & {Audience.STUDENTS, Audience.PARENTS}:
        where = true() if a.class_id is None else _student_matches(_literal(a.class_id), _literal(a.section_id))
        ids |= await family_user_ids(db, where, students=Audience.STUDENTS in want, parents=Audience.PARENTS in want)
    return ids


def _literal(value):
    """A bound value usable where `_teacher_covers` / `_student_matches` expect a column."""
    return null() if value is None else literal(value)


async def create_announcement(db: AsyncSession, actor: User, body: AnnouncementIn, ip: str | None) -> AnnouncementOut:
    if body.section_id is not None:
        section = await db.get(Section, body.section_id)
        if section is None or section.class_id != body.class_id:
            raise invalid("That section isn't in this class.", {"section_id": "Not in this class"})
    elif body.class_id is not None and await db.get(SchoolClass, body.class_id) is None:
        raise invalid("Unknown class.", {"class_id": "Unknown class"})
    if actor.role == Role.TEACHER:
        if body.class_id is None:
            raise invalid("Teachers announce to one of their classes.", {"class_id": "Required"})
        if body.audience == Audience.TEACHERS:
            raise invalid("Teachers announce to students and parents.", {"audience": "Not allowed"})
        teacher_id = await teacher_id_for(db, actor)
        if teacher_id is None or not await teacher_assigned_to_section(db, teacher_id, body.class_id, body.section_id):
            raise not_found("Class section")
    elif actor.role not in MANAGERS:
        raise forbidden()
    a = Announcement(**body.model_dump(), created_by=actor.id)
    db.add(a)
    await db.flush()
    sent = await notify(db, await _recipients(db, a), f"Announcement: {a.title}", "announcements")
    log_action(actor, "create", "announcement", a.id, {"title": a.title, "recipients": sent}, db=db, ip=ip)
    await db.commit()
    row = (await db.execute(_ann_stmt().where(Announcement.id == a.id))).one()
    return _ann_out(actor, row)


async def delete_announcement(db: AsyncSession, actor: User, announcement_id: uuid.UUID, ip: str | None) -> None:
    a = await db.scalar(
        select(Announcement).where(Announcement.id == announcement_id, await _announcement_clause(db, actor))
    )
    if a is None:
        raise not_found("Announcement")
    if actor.role not in MANAGERS and a.created_by != actor.id:
        raise forbidden("Only the author or a manager can remove this announcement.")
    await db.delete(a)
    log_action(actor, "delete", "announcement", announcement_id, {"title": a.title}, db=db, ip=ip)
    await db.commit()


# --- events and calendar -------------------------------------------------------------------------


def _event_clause(user: User) -> ColumnElement[bool]:
    if user.role in SCHOOL_WIDE:
        return true()
    return Event.audience.in_([Audience.ALL, _ROLE_AUDIENCE[user.role]])


async def list_events(db: AsyncSession, user: User, date_from: date, date_to: date) -> list[EventOut]:
    rows = await db.scalars(
        select(Event)
        .where(_event_clause(user), Event.start_date <= date_to, Event.end_date >= date_from)
        .order_by(Event.start_date, Event.title)
    )
    return [EventOut.model_validate(e, from_attributes=True) for e in rows]


async def create_event(db: AsyncSession, actor: User, body: EventIn, ip: str | None) -> EventOut:
    event = Event(**body.model_dump(), created_by=actor.id)
    db.add(event)
    await db.flush()
    log_action(actor, "create", "event", event.id, {"title": event.title, "start": str(event.start_date)}, db=db, ip=ip)
    await db.commit()
    return EventOut.model_validate(event, from_attributes=True)


async def update_event(db: AsyncSession, actor: User, event_id: uuid.UUID, body: EventIn, ip: str | None) -> EventOut:
    event = await db.get(Event, event_id)
    if event is None:
        raise not_found("Event")
    for k, v in body.model_dump().items():
        setattr(event, k, v)
    log_action(actor, "update", "event", event.id, {"title": event.title}, db=db, ip=ip)
    await db.commit()
    return EventOut.model_validate(event, from_attributes=True)


async def delete_event(db: AsyncSession, actor: User, event_id: uuid.UUID, ip: str | None) -> None:
    event = await db.get(Event, event_id)
    if event is None:
        raise not_found("Event")
    await db.delete(event)
    log_action(actor, "delete", "event", event_id, {"title": event.title}, db=db, ip=ip)
    await db.commit()


async def calendar(db: AsyncSession, user: User, date_from: date, date_to: date) -> list[CalendarItem]:
    if (date_to - date_from).days > 400:
        raise invalid("Pick a range of at most a year.", {"to": "Range too long"})
    items = [
        CalendarItem(kind="holiday", id=h.id, title=h.name, start_date=h.date, end_date=h.date, type="holiday")
        for h in await db.scalars(select(SchoolHoliday).where(SchoolHoliday.date.between(date_from, date_to)))
    ]
    items += [
        CalendarItem(kind="event", id=e.id, title=e.title, start_date=e.start_date, end_date=e.end_date, type=e.type)
        for e in await list_events(db, user, date_from, date_to)
    ]
    exams = (
        select(Exam, SchoolClass.name)
        .join(SchoolClass, SchoolClass.id == Exam.class_id)
        .where(
            Exam.start_date.is_not(None),
            Exam.start_date <= date_to,
            func.coalesce(Exam.end_date, Exam.start_date) >= date_from,
        )
    )
    if user.role == Role.TEACHER:
        teacher_id = await teacher_id_for(db, user)
        exams = exams.where(_teacher_covers(teacher_id, Exam.class_id, _literal(None)) if teacher_id else false())
    elif user.role not in SCHOOL_WIDE:
        mine = await _children_clause(db, user)
        exams = exams.where(Exam.class_id.in_(select(Student.class_id).where(mine, Student.is_deleted.is_(False))))
    items += [
        CalendarItem(
            kind="exam",
            id=x.id,
            title=f"{x.name} ({class_name})",
            start_date=x.start_date,
            end_date=x.end_date or x.start_date,
            type=x.type,
        )
        for x, class_name in (await db.execute(exams)).all()
    ]
    return sorted(items, key=lambda i: (i.start_date, i.kind, i.title))


# --- notifications (reader side) -----------------------------------------------------------------


async def list_notifications(db: AsyncSession, user: User, params: PageParams, unread_only: bool) -> Page:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    return await paginate(db, stmt.order_by(Notification.created_at.desc()), params, NotificationOut)


async def unread_count(db: AsyncSession, user: User) -> int:
    return await db.scalar(select(func.count()).where(Notification.user_id == user.id, Notification.is_read.is_(False)))


async def mark_read(db: AsyncSession, user: User, notification_id: uuid.UUID | None) -> None:
    """One notification, or all of the user's when `notification_id` is None."""
    stmt = update(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))
    if notification_id is not None:
        stmt = stmt.where(Notification.id == notification_id)
    await db.execute(stmt.values(is_read=True))
    await db.commit()
