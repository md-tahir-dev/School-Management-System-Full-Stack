"""Student attendance: roster, bulk save, monthly/yearly summaries, and the day-by-day calendar.

See the module docstring notes inline for the two documented formulas (Part B1 of the Phase 3 spec):
the attendance percentage, and what counts as a "school day" for a student.
"""

import calendar
import uuid
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import invalid, not_found
from app.core.permissions import MANAGERS
from app.models import (
    AcademicYear,
    Attendance,
    Guardian,
    Notification,
    Role,
    SchoolHoliday,
    Student,
    StudentGuardian,
    User,
)
from app.models.enums import AttendanceStatus, StudentStatus
from app.schemas.attendance import (
    AttendanceSummary,
    BulkAttendanceIn,
    BulkAttendanceResult,
    CalendarDay,
    CalendarOut,
    RosterOut,
    RosterStudent,
)
from app.services.audit import log_action
from app.services.holidays import holiday_on
from app.services.scoping import get_student_in_scope, teacher_assigned_to_section, teacher_id_for
from app.services.settings import get_school_settings
from app.utils.money import money


def _today(school) -> date:
    """"Today" is computed on the server in the school's own timezone, never taken from the client."""
    try:
        tz = ZoneInfo(school.timezone)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


def _is_weekly_off(school, day: date) -> bool:
    return day.isoweekday() in (school.weekly_off_days or [])


async def _editable_for(db: AsyncSession, actor: User, school, day: date) -> tuple[bool, str | None]:
    """(is_editable, reason_if_not). Does NOT check holiday/weekly-off/future - callers check those
    separately since "not editable because it's a holiday" needs a different message than "too old"."""
    if actor.role in MANAGERS:
        return True, None
    if actor.role == Role.TEACHER:
        today = _today(school)
        if (today - day).days > school.backdate_limit_days:
            return False, f"Teachers can only edit attendance up to {school.backdate_limit_days} day(s) back."
        return True, None
    return False, None


async def _assert_date_allowed(db: AsyncSession, school, day: date) -> None:
    today = _today(school)
    if day > today:
        raise invalid("Attendance can't be marked for a future date.", {"date": "Date is in the future"})
    if await holiday_on(db, day) is not None:
        raise invalid("Attendance can't be marked on a holiday.", {"date": "This date is a holiday"})
    if _is_weekly_off(school, day):
        raise invalid("Attendance can't be marked on a weekly off day.", {"date": "This date is a weekly off day"})


async def _roster_students(db: AsyncSession, class_id: uuid.UUID, section_id: uuid.UUID, day: date) -> list[Student]:
    stmt = (
        select(Student)
        .where(
            Student.class_id == class_id,
            Student.section_id == section_id,
            Student.is_deleted.is_(False),
            Student.status == StudentStatus.ACTIVE,
            Student.admission_date.is_not(None),
            Student.admission_date <= day,
        )
        .order_by(Student.roll_no)
    )
    return list((await db.scalars(stmt)).all())


async def _assert_teacher_scope(db: AsyncSession, actor: User, class_id: uuid.UUID, section_id: uuid.UUID) -> None:
    if actor.role != Role.TEACHER:
        return
    teacher_id = await teacher_id_for(db, actor)
    if teacher_id is None or not await teacher_assigned_to_section(db, teacher_id, class_id, section_id):
        raise not_found("Class section")


# ----------------------------------------------------------------------- roster
async def get_roster(
    db: AsyncSession, actor: User, class_id: uuid.UUID, section_id: uuid.UUID, day: date | None
) -> RosterOut:
    school = await get_school_settings(db)
    day = day or _today(school)
    await _assert_teacher_scope(db, actor, class_id, section_id)

    holiday = await holiday_on(db, day)
    is_holiday = holiday is not None
    is_weekly_off = _is_weekly_off(school, day)
    is_future = day > _today(school)
    editable, _ = await _editable_for(db, actor, school, day)
    is_editable = editable and not is_holiday and not is_weekly_off and not is_future

    students = await _roster_students(db, class_id, section_id, day)
    existing = {
        a.student_id: a
        for a in (
            await db.scalars(
                select(Attendance).where(
                    Attendance.date == day, Attendance.student_id.in_([s.id for s in students] or [uuid.uuid4()])
                )
            )
        ).all()
    }
    rows = [
        RosterStudent(
            student_id=s.id,
            roll_no=s.roll_no,
            full_name=s.full_name,
            photo_url=s.photo_url,
            status=existing[s.id].status if s.id in existing else None,
            remarks=existing[s.id].remarks if s.id in existing else None,
        )
        for s in students
    ]
    return RosterOut(
        class_id=class_id,
        section_id=section_id,
        date=day,
        is_holiday=is_holiday or is_weekly_off,
        holiday_name=holiday.name if holiday else ("Weekly off" if is_weekly_off else None),
        is_editable=is_editable,
        students=rows,
    )


