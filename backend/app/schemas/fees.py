import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import PaymentMethod
from app.schemas.fields import InModel


class PaymentIn(InModel):
    student_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    method: PaymentMethod
    note: str | None = Field(None, max_length=255)


class VoidIn(InModel):
    reason: str = Field(min_length=3, max_length=255)


class AllocationOut(BaseModel):
    month: date
    amount: Decimal


class PaymentOut(BaseModel):
    id: uuid.UUID
    receipt_no: str
    student_id: uuid.UUID
    student_name: str
    roll_no: str
    class_name: str
    amount: Decimal
    method: PaymentMethod
    note: str | None
    paid_at: datetime
    received_by_name: str | None
    voided_at: datetime | None
    void_reason: str | None
    allocations: list[AllocationOut]


class DefaulterOut(BaseModel):
    student_id: uuid.UUID
    full_name: str
    roll_no: str
    class_name: str
    section_name: str | None
    father_phone: str | None
    months_due: int
    amount_due: Decimal
    oldest_due_date: date


class ClassCollection(BaseModel):
    class_name: str
    billed: Decimal
    collected: Decimal
    outstanding: Decimal


class FeeSummaryOut(BaseModel):
    """Money billed for a month vs. collected against it, plus cash received during it."""

    month: date
    billed: Decimal
    collected: Decimal
    outstanding: Decimal
    received_in_month: Decimal
    overdue_total: Decimal
    by_class: list[ClassCollection]

