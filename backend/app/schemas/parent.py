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
    """`upcoming_tests` and `announcements` stay null until phases 5 and 6. `latest_result` and
    `attendance` are filled in Phase 3; `attendance_percentage` is kept (mirroring
    `attendance.month_percentage`) for any client still reading the Phase 2 shape."""

    child: ChildSummary
    status: StudentStatus
    fee_current_month: FeeMonthSummary | None
    latest_result: dict[str, Any] | None = None  # phase 3: {exam_name, percentage, grade, rank, total_students, is_pass}
    attendance_percentage: float | None = None  # phase 3, deprecated: use `attendance.month_percentage`
    attendance: dict[str, Any] | None = None  # phase 3: {month_percentage, present, absent, late, sick, below_threshold}
    upcoming_tests: list[dict[str, Any]] | None = None  # {id, title, subject, start_at, end_at}
    announcements: list[dict[str, Any]] | None = None  # {id, title, priority, created_at}