# ------------------------------------------------------------------- bulk save
async def bulk_save_attendance(
    db: AsyncSession, actor: User, body: BulkAttendanceIn, ip: str | None
) -> BulkAttendanceResult:
    if body.section_id is None:
        raise invalid("A section is required to save attendance.", {"section_id": "Section is required"})
    school = await get_school_settings(db)
    await _assert_teacher_scope(db, actor, body.class_id, body.section_id)
    await _assert_date_allowed(db, school, body.date)
    editable, reason = await _editable_for(db, actor, school, body.date)
    if not editable:
        raise invalid(reason or "This date can't be edited.", {"date": reason or "Not editable"})

    roster = await _roster_students(db, body.class_id, body.section_id, body.date)
    roster_ids = {s.id for s in roster}
    sent_ids = {r.student_id for r in body.records}
    if unknown := sent_ids - roster_ids:
        raise invalid(
            "Some students are not on this class/section's roster for this date.",
            {"records": f"{len(unknown)} student(s) are not on the roster"},
        )

    now_values = [
        {
            "student_id": r.student_id,
            "date": body.date,
            "status": r.status.value,
            "remarks": r.remarks,
            "marked_by": actor.id,
            "updated_by": actor.id,
        }
        for r in body.records
    ]
    stmt = pg_insert(Attendance).values(now_values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Attendance.student_id, Attendance.date],
        set_={
            "status": stmt.excluded.status,
            "remarks": stmt.excluded.remarks,
            "updated_by": stmt.excluded.updated_by,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)

    counts: dict[str, int] = {}
    for r in body.records:
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
    log_action(
        actor,
        "bulk_save",
        "attendance",
        body.section_id,
        {"date": str(body.date), "class_id": str(body.class_id), "section_id": str(body.section_id), "counts": counts},
        db=db,
        ip=ip,
    )

    await _notify_absentees(db, [r.student_id for r in body.records if r.status == AttendanceStatus.ABSENT], body.date)
    await db.commit()
    return BulkAttendanceResult(saved=len(body.records), counts=counts)


async def _notify_absentees(db: AsyncSession, student_ids: list[uuid.UUID], day: date) -> None:
    """One notification per student per day for each linked parent, even if the day is re-saved."""
    if not student_ids:
        return
    rows = await db.execute(
        select(Student.id, Student.full_name, Guardian.user_id)
        .join(StudentGuardian, StudentGuardian.student_id == Student.id)
        .join(Guardian, Guardian.id == StudentGuardian.guardian_id)
        .where(Student.id.in_(student_ids), Guardian.user_id.is_not(None))
    )
    for student_id, full_name, user_id in rows.all():
        message = f"{full_name} was marked absent on {day.isoformat()}."
        already = await db.scalar(
            select(Notification.id).where(Notification.user_id == user_id, Notification.message == message)
        )
        if already is None:
            db.add(Notification(user_id=user_id, message=message))


