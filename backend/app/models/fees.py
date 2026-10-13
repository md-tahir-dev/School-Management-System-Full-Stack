import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, enum_col
from app.models.enums import FeeStatus, PaymentMethod

_ZERO = "0"


class FeeStructure(IdMixin, TimestampMixin, Base):
    __tablename__ = "fee_structures"

    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), unique=True)
    monthly_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=_ZERO)
    exam_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=_ZERO)
    library_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=_ZERO)
    admission_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=_ZERO)


class StudentFeeSetting(IdMixin, TimestampMixin, Base):
    __tablename__ = "student_fee_settings"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), unique=True)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), server_default=_ZERO)
    transport_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=_ZERO)


class FeeLedger(IdMixin, TimestampMixin, Base):
    """One row per student per month. `month` is always the first day of the month."""

    __tablename__ = "fee_ledger"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    academic_year_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_years.id"))
    month: Mapped[date] = mapped_column(Date)
    base_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=_ZERO)
    fine: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=_ZERO)
    fine_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_payable: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=_ZERO)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[FeeStatus] = mapped_column(
        enum_col(FeeStatus), default=FeeStatus.UNPAID, server_default=FeeStatus.UNPAID.value
    )
    paid_date: Mapped[date | None] = mapped_column(Date)
    receipt_no: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (
        UniqueConstraint("student_id", "month"),  # also the (student_id, month) lookup index
        Index("ix_fee_ledger_status_due_date", "status", "due_date"),
    )


class Payment(IdMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id"), index=True)
    receipt_no: Mapped[str] = mapped_column(String(32), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[PaymentMethod] = mapped_column(enum_col(PaymentMethod))
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    received_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(String(255))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    void_reason: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (Index("ix_payments_paid_at", "paid_at"),)


class PaymentAllocation(IdMixin, Base):
    """Splits one payment across several monthly ledger rows (advance / multi-month payment)."""

    __tablename__ = "payment_allocations"

    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), index=True)
    ledger_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fee_ledger.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
