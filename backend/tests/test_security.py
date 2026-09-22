import re
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    generate_temp_password,
    hash_password,
    hash_token,
    validate_password_strength,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("Secret123")
    assert hashed.startswith("$argon2id$")
    assert verify_password("Secret123", hashed)
    assert not verify_password("secret123", hashed)


def test_verify_against_missing_hash_is_always_false():
    assert verify_password("dummy-password-for-timing", None) is False


def test_verify_garbage_hash_is_false():
    assert verify_password("x", "not-a-hash") is False


@pytest.mark.parametrize(
    ("password", "expected_problem"),
    [
        ("Ab1", "at least 8"),
        ("abcdefgh", "digit"),
        ("12345678", "letter"),
        ("a1" * 70, "at most 128"),
    ],
)
def test_password_strength_rejects(password, expected_problem):
    assert any(expected_problem in p for p in validate_password_strength(password))


def test_password_strength_accepts():
    assert validate_password_strength("Goodpass1") == []


def test_temp_password_is_random_and_strong():
    passwords = {generate_temp_password() for _ in range(50)}
    assert len(passwords) == 50
    for p in passwords:
        assert len(p) == 10
        assert re.search(r"[a-z]", p) and re.search(r"[A-Z]", p) and re.search(r"\d", p)
        assert not set(p) & set("0OIl1")  # no look-alikes


def test_access_token_roundtrip():
    uid = uuid.uuid4()
    token, expires_in = create_access_token(uid, "teacher")
    payload = decode_access_token(token)
    assert payload["sub"] == str(uid)
    assert payload["role"] == "teacher"
    assert expires_in == settings.access_token_minutes * 60


def test_expired_token_rejected():
    past = datetime.now(UTC) - timedelta(minutes=1)
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "exp": past}, settings.jwt_secret, algorithm="HS256"
    )
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_wrong_signature_rejected():
    token = jwt.encode(
        {"sub": "x", "type": "access", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        "some-other-secret-that-is-long-enough-123",
        algorithm="HS256",
    )
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_wrong_token_type_rejected():
    token = jwt.encode(
        {"sub": "x", "type": "refresh", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_alg_none_rejected():
    token = jwt.encode({"sub": "x", "type": "access"}, None, algorithm="none")
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_refresh_token_is_stored_hashed():
    raw, hashed = generate_refresh_token()
    assert raw != hashed and hashed == hash_token(raw) and len(hashed) == 64
