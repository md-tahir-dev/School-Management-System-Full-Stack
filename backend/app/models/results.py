import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, enum_col
from app.models.enums import ExamType, ResultStatus


class Exam(IdMixin, TimestampMixin, Base):
    __tablename__ = "exams"

    name: Mapped[str] = mapped_column(String(150))
    type: Mapped[ExamType] = mapped_column(enum_col(ExamType))
    academic_year_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_years.id"))
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id"))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (UniqueConstraint("class_id", "academic_year_id", "name"),)


class ExamSubject(IdMixin, TimestampMixin, Base):
    """Per-exam copy of `class_subjects`, editable while the exam is unpublished. `result_items` snapshot
    from here, never from `class_subjects` directly, so later syllabus changes never rewrite history."""

    __tablename__ = "exam_subjects"

    exam_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
    total_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    passing_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))

    __table_args__ = (UniqueConstraint("exam_id", "subject_id"),)


class Result(IdMixin, TimestampMixin, Base):
    __tablename__ = "results"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    exam_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"))
    total_obtained: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    total_possible: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    grade: Mapped[str] = mapped_column(String(3))
    rank: Mapped[int | None] = mapped_column(Integer)
    is_pass: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[ResultStatus] = mapped_column(
        enum_col(ResultStatus), default=ResultStatus.DRAFT, server_default=ResultStatus.DRAFT.value
    )
    remarks: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("exam_id", "student_id"),  # also serves the (exam_id, student_id) lookup index
        Index("ix_results_student_id", "student_id"),
        Index("ix_results_exam_id_percentage", "exam_id", "percentage"),
    )


class ResultItem(IdMixin, Base):
    """Marks are a snapshot copied from `exam_subjects` at save time; editing `exam_subjects` afterwards
    never rewrites a row here."""

    __tablename__ = "result_items"

    result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("results.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id"))
    total_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    obtained_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    passing_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    is_pass: Mapped[bool] = mapped_column(Boolean)
    is_absent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    __table_args__ = (UniqueConstraint("result_id", "subject_id"),)
