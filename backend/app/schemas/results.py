import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ExamType, ResultStatus
from app.schemas.fields import InModel


# ---------------------------------------------------------------------- exams
class ExamIn(InModel):
    name: str = Field(min_length=1, max_length=150)
    type: ExamType
    academic_year_id: uuid.UUID
    class_id: uuid.UUID
    start_date: date | None = None
    end_date: date | None = None


class ExamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: ExamType
    academic_year_id: uuid.UUID
    class_id: uuid.UUID
    class_name: str
    start_date: date | None
    end_date: date | None
    is_published: bool
    published_at: datetime | None
    created_at: datetime


class ExamSubjectIn(InModel):
    subject_id: uuid.UUID
    total_marks: Decimal = Field(gt=0, max_digits=6, decimal_places=2)
    passing_marks: Decimal = Field(ge=0, max_digits=6, decimal_places=2)


class ExamSubjectOut(BaseModel):
    subject_id: uuid.UUID
    subject_name: str
    total_marks: Decimal
    passing_marks: Decimal


class PublishPreview(BaseModel):
    incomplete_count: int
    complete_count: int


class UnpublishIn(InModel):
    reason: str = Field(min_length=3, max_length=500)


# ---------------------------------------------------------------- marks entry
class MarkEntryRow(BaseModel):
    student_id: uuid.UUID
    roll_no: str
    full_name: str
    total_marks: Decimal
    passing_marks: Decimal
    obtained_marks: Decimal | None
    is_absent: bool


class MarksSheetOut(BaseModel):
    exam_id: uuid.UUID
    subject_id: uuid.UUID
    subject_name: str
    section_id: uuid.UUID | None
    is_locked: bool  # published, or (for teachers) not their assignment
    rows: list[MarkEntryRow]


class MarkSaveIn(InModel):
    student_id: uuid.UUID
    subject_id: uuid.UUID
    obtained_marks: Decimal = Field(ge=0, max_digits=6, decimal_places=2)
    is_absent: bool = False


class MarksBulkSaveIn(InModel):
    entries: list[MarkSaveIn] = Field(min_length=1)
    reason: str | None = Field(None, max_length=500)  # required by the service once the exam is published


class StudentEntrySubject(BaseModel):
    subject_id: uuid.UUID
    subject_name: str
    total_marks: Decimal
    passing_marks: Decimal
    obtained_marks: Decimal | None
    is_absent: bool
    status: str | None  # Pass | Fail | AB | null (not entered)


class StudentEntryOut(BaseModel):
    exam_id: uuid.UUID
    student_id: uuid.UUID
    full_name: str
    roll_no: str
    subjects: list[StudentEntrySubject]
    total_obtained: Decimal
    total_possible: Decimal
    percentage: Decimal
    grade: str | None
    is_complete: bool


class StudentEntrySaveIn(InModel):
    subjects: list[MarkSaveIn] = Field(min_length=1)
    reason: str | None = Field(None, max_length=500)


# -------------------------------------------------------------------- results
class ResultSubjectRow(BaseModel):
    subject_id: uuid.UUID
    subject_name: str
    total_marks: Decimal
    passing_marks: Decimal
    obtained_marks: Decimal
    is_absent: bool
    status: str  # Pass | Fail | AB


class ResultOut(BaseModel):
    id: uuid.UUID
    exam_id: uuid.UUID
    exam_name: str
    exam_type: ExamType
    academic_year_label: str
    student_id: uuid.UUID
    student_name: str
    roll_no: str
    class_name: str
    section_name: str | None
    father_name: str | None
    subjects: list[ResultSubjectRow]
    total_obtained: Decimal
    total_possible: Decimal
    percentage: Decimal
    grade: str
    rank: int | None
    total_ranked: int | None
    is_pass: bool
    status: ResultStatus
    remarks: str | None
    is_published: bool


class ClassResultRow(BaseModel):
    # result_id / exam_id / exam_name are additive (Phase 3 frontend): they let a list row open its
    # result card and let the student's Results tab show which exam each row belongs to.
    result_id: uuid.UUID | None = None
    exam_id: uuid.UUID | None = None
    exam_name: str | None = None
    student_id: uuid.UUID
    roll_no: str
    full_name: str
    section_name: str | None
    total_obtained: Decimal
    total_possible: Decimal
    percentage: Decimal
    grade: str
    rank: int | None
    is_pass: bool
    status: ResultStatus


class TrendPoint(BaseModel):
    exam_id: uuid.UUID
    exam_name: str
    percentage: Decimal
    grade: str


class StudentResultsOut(BaseModel):
    results: list[ClassResultRow]  # reuses the row shape; exam_name carried via trend for charting
    trend: list[TrendPoint]


class SubjectAnalytics(BaseModel):
    subject_id: uuid.UUID
    subject_name: str
    average_percentage: Decimal
    pass_rate: Decimal


class LeaderboardRow(BaseModel):
    student_id: uuid.UUID
    full_name: str
    roll_no: str
    percentage: Decimal
    rank: int | None


class ExamAnalyticsOut(BaseModel):
    exam_id: uuid.UUID
    class_average: Decimal
    highest: Decimal
    lowest: Decimal
    pass_percent: Decimal
    grade_distribution: dict[str, int]
    subjects: list[SubjectAnalytics]
    top_students: list[LeaderboardRow]
    not_entered_count: int
    complete_count: int
    total_students: int


class MarksProgressRow(BaseModel):
    subject_id: uuid.UUID
    subject_name: str
    section_id: uuid.UUID | None
    section_name: str | None
    entered: int
    total: int


SortDirection = Literal["asc", "desc"]
