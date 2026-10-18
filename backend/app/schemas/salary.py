import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import SalaryStatus
from app.schemas.fields import InModel


class GenerateIn(InModel):
    month: date  # any day in the month


class GenerateOut(BaseModel):
    created: int
    recalculated: int
    skipped_paid: int
    without_structure: list[str]  # teacher names with no salary structure


class SalaryRecordOut(BaseModel):
    id: uuid.UUID
    teacher_id: uuid.UUID
    teacher_name: str
    employee_id: str
    month: date
    gross: Decimal
    absent_days: int
    absence_deduction: Decimal
    advance_deduction: Decimal
    net: Decimal
    status: SalaryStatus
    paid_date: date | None


class PayIn(InModel):
    paid_date: date | None = None  # defaults to today


class AdvanceIn(InModel):
    teacher_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    month: date  # month it is deducted from (any day in it)
    note: str | None = Field(None, max_length=255)


class AdvanceOut(BaseModel):
    id: uuid.UUID
    teacher_id: uuid.UUID
    teacher_name: str
    amount: Decimal
    month: date
    note: str | None
