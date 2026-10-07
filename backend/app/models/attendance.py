import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, enum_col
from app.models.enums import AttendanceStatus, TeacherAttendanceStatus


class Attendance(IdMixin, TimestampMixin, Base):
    __tablename__ = "attendance"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    status: Mapped[AttendanceStatus] = mapped_column(enum_col(AttendanceStatus))
    remarks: Mapped[str | None] = mapped_column(Text)
    marked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        UniqueConstraint("student_id", "date"),  # also the (student_id, date) lookup index
        Index("ix_attendance_date", "date"),
        Index("ix_attendance_date_student_id", "date", "student_id"),
    )


class TeacherAttendance(IdMixin, TimestampMixin, Base):
    """Feeds salary deductions (Phase 4)."""

    __tablename__ = "teacher_attendance"

    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    status: Mapped[TeacherAttendanceStatus] = mapped_column(enum_col(TeacherAttendanceStatus))
    remarks: Mapped[str | None] = mapped_column(Text)
    marked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (UniqueConstraint("teacher_id", "date"),)


class SchoolHoliday(IdMixin, TimestampMixin, Base):
    __tablename__ = "school_holidays"

    date: Mapped[date] = mapped_column(Date, unique=True)
    name: Mapped[str] = mapped_column(String(150))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
