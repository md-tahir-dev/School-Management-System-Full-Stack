import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, enum_col
from app.models.enums import ExamType


class Exam(IdMixin, TimestampMixin, Base):
    __tablename__ = "exams"

    name: Mapped[str] = mapped_column(String(150))
    type: Mapped[ExamType] = mapped_column(enum_col(ExamType))
    academic_year_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_years.id"))
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id"))


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

    __table_args__ = (
        UniqueConstraint("exam_id", "student_id"),  # also serves the (exam_id, student_id) lookup index
        Index("ix_results_student_id", "student_id"),
    )


class ResultItem(IdMixin, Base):
    __tablename__ = "result_items"

    result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("results.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id"))
    total_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    obtained_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    passing_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    is_pass: Mapped[bool] = mapped_column(Boolean)

    __table_args__ = (UniqueConstraint("result_id", "subject_id"),)
