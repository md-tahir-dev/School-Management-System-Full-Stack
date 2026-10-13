"""Shared dashboard building blocks (Part D): the Latest Result and Attendance cards used by the
Parent, Student, and CEO dashboards, plus the CEO's whole-school attendance/pass-rate summary."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden, not_found
from app.models import Exam, Result, Role, SchoolClass, Student, User
from app.models.enums import ResultStatus
from app.services.attendance import _today, student_summary
from app.services.exams import exam_analytics
from app.services.settings import get_school_settings
from app.utils.money import money


async def latest_result_card(db: AsyncSession, student_id: uuid.UUID) -> dict[str, Any] | None:
    result = await db.scalar(
        select(Result)
        .join(Exam, Exam.id == Result.exam_id)
        .where(Result.student_id == student_id, Result.status == ResultStatus.COMPLETE, Exam.is_published.is_(True))
        .order_by(Exam.published_at.desc())
        .limit(1)
    )
    if result is None:
        return None
    exam = await db.get(Exam, result.exam_id)
    total_ranked = await db.scalar(
        select(func.count()).select_from(Result).where(Result.exam_id == result.exam_id, Result.status == ResultStatus.COMPLETE)
    )
    return {
        "exam_name": exam.name if exam else "",
        "percentage": float(money(result.percentage)),
        "grade": result.grade,
        "rank": result.rank,
        "total_students": total_ranked,
        "is_pass": result.is_pass,
    }


async def attendance_card(db: AsyncSession, student: Student) -> dict[str, Any] | None:
    if student.section_id is None:
        return None
    school = await get_school_settings(db)
    month = _today(school).strftime("%Y-%m")

    class _FakeUser:
        role = Role.ADMIN  # internal call: bypass scope, the caller already checked it
        id = None

    summary = await student_summary(db, _FakeUser(), student.id, month)
    return {
        "month_percentage": float(summary.month_percentage),
        "present": summary.present,
        "absent": summary.absent,
        "late": summary.late,
        "sick": summary.sick,
        "below_threshold": summary.below_threshold,
    }


async def student_own_dashboard(db: AsyncSession, user: User) -> dict[str, Any]:
    if user.role != Role.STUDENT:
        raise forbidden()
    student = await db.scalar(select(Student).where(Student.user_id == user.id, Student.is_deleted.is_(False)))
    if student is None:
        raise not_found("Student profile")
    from app.services.parents import child_dashboard  # parents imports this module's cards

    return (await child_dashboard(db, user, student.id)).model_dump(mode="json")


async def ceo_dashboard(db: AsyncSession, user: User) -> dict[str, Any]:
    if user.role not in (Role.CEO, Role.HEADMASTER):
        raise forbidden()
    school = await get_school_settings(db)
    today = _today(school)

    from app.models import Attendance
    from app.models import Section as _Section

    counts = await db.execute(
        select(Attendance.status, func.count())
        .select_from(Attendance)
        .join(Student, Student.id == Attendance.student_id)
        .where(Attendance.date == today, Student.is_deleted.is_(False))
        .group_by(Attendance.status)
    )
    counts = {status.value: n for status, n in counts.all()}
    present, late = counts.get("present", 0), counts.get("late", 0)
    marked = sum(counts.values())
    today_percent = (float(present + late) / marked * 100) if marked else 0.0

    section_total = await db.scalar(select(func.count()).select_from(_Section))
    marked_sections = await db.scalar(
        select(func.count(func.distinct(Student.section_id)))
        .select_from(Attendance)
        .join(Student, Student.id == Attendance.student_id)
        .where(Attendance.date == today)
    )
    unmarked = max((section_total or 0) - (marked_sections or 0), 0)

    class_pass_rates = []
    classes = (await db.scalars(select(SchoolClass).order_by(SchoolClass.sort_order))).all()
    for klass in classes:
        exam = await db.scalar(
            select(Exam).where(Exam.class_id == klass.id, Exam.is_published.is_(True)).order_by(Exam.published_at.desc()).limit(1)
        )
        if exam is None:
            continue
        analytics = await exam_analytics(db, user, exam.id)
        class_pass_rates.append({"class_name": klass.name, "exam_name": exam.name, "pass_percent": float(analytics.pass_percent)})

    return {
        "today_attendance_percent": round(today_percent, 2),
        "unmarked_sections": unmarked,
        "class_pass_rates": class_pass_rates,
    }
