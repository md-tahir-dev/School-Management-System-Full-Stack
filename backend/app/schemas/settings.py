import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class SchoolSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    slogan: str | None
    logo_url: str | None
    favicon_url: str | None
    login_image_url: str | None
    address: str | None
    phone: str | None
    email: str | None
    website: str | None
    fee_due_day: int
    late_fine_amount: Decimal
    fail_if_any_subject_failed: bool
    current_academic_year_id: uuid.UUID | None
    weekly_off_days: list[int]
    attendance_alert_threshold: int
    backdate_limit_days: int
    timezone: str


class SchoolSettingsUpdate(BaseModel):
    """All fields optional (PATCH-like PUT): only fields that are sent are changed."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=2, max_length=150)
    slogan: str | None = Field(None, max_length=255)
    logo_url: str | None = Field(None, max_length=500)
    address: str | None = Field(None, max_length=1000)
    phone: str | None = Field(None, max_length=32)
    email: EmailStr | None = None
    website: str | None = Field(None, max_length=200)
    fee_due_day: int | None = Field(None, ge=1, le=28)
    late_fine_amount: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    fail_if_any_subject_failed: bool | None = None
    current_academic_year_id: uuid.UUID | None = None
    weekly_off_days: list[int] | None = Field(None, min_length=0, max_length=7)
    attendance_alert_threshold: int | None = Field(None, ge=1, le=100)
    backdate_limit_days: int | None = Field(None, ge=0, le=365)
    timezone: str | None = Field(None, min_length=1, max_length=64)

    @field_validator("weekly_off_days")
    @classmethod
    def _valid_isoweekdays(cls, v):
        if v is not None and any(not (1 <= d <= 7) for d in v):
            raise ValueError("weekly_off_days must use ISO weekday numbers 1 (Mon) to 7 (Sun)")
        return v

    @field_validator("name", "slogan", "address", "phone", "website", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class PublicConfig(BaseModel):
    school_name: str
    slogan: str | None
    logo_url: str | None
    favicon_url: str | None
    login_image_url: str | None
    app_env: str
    demo_accounts: list[dict[str, str]] | None
