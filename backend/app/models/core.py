import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, enum_col
from app.models.enums import Role


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(enum_col(Role), index=True)
    full_name: Mapped[str | None] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # brute-force protection
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    first_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(IdMixin, Base):
    """Rotating opaque refresh tokens. Rows sharing `family_id` descend from one login."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AcademicYear(IdMixin, TimestampMixin, Base):
    __tablename__ = "academic_years"

    label: Mapped[str] = mapped_column(String(32), unique=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    __table_args__ = (
        # at most one current academic year
        Index("uq_academic_years_single_current", "is_current", unique=True, postgresql_where=text("is_current")),
    )


class SchoolSettings(IdMixin, TimestampMixin, Base):
    """Singleton row (the app reads the first row)."""

    __tablename__ = "school_settings"

    name: Mapped[str] = mapped_column(String(150))
    slogan: Mapped[str | None] = mapped_column(String(255))
    logo_url: Mapped[str | None] = mapped_column(String(500))
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(150))
    website: Mapped[str | None] = mapped_column(String(200))
    fee_due_day: Mapped[int] = mapped_column(Integer, default=10, server_default="10")
    late_fine_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, server_default="0")
    fail_if_any_subject_failed: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    current_academic_year_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("academic_years.id", ondelete="SET NULL")
    )
    # --- Phase 3: attendance & results ---
    weekly_off_days: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=lambda: [7], server_default=text("'{7}'")
    )  # ISO weekday numbers (Mon=1..Sun=7); default = Sunday only
    attendance_alert_threshold: Mapped[int] = mapped_column(Integer, default=75, server_default="75")
    backdate_limit_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Karachi", server_default="Asia/Karachi")


class SchoolClass(IdMixin, TimestampMixin, Base):
    __tablename__ = "classes"

    name: Mapped[str] = mapped_column(String(64), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Section(IdMixin, TimestampMixin, Base):
    __tablename__ = "sections"

    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(32))

    __table_args__ = (UniqueConstraint("class_id", "name"),)


class Subject(IdMixin, TimestampMixin, Base):
    __tablename__ = "subjects"

    name: Mapped[str] = mapped_column(String(100), unique=True)


class ClassSubject(IdMixin, TimestampMixin, Base):
    __tablename__ = "class_subjects"

    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
    total_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=100, server_default="100")
    passing_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=33, server_default="33")

    __table_args__ = (UniqueConstraint("class_id", "subject_id"),)


class Counter(IdMixin, Base):
    """Race-safe sequences (roll no, employee id, receipt no). `year` = 0 for non-yearly keys."""

    __tablename__ = "counters"

    key: Mapped[str] = mapped_column(String(64))
    year: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_value: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    __table_args__ = (UniqueConstraint("key", "year"),)


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(32))  # create / update / delete / payment / login ...
    entity: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    diff: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
