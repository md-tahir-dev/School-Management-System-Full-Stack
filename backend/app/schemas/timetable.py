import uuid
from datetime import time

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.fields import InModel


class PeriodIn(InModel):
    name: str = Field(min_length=1, max_length=64)
    start_time: time
    end_time: time
    sort_order: int = 0
    is_break: bool = False

    @model_validator(mode="after")
    def _order(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class PeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    start_time: time
    end_time: time
    sort_order: int
    is_break: bool


class CellIn(InModel):
    """One lecture: who teaches what to a class/section in a weekday + period slot."""

    class_id: uuid.UUID
    section_id: uuid.UUID | None = None
    weekday: int = Field(ge=1, le=7)
    period_id: uuid.UUID
    subject_id: uuid.UUID
    teacher_id: uuid.UUID
    room: str | None = Field(None, max_length=32)


class EntryOut(BaseModel):
    id: uuid.UUID
    weekday: int
    period_id: uuid.UUID
    class_id: uuid.UUID
    class_name: str
    section_id: uuid.UUID | None
    section_name: str | None
    subject_id: uuid.UUID
    subject_name: str
    teacher_id: uuid.UUID
    teacher_name: str
    room: str | None


class TimetableOut(BaseModel):
    periods: list[PeriodOut]
    entries: list[EntryOut]


class ClassTeacherIn(InModel):
    class_id: uuid.UUID
    section_id: uuid.UUID | None = None
    teacher_id: uuid.UUID | None = None  # null removes the class teacher


class ClassTeacherOut(BaseModel):
    class_id: uuid.UUID
    class_name: str
    section_id: uuid.UUID | None
    section_name: str | None
    teacher_id: uuid.UUID
    teacher_name: str
