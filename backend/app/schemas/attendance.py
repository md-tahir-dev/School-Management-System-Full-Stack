import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AttendanceStatus, TeacherAttendanceStatus
from app.schemas.fields import InModel


# --------------------------------------------------------------- holidays
class HolidayIn(InModel):
    date: date
    name: str = Field(min_length=1, max_length=150)


class HolidayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: date
    name: str


# ------------------------------------------------------------ student roster
class RosterStudent(BaseModel):
    student_id: uuid.UUID
    roll_no: str
    full_name: str
    photo_url: str | None
    status: AttendanceStatus | None  # null = not yet marked today
    remarks: str | None


class RosterOut(BaseModel):
    class_id: uuid.UUID
    section_id: uuid.UUID | None
    date: date
    is_holiday: bool
    holiday_name: str | None
    is_editable: bool
    students: list[RosterStudent]


class AttendanceRecordIn(InModel):
    student_id: uuid.UUID
    status: AttendanceStatus
    remarks: str | None = Field(None, max_length=500)


class BulkAttendanceIn(InModel):
    class_id: uuid.UUID
    section_id: uuid.UUID | None = None
    date: date
    records: list[AttendanceRecordIn] = Field(min_length=1)


class BulkAttendanceResult(BaseModel):
    saved: int
    counts: dict[str, int]  # status -> count, for the audit line and the UI's sticky footer


# ------------------------------------------------------------------ summary
class AttendanceSummary(BaseModel):
    month: str  # "YYYY-MM"
    present: int
    absent: int
    late: int
    sick: int
    school_days: int
    month_percentage: Decimal
    year_percentage: Decimal
    below_threshold: bool


class CalendarDay(BaseModel):
    date: date
    status: str | None  # present|absent|late|sick|holiday|off|null
    holiday_name: str | None = None


class CalendarOut(BaseModel):
    month: str
    days: list[CalendarDay]


# ------------------------------------------------------------------- reports
class ClassAttendanceRow(BaseModel):
    student_id: uuid.UUID
    roll_no: str
    full_name: str
    present: int
    absent: int
    late: int
    sick: int
    percentage: Decimal


class ClassAttendanceReport(BaseModel):
    from_date: date
    to_date: date
    rows: list[ClassAttendanceRow]


class SectionOverviewRow(BaseModel):
    class_id: uuid.UUID
    class_name: str
    section_id: uuid.UUID | None
    section_name: str | None
    present_percent: Decimal | None
    absent_count: int
    marked: bool


class OverviewOut(BaseModel):
    date: date
    school_present_percent: Decimal
    absent_count: int
    unmarked_sections: int
    sections: list[SectionOverviewRow]


class LowAttendanceRow(BaseModel):
    student_id: uuid.UUID
    roll_no: str
    full_name: str
    class_name: str
    section_name: str | None
    percentage: Decimal
    guardian_phone: str | None


class LowAttendanceOut(BaseModel):
    threshold: int
    students: list[LowAttendanceRow]


# ------------------------------------------------------------- teacher side
class TeacherRosterRow(BaseModel):
    teacher_id: uuid.UUID
    full_name: str
    employee_id: str
    status: TeacherAttendanceStatus | None
    remarks: str | None


class TeacherRosterOut(BaseModel):
    date: date
    is_editable: bool
    teachers: list[TeacherRosterRow]


class TeacherAttendanceRecordIn(InModel):
    teacher_id: uuid.UUID
    status: TeacherAttendanceStatus
    remarks: str | None = Field(None, max_length=500)


class BulkTeacherAttendanceIn(InModel):
    date: date
    records: list[TeacherAttendanceRecordIn] = Field(min_length=1)


class TeacherAttendanceSummary(BaseModel):
    month: str
    present: int
    absent: int
    late: int
    leave: int
