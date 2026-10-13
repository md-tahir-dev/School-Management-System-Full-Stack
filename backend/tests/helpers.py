"""Builders for Phase 2 tests. Data is never truncated between tests, so everything uses unique names."""

import random
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import update

from app.db.session import SessionLocal
from app.models import (
    AcademicYear,
    ClassSubject,
    FeeStructure,
    SchoolClass,
    Section,
    Subject,
)
from app.schemas.students import StudentCreate
from app.schemas.teachers import TeacherCreate
from app.services import students as student_svc
from app.services import teachers as teacher_svc
from app.services.settings import get_school_settings
from tests.conftest import DEFAULT_PASSWORD


def _digits(n: int) -> str:
    return "".join(random.choices("0123456789", k=n))


def rand_cnic() -> str:
    return f"{_digits(5)}-{_digits(7)}-{_digits(1)}"


def rand_phone() -> str:
    return f"03{_digits(2)}-{_digits(7)}"


def tag() -> str:
    return uuid.uuid4().hex[:8]


async def make_school(fee: str | None = "2000") -> SimpleNamespace:
    """A current academic year (starting this month), one class with sections A and B, two subjects mapped
    100/40, and a monthly fee. Pass fee=None to leave the class without a fee structure."""
    t = tag()
    start = date.today().replace(day=1)
    async with SessionLocal() as db:
        await db.execute(update(AcademicYear).values(is_current=False))
        year = AcademicYear(
            label=f"T{t}", start_date=start, end_date=date(start.year + 1, start.month, 1), is_current=True
        )
        klass = SchoolClass(name=f"Class-{t}", sort_order=1)
        db.add_all([year, klass])
        await db.flush()
        sec_a, sec_b = Section(class_id=klass.id, name="A"), Section(class_id=klass.id, name="B")
        math, english = Subject(name=f"Math-{t}"), Subject(name=f"English-{t}")
        db.add_all([sec_a, sec_b, math, english])
        await db.flush()
        db.add_all(
            ClassSubject(class_id=klass.id, subject_id=s.id, total_marks=100, passing_marks=40) for s in (math, english)
        )
        if fee is not None:
            db.add(FeeStructure(class_id=klass.id, monthly_fee=Decimal(fee)))
        settings = await get_school_settings(db)
        settings.fee_due_day = 10
        settings.late_fine_amount = Decimal(0)  # other tests change it and don't reset it
        settings.current_academic_year_id = year.id
        await db.commit()
    return SimpleNamespace(year=year, klass=klass, sec_a=sec_a, sec_b=sec_b, math=math, english=english)


def student_payload(school, **overrides) -> dict:
    guardian = {
        "father_name": f"Father {tag()}",
        "father_cnic": rand_cnic(),
        "father_phone": rand_phone(),
    }
    guardian.update(overrides.pop("guardian", {}))
    body = {
        "full_name": f"Student {tag()}",
        "dob": "2015-05-10",
        "gender": "male",
        "class_id": str(school.klass.id),
        "section_id": str(school.sec_a.id),
        "guardian": guardian,
    }
    body.update(overrides)
    return body


async def create_student(school, *, logins=None, **overrides):
    """Registers through the same service function the API uses."""
    payload = StudentCreate(**student_payload(school, **overrides))
    async with SessionLocal() as db:
        return await student_svc.register_student(db, payload, None, logins=logins)


def teacher_payload(school, **overrides) -> dict:
    body = {
        "full_name": f"Teacher {tag()}",
        "gender": "female",
        "cnic": rand_cnic(),
        "phone": rand_phone(),
        "designation": "Teacher",
        "qualification": "Master's",
        "joining_date": "2024-08-01",
        "employment_type": "full_time",
        "salary": {"basic": "50000", "house": "10000", "transport": "5000", "medical": "2500"},
        "assignments": [
            {"class_id": str(school.klass.id), "section_id": str(school.sec_a.id), "subject_id": str(school.math.id)}
        ],
    }
    body.update(overrides)
    return body


async def create_teacher(school, *, password: str = DEFAULT_PASSWORD, **overrides):
    """Registers through the service with a known login so the test can sign in as the teacher."""
    payload = TeacherCreate(**teacher_payload(school, **overrides))
    username = f"t-{tag()}"
    async with SessionLocal() as db:
        reg = await teacher_svc.register_teacher(db, payload, None, login=(username, password))
    return reg, username
