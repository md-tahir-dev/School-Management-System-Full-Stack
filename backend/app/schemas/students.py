import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.models.enums import FeeStatus, Gender, StudentStatus
from app.schemas.fields import BloodGroup, Cnic, Credential, InModel, PersonName, Phone
from app.utils.validators import student_dob


class GuardianIn(InModel):
    father_name: PersonName
    father_cnic: Cnic
    father_phone: Phone
    father_occupation: str | None = Field(None, max_length=100)
    mother_name: PersonName | None = None
    mother_cnic: Cnic | None = None
    mother_phone: Phone | None = None
    guardian_name: PersonName | None = None
    guardian_phone: Phone | None = None
    guardian_relation: str | None = Field(None, max_length=64)


class GuardianUpdate(InModel):
    """Edits the (shared) guardian record. The father's CNIC is the identity key and cannot change."""

    father_name: PersonName | None = None
    father_phone: Phone | None = None
    father_occupation: str | None = Field(None, max_length=100)
    mother_name: PersonName | None = None
    mother_cnic: Cnic | None = None
    mother_phone: Phone | None = None
    guardian_name: PersonName | None = None
    guardian_phone: Phone | None = None
    guardian_relation: str | None = Field(None, max_length=64)


class GuardianOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    father_name: str | None
    father_cnic: str | None
    father_phone: str | None
    father_occupation: str | None
    mother_name: str | None
    mother_cnic: str | None
    mother_phone: str | None
    guardian_name: str | None
    guardian_phone: str | None
    guardian_relation: str | None


class StudentCreate(InModel):
    full_name: PersonName
    dob: date
    gender: Gender
    religion: str | None = Field(None, max_length=64)
    nationality: str | None = Field(None, max_length=64)
    blood_group: BloodGroup | None = None
    class_id: uuid.UUID
    section_id: uuid.UUID | None = None
    admission_date: date | None = None
    previous_school: str | None = Field(None, max_length=200)
    address: str | None = Field(None, max_length=1000)
    city: str | None = Field(None, max_length=100)
    emergency_name: PersonName | None = None
    emergency_phone: Phone | None = None
    guardian: GuardianIn
    create_student_login: bool = False
    discount_percent: Decimal = Field(Decimal(0), ge=0, le=100, max_digits=5, decimal_places=2)

    @field_validator("dob")
    @classmethod
    def _dob(cls, v: date) -> date:
        return student_dob(v)


class StudentUpdate(InModel):
    """PATCH-like: only the fields sent are changed. `roll_no` is immutable."""

    roll_no: str | None = None
    full_name: PersonName | None = None
    dob: date | None = None
    gender: Gender | None = None
    religion: str | None = Field(None, max_length=64)
    nationality: str | None = Field(None, max_length=64)
    blood_group: BloodGroup | None = None
    class_id: uuid.UUID | None = None
    section_id: uuid.UUID | None = None
    admission_date: date | None = None
    previous_school: str | None = Field(None, max_length=200)
    address: str | None = Field(None, max_length=1000)
    city: str | None = Field(None, max_length=100)
    emergency_name: PersonName | None = None
    emergency_phone: Phone | None = None
    guardian: GuardianUpdate | None = None

    @field_validator("roll_no")
    @classmethod
    def _roll_no_immutable(cls, v):
        if v is not None:
            raise ValueError("Roll number cannot be changed")
        return v

    @field_validator("dob")
    @classmethod
    def _dob(cls, v: date | None) -> date | None:
        return student_dob(v) if v else v


class StatusUpdate(InModel):
    status: StudentStatus
    reason: str | None = Field(None, max_length=500, validate_default=True)

    @field_validator("reason")
    @classmethod
    def _expelled_needs_reason(cls, v: str | None, info: ValidationInfo) -> str | None:
        # attributed to the `reason` field so the form can show the message under that input
        if info.data.get("status") == StudentStatus.EXPELLED and not v:
            raise ValueError("A reason is required when expelling a student")
        return v


class DiscountUpdate(InModel):
    discount_percent: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)


class DiscountResult(BaseModel):
    discount_percent: Decimal
    recalculated_rows: int


class StudentListItem(BaseModel):
    id: uuid.UUID
    roll_no: str
    full_name: str
    photo_url: str | None
    class_id: uuid.UUID
    class_name: str
    section_id: uuid.UUID | None
    section_name: str | None
    father_name: str | None
    father_phone: str | None
    status: StudentStatus


class StudentDetail(BaseModel):
    id: uuid.UUID
    roll_no: str
    full_name: str
    dob: date | None
    gender: Gender | None
    religion: str | None
    nationality: str | None
    blood_group: str | None
    photo_url: str | None
    class_id: uuid.UUID
    class_name: str
    section_id: uuid.UUID | None
    section_name: str | None
    admission_date: date | None
    previous_school: str | None
    address: str | None
    city: str | None
    emergency_name: str | None
    emergency_phone: str | None
    status: StudentStatus
    status_reason: str | None
    discount_percent: Decimal
    has_login: bool
    guardian: GuardianOut | None
    created_at: datetime


class StudentCredentials(BaseModel):
    """Only ever returned by the registration response; the passwords are not retrievable afterwards."""

    parent: Credential | None
    student: Credential | None


class StudentCreated(BaseModel):
    student: StudentDetail
    credentials: StudentCredentials
    warnings: list[str] = []


class LedgerRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    month: date
    base_fee: Decimal
    discount: Decimal
    fine: Decimal
    total_payable: Decimal
    paid_amount: Decimal
    due_date: date
    status: FeeStatus
    paid_date: date | None
    receipt_no: str | None


class LedgerTotals(BaseModel):
    total_payable: Decimal
    paid_amount: Decimal
    balance: Decimal


class LedgerOut(BaseModel):
    items: list[LedgerRow]
    totals: LedgerTotals
