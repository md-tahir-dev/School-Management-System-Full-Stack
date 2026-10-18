"""Teacher attendance: Admin-only marking, CEO read-only. Feeds Phase 4 salary deductions."""

import calendar
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden, invalid, not_found
from app.core.permissions import MANAGERS, SCHOOL_WIDE
from app.models import Role, Teacher, TeacherAttendance, User
from app.schemas.attendance import (
    BulkAttendanceResult,
    BulkTeacherAttendanceIn,
    TeacherAttendanceSummary,
    TeacherRosterOut,
    TeacherRosterRow,
)
from app.services.attendance import _assert_date_allowed, _today  # date rules are shared with students
from app.services.audit import log_action
from app.services.settings import get_school_settings


async def get_roster(db: AsyncSession, actor: User, day: date | None) -> TeacherRosterOut:
    school = await get_school_settings(db)
    day = day or _today(school)
    teachers = list(
        (await db.scalars(select(Teacher).where(Teacher.is_deleted.is_(False)).order_by(Teacher.full_name))).all()
    )
    existing = {
        a.teacher_id: a
        for a in (
            await db.scalars(
                select(TeacherAttendance).where(
                    TeacherAttendance.date == day,
                    TeacherAttendance.teacher_id.in_([t.id for t in teachers] or [uuid.uuid4()]),
                )
            )
        ).all()
    }
    rows = [
        TeacherRosterRow(
            teacher_id=t.id,
            full_name=t.full_name,
            employee_id=t.employee_id,
            status=existing[t.id].status if t.id in existing else None,
            remarks=existing[t.id].remarks if t.id in existing else None,
        )
        for t in teachers
    ]
    is_editable = day <= _today(school)
    return TeacherRosterOut(date=day, is_editable=is_editable, teachers=rows)


async def bulk_save(db: AsyncSession, actor: User, body: BulkTeacherAttendanceIn, ip: str | None) -> BulkAttendanceResult:
    if actor.role not in MANAGERS:
        raise forbidden()
    school = await get_school_settings(db)
    await _assert_date_allowed(db, school, body.date)

    known_ids = set((await db.scalars(select(Teacher.id).where(Teacher.is_deleted.is_(False)))).all())
    sent_ids = {r.teacher_id for r in body.records}
    if unknown := sent_ids - known_ids:
        raise invalid("Unknown teacher.", {"records": f"{len(unknown)} teacher(s) not found"})

    values = [
        {
            "teacher_id": r.teacher_id,
            "date": body.date,
            "status": r.status.value,
            "remarks": r.remarks,
            "marked_by": actor.id,
        }
        for r in body.records
    ]
    stmt = pg_insert(TeacherAttendance).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[TeacherAttendance.teacher_id, TeacherAttendance.date],
        set_={
            "status": stmt.excluded.status,
            "remarks": stmt.excluded.remarks,
            "marked_by": stmt.excluded.marked_by,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)

    counts: dict[str, int] = {}
    for r in body.records:
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
    log_action(actor, "bulk_save", "teacher_attendance", str(body.date), {"date": str(body.date), "counts": counts}, db=db, ip=ip)
    await db.commit()
    return BulkAttendanceResult(saved=len(body.records), counts=counts)


async def teacher_summary(db: AsyncSession, user: User, teacher_id: uuid.UUID, month: str) -> TeacherAttendanceSummary:
    if user.role not in (*SCHOOL_WIDE, Role.TEACHER):
        raise forbidden()  # before the lookup, so the status doesn't reveal whether the id exists
    teacher = await db.get(Teacher, teacher_id)
    if teacher is None or teacher.is_deleted:
        raise not_found("Teacher")
    if user.role == Role.TEACHER and teacher.user_id != user.id:
        raise not_found("Teacher")

    year, mon = (int(x) for x in month.split("-"))
    start = date(year, mon, 1)
    end = date(year, mon, calendar.monthrange(year, mon)[1])
    rows = await db.execute(
        select(TeacherAttendance.status, func.count())
        .where(TeacherAttendance.teacher_id == teacher_id, TeacherAttendance.date >= start, TeacherAttendance.date <= end)
        .group_by(TeacherAttendance.status)
    )
    counts = {status.value: n for status, n in rows.all()}
    return TeacherAttendanceSummary(
        month=month,
        present=counts.get("present", 0),
        absent=counts.get("absent", 0),
        late=counts.get("late", 0),
        leave=counts.get("leave", 0),
    )
