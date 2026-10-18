import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import Audience, EventType, Priority
from app.schemas.fields import InModel


class AnnouncementIn(InModel):
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=5000)
    audience: Audience = Audience.ALL
    priority: Priority = Priority.NORMAL
    class_id: uuid.UUID | None = None  # null: whole school
    section_id: uuid.UUID | None = None


class AnnouncementOut(BaseModel):
    id: uuid.UUID
    title: str
    message: str
    audience: Audience
    priority: Priority
    class_id: uuid.UUID | None
    class_name: str | None
    section_id: uuid.UUID | None
    section_name: str | None
    author_name: str | None
    created_at: datetime
    can_edit: bool


class EventIn(InModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    start_date: date
    end_date: date | None = None  # defaults to start_date
    type: EventType = EventType.EVENT
    audience: Audience = Audience.ALL

    @model_validator(mode="after")
    def _range(self):
        if self.end_date is None:
            self.end_date = self.start_date
        if self.end_date < self.start_date:
            raise ValueError("end_date can't be before start_date")
        return self


class EventOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    start_date: date
    end_date: date
    type: EventType
    audience: Audience


class CalendarItem(BaseModel):
    kind: Literal["holiday", "event", "exam"]
    id: uuid.UUID
    title: str
    start_date: date
    end_date: date
    type: str  # event type, "holiday", or the exam type


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message: str
    link: str | None  # role-relative path, e.g. "diary?date=2026-10-08"
    is_read: bool
    created_at: datetime


class UnreadCount(BaseModel):
    count: int
