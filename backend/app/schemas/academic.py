import uuid
from datetime import date
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.schemas.fields import InModel

Money = Field(ge=0, max_digits=12, decimal_places=2)


class AcademicYearIn(InModel):
    label: str = Field(min_length=1, max_length=32)
    start_date: date
    end_date: date

    @field_validator("end_date")
    @classmethod
    def _after_start(cls, v: date, info: ValidationInfo) -> date:
        start = info.data.get("start_date")
        if start and v <= start:
            raise ValueError("Must be after the start date")
        return v


class AcademicYearOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    start_date: date
    end_date: date
    is_current: bool


class ClassIn(InModel):
    name: str = Field(min_length=1, max_length=64)
    order: int = Field(0, ge=0, le=1000)


class ClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    name: str
    order: int = Field(validation_alias=AliasChoices("order", "sort_order"))
    section_count: int = 0
    student_count: int = 0


class SectionIn(InModel):
    name: str = Field(min_length=1, max_length=32)


class SectionOut(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    name: str
    student_count: int = 0


class SubjectIn(InModel):
    name: str = Field(min_length=1, max_length=100)


class SubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class ClassSubjectIn(InModel):
    subject_id: uuid.UUID
    total_marks: Decimal = Field(gt=0, max_digits=6, decimal_places=2)
    passing_marks: Decimal = Field(ge=0, max_digits=6, decimal_places=2)

    @field_validator("passing_marks")
    @classmethod
    def _not_above_total(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        total = info.data.get("total_marks")
        if total is not None and v > total:
            raise ValueError("Passing marks cannot exceed total marks")
        return v


class ClassSubjectOut(BaseModel):
    subject_id: uuid.UUID
    subject_name: str
    total_marks: Decimal
    passing_marks: Decimal


class FeeStructureIn(InModel):
    class_id: uuid.UUID
    monthly_fee: Decimal = Money


class FeeStructureOut(BaseModel):
    class_id: uuid.UUID
    class_name: str
    monthly_fee: Decimal


class LogoOut(BaseModel):
    logo_url: str


class ResetPasswordOut(BaseModel):
    username: str
    temp_password: str
    must_change_password: bool = True
