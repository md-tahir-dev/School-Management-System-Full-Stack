import uuid
from datetime import time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Period(IdMixin, TimestampMixin, Base):
    """School-wide bell schedule slot."""

    __tablename__ = "periods"

    name: Mapped[str] = mapped_column(String(64))
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_break: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    __table_args__ = (CheckConstraint("end_time > start_time", name="end_after_start"),)


class TimetableEntry(IdMixin, TimestampMixin, Base):
    __tablename__ = "timetable_entries"

    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    section_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 1=Monday .. 7=Sunday
    period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("periods.id", ondelete="CASCADE"))
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), index=True)
    room: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (
        CheckConstraint("weekday BETWEEN 1 AND 7", name="weekday_range"),
        UniqueConstraint(
            "class_id",
            "section_id",
            "weekday",
            "period_id",
            name="uq_timetable_slot",
            postgresql_nulls_not_distinct=True,
        ),
        UniqueConstraint("teacher_id", "weekday", "period_id", name="uq_timetable_teacher_slot"),
    )


class ClassTeacher(IdMixin, TimestampMixin, Base):
    __tablename__ = "class_teachers"

    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    section_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"))
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), index=True)

    __table_args__ = (
        UniqueConstraint("class_id", "section_id", name="uq_class_teacher", postgresql_nulls_not_distinct=True),
    )
