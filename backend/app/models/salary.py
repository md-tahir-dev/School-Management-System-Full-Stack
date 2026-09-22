import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, enum_col
from app.models.enums import SalaryStatus

_ZERO = "0"


class SalaryStructure(IdMixin, TimestampMixin, Base):
    __tablename__ = "salary_structures"

    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), unique=True)
    basic: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=_ZERO)
    house: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=_ZERO)
    transport: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=_ZERO)
    medical: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=_ZERO)


class SalaryRecord(IdMixin, TimestampMixin, Base):
    """`month` is the first day of the month."""

    __tablename__ = "salary_records"

    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"))
    month: Mapped[date] = mapped_column(Date)
    gross: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    absent_days: Mapped[int] = mapped_column(Integer, server_default=_ZERO)
    absence_deduction: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=_ZERO)
    advance_deduction: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=_ZERO)
    net: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[SalaryStatus] = mapped_column(
        enum_col(SalaryStatus), default=SalaryStatus.UNPAID, server_default=SalaryStatus.UNPAID.value
    )
    paid_date: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (UniqueConstraint("teacher_id", "month"),)


class SalaryAdvance(IdMixin, TimestampMixin, Base):
    __tablename__ = "salary_advances"

    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    month: Mapped[date] = mapped_column(Date)  # month it is deducted from
    note: Mapped[str | None] = mapped_column(String(255))
