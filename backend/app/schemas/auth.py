import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Role
from app.schemas.fields import InModel


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    full_name: str | None
    role: Role
    is_active: bool
    must_change_password: bool
    last_login: datetime | None


class UserCreate(InModel):
    """Staff accounts without a profile. Teacher/student/parent logins come from registration."""

    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    full_name: str = Field(min_length=1, max_length=150)
    role: Literal[Role.ADMIN, Role.CEO, Role.HEADMASTER]


class UserUpdate(InModel):
    username: str | None = Field(None, min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    full_name: str | None = Field(None, min_length=1, max_length=150)


class PasswordSet(InModel):
    """Empty body or no password: a random one-time password. A chosen password needs no change at sign-in."""

    password: str | None = Field(None, min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)
