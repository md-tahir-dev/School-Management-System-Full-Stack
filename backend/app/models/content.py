import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, enum_col
from app.models.enums import Audience, EventType, MaterialType, Priority


class Material(IdMixin, TimestampMixin, Base):
    __tablename__ = "materials"
    __table_args__ = (Index("ix_materials_class_section", "class_id", "section_id"),)

    title: Mapped[str] = mapped_column(String(200))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subjects.id"))
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id"), index=True)
    section_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"))
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[MaterialType] = mapped_column(enum_col(MaterialType))
    file_url: Mapped[str | None] = mapped_column(String(500))
    external_link: Mapped[str | None] = mapped_column(String(500))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class DiaryEntry(IdMixin, TimestampMixin, Base):
    __tablename__ = "diary_entries"
    __table_args__ = (
        Index("ix_diary_entries_class_section_date", "class_id", "section_id", "date"),
        CheckConstraint("due_date IS NULL OR due_date >= date", name="due_after_date"),
    )

    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    section_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"))
    # null subject = general note from the class teacher
    subject_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"))
    date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    attachment_url: Mapped[str | None] = mapped_column(String(500))
    submission_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # explicit: `date` above shadows the type
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class DiarySubmission(IdMixin, TimestampMixin, Base):
    __tablename__ = "diary_submissions"
    __table_args__ = (UniqueConstraint("entry_id", "student_id", name="uq_diary_submission"),)

    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("diary_entries.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    file_url: Mapped[str | None] = mapped_column(String(500))
    note: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    checked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    remarks: Mapped[str | None] = mapped_column(String(500))


class Announcement(IdMixin, TimestampMixin, Base):
    __tablename__ = "announcements"
    __table_args__ = (Index("ix_announcements_created_at", "created_at"),)

    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    audience: Mapped[Audience] = mapped_column(enum_col(Audience))
    priority: Mapped[Priority] = mapped_column(
        enum_col(Priority), default=Priority.NORMAL, server_default=Priority.NORMAL.value
    )
    # null class = whole school
    class_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    section_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Event(IdMixin, TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="end_after_start"),
        Index("ix_events_start_date", "start_date"),
    )

    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    type: Mapped[EventType] = mapped_column(enum_col(EventType))
    audience: Mapped[Audience] = mapped_column(
        enum_col(Audience), default=Audience.ALL, server_default=Audience.ALL.value
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Notification(IdMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "is_read"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300))
    is_read: Mapped[bool] = mapped_column(Boolean, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
