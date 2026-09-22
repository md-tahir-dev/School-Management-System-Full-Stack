from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import AuditLog, RefreshToken, Role, User
from tests.conftest import DEFAULT_PASSWORD, cookie_value, login

# ------------------------------------------------------------------ login


async def test_login_success_returns_token_and_sets_cookies(client, make_user):
    user, password = await make_user(Role.TEACHER)
    resp = await login(client, user.username, password)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.access_token_minutes * 60
    assert body["user"]["role"] == "teacher"
    assert "password_hash" not in resp.text

    cookies = resp.headers.get_list("set-cookie")
    refresh = next(c for c in cookies if c.startswith("sms_refresh="))
    assert "HttpOnly" in refresh and "Path=/api/v1/auth" in refresh and "SameSite=lax" in refresh
    assert cookie_value(resp, "sms_role") == "teacher"

    async with SessionLocal() as db:
        fresh = await db.get(User, user.id)
        assert fresh.last_login is not None
        assert await db.scalar(select(AuditLog.id).where(AuditLog.user_id == user.id, AuditLog.action == "login"))


async def test_refresh_token_is_never_stored_in_plaintext(client, make_user):
    user, password = await make_user()
    raw = cookie_value(await login(client, user.username, password), "sms_refresh")
    async with SessionLocal() as db:
        hashes = (await db.scalars(select(RefreshToken.token_hash).where(RefreshToken.user_id == user.id))).all()
    assert raw not in hashes and len(hashes) == 1


async def test_login_username_is_case_insensitive(client, make_user):
    user, password = await make_user(username="mixedcase-user")
    assert (await login(client, "  MixedCase-User ", password)).status_code == 200


async def test_wrong_password_and_unknown_user_look_identical(client, make_user):
    user, _ = await make_user()
    wrong = await login(client, user.username, "not-the-password")
    unknown = await login(client, "does-not-exist", "whatever1")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["code"] == unknown.json()["code"] == "INVALID_CREDENTIALS"
    assert wrong.json()["detail"] == unknown.json()["detail"]


async def test_deactivated_account_cannot_log_in(client, make_user):
    user, password = await make_user(is_active=False)
    resp = await login(client, user.username, password)
    assert resp.status_code == 403 and resp.json()["code"] == "ACCOUNT_DISABLED"
    # ...and a wrong password doesn't reveal that the account exists but is disabled
    assert (await login(client, user.username, "nope")).status_code == 401


