import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, enum_col
from app.models.enums import Audience, MaterialType, Priority


class Material(IdMixin, TimestampMixin, Base):
    __tablename__ = "materials"

    title: Mapped[str] = mapped_column(String(200))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subjects.id"))
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id"), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[MaterialType] = mapped_column(enum_col(MaterialType))
    file_url: Mapped[str | None] = mapped_column(String(500))
    external_link: Mapped[str | None] = mapped_column(String(500))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Announcement(IdMixin, TimestampMixin, Base):
    __tablename__ = "announcements"

    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    audience: Mapped[Audience] = mapped_column(enum_col(Audience))
    priority: Mapped[Priority] = mapped_column(
        enum_col(Priority), default=Priority.NORMAL, server_default=Priority.NORMAL.value
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Notification(IdMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
