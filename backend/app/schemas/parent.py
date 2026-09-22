import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.models.enums import FeeStatus, StudentStatus


class ChildSummary(BaseModel):
    id: uuid.UUID
    full_name: str
    roll_no: str
    class_name: str
    section_name: str | None
    photo_url: str | None


class FeeMonthSummary(BaseModel):
    month: date
    status: FeeStatus
    total_payable: Decimal
    paid_amount: Decimal
    due_date: date


class ChildDashboard(BaseModel):
    """`latest_result`, `attendance_percentage`, `upcoming_tests` and `announcements` are always null in
    Phase 2. They are part of the schema now so phases 3 to 6 can fill them without breaking clients."""

    child: ChildSummary
    status: StudentStatus
    fee_current_month: FeeMonthSummary | None
    latest_result: dict[str, Any] | None = None  # phase 3
    attendance_percentage: float | None = None  # phase 3
    upcoming_tests: list[dict[str, Any]] | None = None  # phase 5
    announcements: list[dict[str, Any]] | None = None  # phase 6
