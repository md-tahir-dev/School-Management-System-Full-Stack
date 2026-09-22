"""Input validators shared by schemas and services. Each `validate_*` raises ValueError with a
user-facing message, which Pydantic turns into a field-level error."""

import re
from datetime import date

CNIC_RE = re.compile(r"^\d{5}-\d{7}-\d$")
PHONE_RE = re.compile(r"^03\d{2}-?\d{7}$")
BLOOD_GROUPS = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")


def validate_cnic(value: str) -> str:
    value = value.strip()
    if not CNIC_RE.match(value):
        raise ValueError("Invalid CNIC format (use 00000-0000000-0)")
    return value


def normalize_phone(value: str) -> str:
    """Accepts 03XXXXXXXXX or 03XX-XXXXXXX, returns 03XX-XXXXXXX."""
    value = value.strip()
    if not PHONE_RE.match(value):
        raise ValueError("Invalid mobile number (use 03XX-XXXXXXX)")
    digits = value.replace("-", "")
    return f"{digits[:4]}-{digits[4:]}"


def validate_blood_group(value: str) -> str:
    value = value.strip().upper()
    if value not in BLOOD_GROUPS:
        raise ValueError(f"Blood group must be one of {', '.join(BLOOD_GROUPS)}")
    return value


def age_on(dob: date, today: date) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def validate_dob(
    dob: date, *, min_age: int | None = None, max_age: int | None = None, today: date | None = None
) -> date:
    today = today or date.today()
    if dob >= today:
        raise ValueError("Date of birth must be in the past")
    age = age_on(dob, today)
    if min_age is not None and age < min_age:
        raise ValueError(f"Must be at least {min_age} years old")
    if max_age is not None and age > max_age:
        raise ValueError(f"Must be at most {max_age} years old")
    return dob


def student_dob(dob: date) -> date:
    return validate_dob(dob, min_age=3, max_age=25)


def teacher_dob(dob: date) -> date:
    return validate_dob(dob, min_age=18, max_age=70)