async def test_login_validation_error_never_echoes_password(client):
    resp = await client.post("/api/v1/auth/login", json={"username": "someone", "password": "x" * 500})
    assert resp.status_code == 422
    assert "x" * 50 not in resp.text
    assert resp.json()["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------- lockout


async def test_account_locks_after_five_failures_then_recovers(client, make_user):
    user, password = await make_user()
    for _ in range(4):
        assert (await login(client, user.username, "bad-password1")).status_code == 401
    fifth = await login(client, user.username, "bad-password1")
    assert fifth.status_code == 429 and fifth.json()["code"] == "ACCOUNT_LOCKED"
    assert "retry-after" in fifth.headers

    # correct password is refused while locked
    assert (await login(client, user.username, password)).status_code == 429

    # lock expires
    async with SessionLocal() as db:
        u = await db.get(User, user.id)
        u.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    assert (await login(client, user.username, password)).status_code == 200


async def test_successful_login_resets_the_failure_counter(client, make_user):
    user, password = await make_user()
    for _ in range(4):
        await login(client, user.username, "bad-password1")
    assert (await login(client, user.username, password)).status_code == 200
    for _ in range(4):
        assert (await login(client, user.username, "bad-password1")).status_code == 401  # not locked yet


async def test_failures_outside_the_window_do_not_accumulate(client, make_user):
    user, _ = await make_user()
    for _ in range(3):
        await login(client, user.username, "bad-password1")
    async with SessionLocal() as db:
        u = await db.get(User, user.id)
        u.first_failed_at = datetime.now(UTC) - timedelta(minutes=settings.login_window_minutes + 1)
        await db.commit()
    for _ in range(3):
        assert (await login(client, user.username, "bad-password1")).status_code == 401


# ---------------------------------------------------------------- tokens


async def test_me_requires_valid_bearer_token(client, auth):
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    garbage = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nonsense"})
    assert garbage.status_code == 401 and garbage.json()["code"] == "INVALID_TOKEN"

    user, headers = await auth(Role.PARENT)
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200 and resp.json()["username"] == user.username


async def test_expired_token_is_rejected(client, make_user):
    user, _ = await make_user()
    token = jwt.encode(
        {"sub": str(user.id), "role": "admin", "type": "access", "exp": datetime.now(UTC) - timedelta(seconds=5)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_token_stops_working_when_user_is_deactivated(client, auth):
    user, headers = await auth(Role.TEACHER)
    async with SessionLocal() as db:
        (await db.get(User, user.id)).is_active = False
        await db.commit()
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_role_comes_from_the_database_not_the_token(client, make_user):
    """A token that claims role=admin must not grant admin if the DB says teacher."""
    user, password = await make_user(Role.TEACHER)
    from app.core.security import create_access_token

    forged, _ = create_access_token(user.id, "admin")
    resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 403


# --------------------------------------------------------------- refresh


async def test_refresh_rotates_the_token(client, make_user):
    user, password = await make_user()
    first = cookie_value(await login(client, user.username, password), "sms_refresh")

    resp = await client.post("/api/v1/auth/refresh")  # cookie jar carries sms_refresh
    assert resp.status_code == 200 and resp.json()["access_token"]
    second = cookie_value(resp, "sms_refresh")
    assert second and second != first

    third = await client.post("/api/v1/auth/refresh")
    assert third.status_code == 200 and cookie_value(third, "sms_refresh") != second


async def test_refresh_without_cookie_is_401(client):
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401 and resp.json()["code"] == "INVALID_REFRESH_TOKEN"


async def test_failed_refresh_clears_stale_cookies(client):
    """Otherwise the frontend would keep believing it is signed in (role cookie) and loop."""
    client.cookies.set("sms_refresh", "garbage", path="/api/v1/auth")
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401
    cleared = resp.headers.get_list("set-cookie")
    assert any(c.startswith("sms_refresh=") and "Max-Age=0" in c for c in cleared)
    assert any(c.startswith("sms_role=") and "Max-Age=0" in c for c in cleared)
    assert "request_id" in resp.json()


async def test_reusing_a_rotated_token_revokes_the_whole_family(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "refresh_reuse_grace_seconds", 0)
    user, password = await make_user()
    stolen = cookie_value(await login(client, user.username, password), "sms_refresh")
    rotated = cookie_value(await client.post("/api/v1/auth/refresh"), "sms_refresh")

    client.cookies.clear()
    client.cookies.set("sms_refresh", stolen, path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401  # replay detected

    client.cookies.clear()
    client.cookies.set("sms_refresh", rotated, path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401  # legit token revoked too


async def test_reuse_inside_grace_window_is_rejected_but_keeps_the_session(client, make_user):
    """Two tabs refreshing at the same moment must not log the user out."""
    user, password = await make_user()
    old = cookie_value(await login(client, user.username, password), "sms_refresh")
    new = cookie_value(await client.post("/api/v1/auth/refresh"), "sms_refresh")

    client.cookies.clear()
    client.cookies.set("sms_refresh", old, path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401

    client.cookies.clear()
    client.cookies.set("sms_refresh", new, path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200


async def test_expired_refresh_token_is_rejected(client, make_user):
    user, password = await make_user()
    await login(client, user.username, password)
    async with SessionLocal() as db:
        for row in (await db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id))).all():
            row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db.commit()
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_logout_revokes_refresh_token_and_clears_cookies(client, make_user):
    user, password = await make_user()
    raw = cookie_value(await login(client, user.username, password), "sms_refresh")
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 204
    assert any("sms_refresh=" in c and "Max-Age=0" in c for c in resp.headers.get_list("set-cookie"))

    client.cookies.set("sms_refresh", raw, path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_logout_without_session_is_fine(client):
    assert (await client.post("/api/v1/auth/logout")).status_code == 204


# ------------------------------------------------------- change password


async def test_change_password_flow(client, make_user):
    user, password = await make_user()
    login_resp = await login(client, user.username, password)
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}
    old_refresh = cookie_value(login_resp, "sms_refresh")

    wrong = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "nope", "new_password": "Brand-new-1"},
    )
    assert wrong.status_code == 400 and wrong.json()["code"] == "WRONG_PASSWORD"

    weak = await client.post(
        "/api/v1/auth/change-password", headers=headers, json={"current_password": password, "new_password": "short"}
    )
    assert weak.status_code == 422 and weak.json()["code"] == "WEAK_PASSWORD"

    same = await client.post(
        "/api/v1/auth/change-password", headers=headers, json={"current_password": password, "new_password": password}
    )
    assert same.status_code == 422

    ok = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": password, "new_password": "Brand-new-1"},
    )
    assert ok.status_code == 200 and ok.json()["access_token"]

    # old refresh token is dead, old password no longer works, new one does
    client.cookies.clear()
    client.cookies.set("sms_refresh", old_refresh, path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    client.cookies.clear()
    assert (await login(client, user.username, password)).status_code == 401
    assert (await login(client, user.username, "Brand-new-1")).status_code == 200


async def test_must_change_password_blocks_everything_except_me_and_change_password(client, make_user):
    user, password = await make_user(Role.ADMIN, must_change_password=True)
    resp = await login(client, user.username, password)
    assert resp.json()["user"]["must_change_password"] is True
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    blocked = await client.get("/api/v1/users", headers=headers)
    assert blocked.status_code == 403 and blocked.json()["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert (await client.get("/api/v1/settings", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    changed = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": password, "new_password": "Fresh-pass-9"},
    )
    assert changed.status_code == 200 and changed.json()["user"]["must_change_password"] is False
    new_headers = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert (await client.get("/api/v1/users", headers=new_headers)).status_code == 200


async def test_default_test_password_constant_is_valid():
    from app.core.security import validate_password_strength

    assert validate_password_strength(DEFAULT_PASSWORD) == []
