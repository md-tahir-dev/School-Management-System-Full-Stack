import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import MaterialType
from app.schemas.fields import InModel


class DiaryIn(InModel):
    class_id: uuid.UUID
    section_id: uuid.UUID | None = None
    subject_id: uuid.UUID | None = None  # null: a general note from the class teacher
    date: date
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10_000)
    submission_required: bool = False
    due_date: date | None = None

    @model_validator(mode="after")
    def _due(self):
        if self.due_date is not None and self.due_date < self.date:
            raise ValueError("due_date can't be before the diary date")
        return self


class SubmissionOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    file_url: str | None
    note: str | None
    submitted_at: datetime
    checked: bool
    remarks: str | None
    late: bool


class DiaryOut(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    class_name: str
    section_id: uuid.UUID | None
    section_name: str | None
    subject_id: uuid.UUID | None
    subject_name: str | None
    date: date
    title: str
    body: str
    attachment_url: str | None
    submission_required: bool
    due_date: date | None
    author_name: str | None
    created_at: datetime
    can_edit: bool
    submission_count: int | None = None  # staff only
    my_submission: SubmissionOut | None = None  # student/parent only


class SubmissionRow(BaseModel):
    """One student of the entry's class/section, with their submission if any."""

    student_id: uuid.UUID
    full_name: str
    roll_no: str
    submission: SubmissionOut | None


class SubmissionCheckIn(InModel):
    checked: bool
    remarks: str | None = Field(None, max_length=500)


class MaterialOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    type: MaterialType
    class_id: uuid.UUID
    class_name: str
    section_id: uuid.UUID | None
    section_name: str | None
    subject_id: uuid.UUID | None
    subject_name: str | None
    file_url: str | None
    external_link: str | None
    author_name: str | None
    created_at: datetime
    can_edit: bool
