"""Reusable validated field types and the base class for request bodies."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints, model_validator

from app.utils.validators import normalize_phone, validate_blood_group, validate_cnic

Cnic = Annotated[str, AfterValidator(validate_cnic)]
Phone = Annotated[str, AfterValidator(normalize_phone)]
BloodGroup = Annotated[str, AfterValidator(validate_blood_group)]
PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)]


class InModel(BaseModel):
    """Base for request bodies: unknown fields are rejected, whitespace is trimmed, and blank strings
    become null (so an empty optional input from a form is "not provided", not an invalid value)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def _blank_to_none(cls, data):
        if isinstance(data, dict):
            return {k: (None if isinstance(v, str) and not v.strip() else v) for k, v in data.items()}
        return data


class Credential(BaseModel):
    """Shown exactly once, in the response that created (or reset) the account."""

    username: str
    temp_password: str
