import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, enum_col
from app.models.enums import AttemptStatus, QuestionType, TestStatus


class OnlineTest(IdMixin, TimestampMixin, Base):
    __tablename__ = "tests"

    title: Mapped[str] = mapped_column(String(200))
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id"))
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id"), index=True)
    section_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sections.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    instructions: Mapped[str | None] = mapped_column(Text)
    time_limit_min: Mapped[int] = mapped_column(Integer)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[TestStatus] = mapped_column(
        enum_col(TestStatus), default=TestStatus.DRAFT, server_default=TestStatus.DRAFT.value
    )
    share_token: Mapped[str] = mapped_column(String(64), unique=True)
    show_one_by_one: Mapped[bool] = mapped_column(Boolean, server_default=false())
    results_released: Mapped[bool] = mapped_column(Boolean, server_default=false())


class Question(IdMixin, TimestampMixin, Base):
    __tablename__ = "questions"

    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), index=True)
    type: Mapped[QuestionType] = mapped_column(enum_col(QuestionType))
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list | None] = mapped_column(JSONB)
    correct_answer: Mapped[str | None] = mapped_column(Text)  # never sent to students
    marks: Mapped[Decimal] = mapped_column(Numeric(6, 2), server_default="1")
    model_answer: Mapped[str | None] = mapped_column(Text)  # never sent to students
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")


class Attempt(IdMixin, TimestampMixin, Base):
    __tablename__ = "test_attempts"

    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("students.id", ondelete="SET NULL"))
    guest_name: Mapped[str | None] = mapped_column(String(150))
    guest_roll_no: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # server-owned deadline
    score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    status: Mapped[AttemptStatus] = mapped_column(
        enum_col(AttemptStatus),
        default=AttemptStatus.IN_PROGRESS,
        server_default=AttemptStatus.IN_PROGRESS.value,
    )

    __table_args__ = (
        # one attempt per student / per guest roll number
        Index(
            "uq_test_attempts_test_student",
            "test_id",
            "student_id",
            unique=True,
            postgresql_where=text("student_id IS NOT NULL"),
        ),
        Index(
            "uq_test_attempts_test_guest_roll",
            "test_id",
            "guest_roll_no",
            unique=True,
            postgresql_where=text("guest_roll_no IS NOT NULL"),
        ),
        Index("ix_test_attempts_status_expires_at", "status", "expires_at"),
    )


class AttemptAnswer(IdMixin, TimestampMixin, Base):
    __tablename__ = "attempt_answers"

    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_attempts.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    answer: Mapped[str | None] = mapped_column(Text)
    marks_awarded: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    is_graded: Mapped[bool] = mapped_column(Boolean, server_default=false())

    __table_args__ = (UniqueConstraint("attempt_id", "question_id"),)
