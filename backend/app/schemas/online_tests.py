import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import AttemptStatus, QuestionType, TestStatus
from app.schemas.fields import InModel


class TestIn(InModel):
    __test__ = False  # not a pytest class

    title: str = Field(min_length=1, max_length=200)
    subject_id: uuid.UUID
    class_id: uuid.UUID
    section_id: uuid.UUID | None = None
    instructions: str | None = Field(None, max_length=5000)
    time_limit_min: int = Field(ge=1, le=600)
    start_at: datetime
    end_at: datetime
    show_one_by_one: bool = False

    @model_validator(mode="after")
    def _window(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class QuestionIn(InModel):
    type: QuestionType
    text: str = Field(min_length=1, max_length=5000)
    options: list[str] | None = Field(None, max_length=10)
    correct_answer: str | None = Field(None, max_length=2000)
    marks: Decimal = Field(gt=0, le=100, max_digits=6, decimal_places=2)
    model_answer: str | None = Field(None, max_length=5000)

    @model_validator(mode="after")
    def _shape(self):
        if self.type == QuestionType.MCQ:
            opts = [o.strip() for o in self.options or [] if o and o.strip()]
            if len(opts) < 2 or len(set(opts)) != len(opts):
                raise ValueError("a multiple-choice question needs at least two different options")
            if self.correct_answer not in opts:
                raise ValueError("the correct answer must be one of the options")
            self.options = opts
        elif self.type == QuestionType.TRUE_FALSE:
            if self.correct_answer not in ("true", "false"):
                raise ValueError('a true/false answer must be "true" or "false"')
            self.options = None
        else:
            self.options = None
        return self


class QuestionsIn(InModel):
    questions: list[QuestionIn] = Field(max_length=200)


class QuestionOut(BaseModel):
    """Staff view, including the answer key."""

    id: uuid.UUID
    type: QuestionType
    text: str
    options: list[str] | None
    correct_answer: str | None
    marks: Decimal
    model_answer: str | None


class StudentQuestionOut(BaseModel):
    """What a student sees while answering: never the answer key."""

    id: uuid.UUID
    type: QuestionType
    text: str
    options: list[str] | None
    marks: Decimal


class TestOut(BaseModel):
    __test__ = False

    id: uuid.UUID
    title: str
    subject_id: uuid.UUID
    subject_name: str
    class_id: uuid.UUID
    class_name: str
    section_id: uuid.UUID | None
    section_name: str | None
    instructions: str | None
    time_limit_min: int
    start_at: datetime | None
    end_at: datetime | None
    status: TestStatus
    show_one_by_one: bool
    results_released: bool
    total_marks: Decimal
    question_count: int
    author_name: str | None
    can_edit: bool


class TestDetailOut(TestOut):
    questions: list[QuestionOut]
    attempt_count: int


class MyTestOut(TestOut):
    """A student's row: the test plus their attempt state (score only once results are released)."""

    attempt_id: uuid.UUID | None
    attempt_status: AttemptStatus | None
    score: Decimal | None


class AnswerIn(InModel):
    question_id: uuid.UUID
    answer: str | None = Field(None, max_length=5000)


class AnswersIn(InModel):
    answers: list[AnswerIn] = Field(max_length=200)


class AttemptView(BaseModel):
    """The running attempt: questions without the key, saved answers, and the server deadline."""

    attempt_id: uuid.UUID
    test_id: uuid.UUID
    title: str
    instructions: str | None
    show_one_by_one: bool
    status: AttemptStatus
    expires_at: datetime
    server_now: datetime
    questions: list[StudentQuestionOut]
    answers: dict[uuid.UUID, str | None]


class AnswerResult(BaseModel):
    question_id: uuid.UUID
    text: str
    type: QuestionType
    options: list[str] | None
    answer: str | None
    correct_answer: str | None
    marks: Decimal
    marks_awarded: Decimal | None
    is_graded: bool


class AttemptResult(BaseModel):
    attempt_id: uuid.UUID
    test_id: uuid.UUID
    title: str
    student_name: str
    roll_no: str | None
    status: AttemptStatus
    started_at: datetime
    submitted_at: datetime | None
    score: Decimal | None
    total_marks: Decimal
    released: bool
    answers: list[AnswerResult]  # empty for students until results are released


class AttemptRow(BaseModel):
    attempt_id: uuid.UUID
    student_id: uuid.UUID | None
    student_name: str
    roll_no: str | None
    status: AttemptStatus
    started_at: datetime
    submitted_at: datetime | None
    score: Decimal | None
    needs_grading: int


class GradeIn(InModel):
    marks: dict[uuid.UUID, Decimal]  # question_id -> marks awarded (short answers)
