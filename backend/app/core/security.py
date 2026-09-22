"""Password hashing, JWT access tokens and opaque refresh tokens."""

import asyncio
import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

_hasher = PasswordHasher()
# Verified against when the username doesn't exist, so timing doesn't reveal valid usernames.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


async def ahash_password(password: str) -> str:
    """Argon2 is CPU-heavy (~50 ms); run it in a worker thread so the event loop keeps serving requests."""
    return await asyncio.to_thread(hash_password, password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        ok = _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return ok and password_hash is not None


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def validate_password_strength(password: str) -> list[str]:
    """Returns a list of problems; empty means the password is acceptable."""
    problems = []
    if len(password) < 8:
        problems.append("must be at least 8 characters")
    if len(password) > 128:
        problems.append("must be at most 128 characters")
    if not re.search(r"[A-Za-z]", password):
        problems.append("must contain a letter")
    if not re.search(r"\d", password):
        problems.append("must contain a digit")
    return problems


def generate_temp_password(length: int = 10) -> str:
    """Random one-time password: guaranteed lower, upper and digit; no look-alike characters."""
    lower = "abcdefghijkmnpqrstuvwxyz"
    upper = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    digits = "23456789"
    chars = [secrets.choice(lower), secrets.choice(upper), secrets.choice(digits)]
    pool = lower + upper + digits
    chars += [secrets.choice(pool) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


# ---------------------------------------------------------------- access tokens
class TokenError(Exception):
    pass


def create_access_token(user_id: uuid.UUID, role: str) -> tuple[str, int]:
    """Returns (token, expires_in_seconds)."""
    now = datetime.now(UTC)
    expires = timedelta(minutes=settings.access_token_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + expires,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expires.total_seconds())


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("type") != "access":
        raise TokenError("wrong token type")
    return payload


# --------------------------------------------------------------- refresh tokens
def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_refresh_token() -> tuple[str, str]:
    """Opaque random token. Only its SHA-256 hash is stored. Returns (raw, hash)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def random_token(nbytes: int = 24) -> str:
    """Unguessable URL-safe token (e.g. public test share links)."""
    return secrets.token_urlsafe(nbytes)
