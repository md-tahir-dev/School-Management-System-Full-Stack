"""Attendance reporting: class report, whole-school overview, and the low-attendance list.
Results/exam analytics live in `app.services.exams` since they're exam-scoped, not date-range-scoped."""

import csv
import io
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden
from app.models import Attendance, Guardian, Role, SchoolClass, Section, Student, StudentGuardian, User
from app.models.enums import StudentStatus
from app.schemas.attendance import (
    ClassAttendanceReport,
    ClassAttendanceRow,
    LowAttendanceOut,
    LowAttendanceRow,
    OverviewOut,
    SectionOverviewRow,
)
from app.services.scoping import teacher_assigned_to_section, teacher_id_for
from app.utils.money import money


def _pct(attended: int, denom: int) -> Decimal:
    if denom <= 0:
        return Decimal("0.00")
    return (Decimal(attended) / Decimal(denom) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def _assert_class_section_scope(db: AsyncSession, user: User, class_id: uuid.UUID, section_id: uuid.UUID | None) -> None:
    if user.role in (Role.ADMIN, Role.CEO):
        return
    if user.role == Role.TEACHER:
        teacher_id = await teacher_id_for(db, user)
        if teacher_id and section_id and await teacher_assigned_to_section(db, teacher_id, class_id, section_id):
            return
    raise forbidden()


async def class_report(
    db: AsyncSession, user: User, class_id: uuid.UUID, section_id: uuid.UUID, from_date: date, to_date: date
) -> ClassAttendanceReport:
    await _assert_class_section_scope(db, user, class_id, section_id)
    students = list(
        (
            await db.scalars(
                select(Student)
                .where(
                    Student.class_id == class_id,
                    Student.section_id == section_id,
                    Student.is_deleted.is_(False),
                    Student.status == StudentStatus.ACTIVE,
                )
                .order_by(Student.roll_no)
            )
        ).all()
    )
    rows = []
    for s in students:
        counts_rows = await db.execute(
            select(Attendance.status, func.count())
            .where(Attendance.student_id == s.id, Attendance.date >= from_date, Attendance.date <= to_date)
            .group_by(Attendance.status)
        )
        counts = {status.value: n for status, n in counts_rows.all()}
        present, absent, late, sick = (counts.get(k, 0) for k in ("present", "absent", "late", "sick"))
        school_days = present + absent + late + sick
        rows.append(
            ClassAttendanceRow(
                student_id=s.id,
                roll_no=s.roll_no,
                full_name=s.full_name,
                present=present,
                absent=absent,
                late=late,
                sick=sick,
                percentage=money(_pct(present + late, school_days - sick)),
            )
        )
    rows.sort(key=lambda r: r.percentage)
    return ClassAttendanceReport(from_date=from_date, to_date=to_date, rows=rows)


def class_report_csv(report: ClassAttendanceReport) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Roll No", "Name", "Present", "Absent", "Late", "Sick", "Percentage"])
    for r in report.rows:
        writer.writerow([r.roll_no, r.full_name, r.present, r.absent, r.late, r.sick, str(r.percentage)])
    return buf.getvalue()


async def overview(db: AsyncSession, user: User, day: date) -> OverviewOut:
    if user.role not in (Role.ADMIN, Role.CEO):
        raise forbidden()
    sections = await db.execute(
        select(Section, SchoolClass.name)
        .join(SchoolClass, SchoolClass.id == Section.class_id)
        .order_by(SchoolClass.sort_order, Section.name)
    )
    rows = []
    total_present = total_marked = total_absent = unmarked = 0
    for section, class_name in sections.all():
        counts_rows = await db.execute(
            select(Attendance.status, func.count())
            .select_from(Attendance)
            .join(Student, Student.id == Attendance.student_id)
            .where(Student.section_id == section.id, Attendance.date == day)
            .group_by(Attendance.status)
        )
        counts = {status.value: n for status, n in counts_rows.all()}
        marked = sum(counts.values())
        present, absent, late = counts.get("present", 0), counts.get("absent", 0), counts.get("late", 0)
        is_marked = marked > 0
        if not is_marked:
            unmarked += 1
        else:
            total_present += present + late
            total_marked += marked
            total_absent += absent
        rows.append(
            SectionOverviewRow(
                class_id=section.class_id,
                class_name=class_name,
                section_id=section.id,
                section_name=section.name,
                present_percent=money(_pct(present + late, marked)) if is_marked else None,
                absent_count=absent,
                marked=is_marked,
            )
        )
    return OverviewOut(
        date=day,
        school_present_percent=money(_pct(total_present, total_marked)),
        absent_count=total_absent,
        unmarked_sections=unmarked,
        sections=rows,
    )


async def low_attendance(db: AsyncSession, user: User, threshold: int) -> LowAttendanceOut:
    if user.role not in (Role.ADMIN, Role.CEO):
        raise forbidden()
    students = list(
        (
            await db.scalars(
                select(Student).where(Student.is_deleted.is_(False), Student.status == StudentStatus.ACTIVE)
            )
        ).all()
    )
    rows: list[LowAttendanceRow] = []
    for s in students:
        counts_rows = await db.execute(
            select(Attendance.status, func.count()).where(Attendance.student_id == s.id).group_by(Attendance.status)
        )
        counts = {status.value: n for status, n in counts_rows.all()}
        present, late, sick = counts.get("present", 0), counts.get("late", 0), counts.get("sick", 0)
        school_days = sum(counts.values())
        if school_days == 0:
            continue
        pct = _pct(present + late, school_days - sick)
        if pct < threshold:
            klass = await db.get(SchoolClass, s.class_id)
            section = await db.get(Section, s.section_id) if s.section_id else None
            phone = await db.scalar(
                select(Guardian.father_phone)
                .join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
                .where(StudentGuardian.student_id == s.id)
                .limit(1)
            )
            rows.append(
                LowAttendanceRow(
                    student_id=s.id,
                    roll_no=s.roll_no,
                    full_name=s.full_name,
                    class_name=klass.name if klass else "",
                    section_name=section.name if section else None,
                    percentage=money(pct),
                    guardian_phone=phone,
                )
            )
    rows.sort(key=lambda r: r.percentage)
    return LowAttendanceOut(threshold=threshold, students=rows)