# --------------------------------------------------------------------- summary
def _percentage(present: int, late: int, sick: int, school_days: int) -> Decimal:
    denom = school_days - sick
    if denom <= 0:
        return Decimal("0.00")
    attended = present + late
    return (Decimal(attended) / Decimal(denom) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def _section_school_days(db: AsyncSession, section_id: uuid.UUID | None, start: date, end: date) -> int:
    """Distinct dates in [start, end] on which attendance was recorded for the student's section
    (holidays and weekly-offs are never in this count because they're never recorded)."""
    if section_id is None:
        return 0
    stmt = (
        select(func.count(func.distinct(Attendance.date)))
        .select_from(Attendance)
        .join(Student, Student.id == Attendance.student_id)
        .where(Student.section_id == section_id, Attendance.date >= start, Attendance.date <= end)
    )
    return (await db.scalar(stmt)) or 0


async def _status_counts(db: AsyncSession, student_id: uuid.UUID, start: date, end: date) -> dict[str, int]:
    rows = await db.execute(
        select(Attendance.status, func.count())
        .where(Attendance.student_id == student_id, Attendance.date >= start, Attendance.date <= end)
        .group_by(Attendance.status)
    )
    return {status.value: n for status, n in rows.all()}


async def student_summary(db: AsyncSession, user: User, student_id: uuid.UUID, month: str) -> AttendanceSummary:
    student = await get_student_in_scope(db, user, student_id)
    school = await get_school_settings(db)
    year, mon = (int(x) for x in month.split("-"))
    month_start = date(year, mon, 1)
    month_end = date(year, mon, calendar.monthrange(year, mon)[1])

    year_row = await db.scalar(select(AcademicYear).where(AcademicYear.is_current.is_(True)))
    year_start = year_row.start_date if year_row else date(year, 1, 1)
    year_end = year_row.end_date if year_row else date(year, 12, 31)

    m_counts = await _status_counts(db, student.id, month_start, month_end)
    y_counts = await _status_counts(db, student.id, year_start, year_end)
    m_school_days = await _section_school_days(db, student.section_id, month_start, month_end)
    y_school_days = await _section_school_days(db, student.section_id, year_start, year_end)

    m_present, m_late, m_sick = m_counts.get("present", 0), m_counts.get("late", 0), m_counts.get("sick", 0)
    y_present, y_late, y_sick = y_counts.get("present", 0), y_counts.get("late", 0), y_counts.get("sick", 0)
    month_pct = _percentage(m_present, m_late, m_sick, m_school_days)

    return AttendanceSummary(
        month=month,
        present=m_present,
        absent=m_counts.get("absent", 0),
        late=m_late,
        sick=m_sick,
        school_days=m_school_days,
        month_percentage=money(month_pct),
        year_percentage=money(_percentage(y_present, y_late, y_sick, y_school_days)),
        below_threshold=month_pct < school.attendance_alert_threshold,
    )


async def student_calendar(db: AsyncSession, user: User, student_id: uuid.UUID, month: str) -> CalendarOut:
    student = await get_student_in_scope(db, user, student_id)
    school = await get_school_settings(db)
    year, mon = (int(x) for x in month.split("-"))
    days_in_month = calendar.monthrange(year, mon)[1]

    records = {
        a.date: a.status.value
        for a in (
            await db.scalars(
                select(Attendance).where(
                    Attendance.student_id == student.id,
                    Attendance.date >= date(year, mon, 1),
                    Attendance.date <= date(year, mon, days_in_month),
                )
            )
        ).all()
    }
    holidays = {
        h.date: h.name
        for h in (
            await db.scalars(
                select(SchoolHoliday).where(
                    func.extract("year", SchoolHoliday.date) == year,
                    func.extract("month", SchoolHoliday.date) == mon,
                )
            )
        ).all()
    }

    days = []
    for d in range(1, days_in_month + 1):
        day = date(year, mon, d)
        if day in holidays:
            days.append(CalendarDay(date=day, status="holiday", holiday_name=holidays[day]))
        elif _is_weekly_off(school, day):
            days.append(CalendarDay(date=day, status="off"))
        elif day in records:
            days.append(CalendarDay(date=day, status=records[day]))
        else:
            days.append(CalendarDay(date=day, status=None))
    return CalendarOut(month=month, days=days)


async def attendance_percentage_for_student(db: AsyncSession, student: Student, *, today: date | None = None) -> Decimal | None:
    """Used by the student profile header and dashboards: current month's percentage, or None if the
    student's section has no recorded attendance this month yet."""
    if student.section_id is None:
        return None
    school = await get_school_settings(db)
    day = today or _today(school)
    month_start = day.replace(day=1)
    counts = await _status_counts(db, student.id, month_start, day)
    school_days = await _section_school_days(db, student.section_id, month_start, day)
    if school_days == 0:
        return None
    return money(_percentage(counts.get("present", 0), counts.get("late", 0), counts.get("sick", 0), school_days))
