import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import Designation, EmploymentType, Gender, Qualification
from app.schemas.fields import BloodGroup, Cnic, Credential, InModel, PersonName, Phone
from app.utils.validators import teacher_dob

_MONEY = {"ge": 0, "max_digits": 12, "decimal_places": 2}


class SalaryIn(InModel):
    basic: Decimal = Field(**_MONEY)
    house: Decimal = Field(Decimal(0), **_MONEY)
    transport: Decimal = Field(Decimal(0), **_MONEY)
    medical: Decimal = Field(Decimal(0), **_MONEY)


class SalaryOut(BaseModel):
    basic: Decimal
    house: Decimal
    transport: Decimal
    medical: Decimal
    gross: Decimal  # always computed by the server; never accepted from the client


class AssignmentIn(InModel):
    class_id: uuid.UUID
    section_id: uuid.UUID | None = None
    subject_id: uuid.UUID


class AssignmentOut(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    class_name: str
    section_id: uuid.UUID | None
    section_name: str | None
    subject_id: uuid.UUID
    subject_name: str


class TeacherCreate(InModel):
    full_name: PersonName
    father_name: PersonName | None = None
    dob: date | None = None
    gender: Gender
    cnic: Cnic
    phone: Phone
    emergency_contact: Phone | None = None
    blood_group: BloodGroup | None = None
    religion: str | None = Field(None, max_length=64)
    designation: Designation
    qualification: Qualification
    joining_date: date
    employment_type: EmploymentType
    address: str | None = Field(None, max_length=1000)
    city: str | None = Field(None, max_length=100)
    salary: SalaryIn
    assignments: list[AssignmentIn] = []

    @field_validator("dob")
    @classmethod
    def _dob(cls, v: date | None) -> date | None:
        return teacher_dob(v) if v else v


class TeacherUpdate(InModel):
    """PATCH-like profile edit. Assignments and salary have their own endpoints; `employee_id` is immutable."""

    employee_id: str | None = None
    full_name: PersonName | None = None
    father_name: PersonName | None = None
    dob: date | None = None
    gender: Gender | None = None
    cnic: Cnic | None = None
    phone: Phone | None = None
    emergency_contact: Phone | None = None
    blood_group: BloodGroup | None = None
    religion: str | None = Field(None, max_length=64)
    designation: Designation | None = None
    qualification: Qualification | None = None
    joining_date: date | None = None
    employment_type: EmploymentType | None = None
    address: str | None = Field(None, max_length=1000)
    city: str | None = Field(None, max_length=100)

    @field_validator("employee_id")
    @classmethod
    def _immutable(cls, v):
        if v is not None:
            raise ValueError("Employee ID cannot be changed")
        return v

    @field_validator("dob")
    @classmethod
    def _dob(cls, v: date | None) -> date | None:
        return teacher_dob(v) if v else v


class TeacherListItem(BaseModel):
    id: uuid.UUID
    employee_id: str
    full_name: str
    photo_url: str | None
    designation: str | None
    employment_type: EmploymentType | None
    phone: str | None
    subjects: list[str]
    classes: list[str]


class TeacherDetail(BaseModel):
    id: uuid.UUID
    employee_id: str
    full_name: str
    father_name: str | None
    dob: date | None
    gender: Gender | None
    cnic: str | None
    phone: str | None
    emergency_contact: str | None
    photo_url: str | None
    blood_group: str | None
    religion: str | None
    designation: str | None
    qualification: str | None
    joining_date: date | None
    employment_type: EmploymentType | None
    address: str | None
    city: str | None
    assignments: list[AssignmentOut]
    salary_structure: SalaryOut | None
    created_at: datetime


class TeacherCredentials(BaseModel):
    teacher: Credential


class TeacherCreated(BaseModel):
    teacher: TeacherDetail
    credentials: TeacherCredentials
