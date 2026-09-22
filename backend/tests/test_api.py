import uuid

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import AuditLog, Role


async def test_health_endpoints(client):
    assert (await client.get("/api/v1/health")).json() == {"status": "ok"}
    assert (await client.get("/api/v1/health/ready")).json() == {"status": "ready"}


async def test_error_shape_is_consistent(client):
    resp = await client.get("/api/v1/nope", headers={"X-Request-ID": "abc123"})
    assert resp.status_code == 404
    err = resp.json()
    assert err["code"] == "NOT_FOUND" and err["request_id"] == "abc123"
    assert resp.headers["x-request-id"] == "abc123"
    assert resp.headers["x-content-type-options"] == "nosniff"


async def test_openapi_docs_available(client):
    assert (await client.get("/docs")).status_code == 200
    assert "/api/v1/auth/login" in (await client.get("/openapi.json")).json()["paths"]


async def test_cors_only_allows_the_frontend_origin(client):
    ok = await client.options(
        "/api/v1/auth/login",
        headers={"Origin": settings.cors_origin_list[0], "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers.get("access-control-allow-origin") == settings.cors_origin_list[0]
    assert ok.headers.get("access-control-allow-credentials") == "true"
    bad = await client.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in bad.headers


# ------------------------------------------------------------ public config


async def test_public_config_hides_demo_accounts_outside_demo_env(client):
    resp = await client.get("/api/v1/public/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["demo_accounts"] is None and "password" not in resp.text.lower()


async def test_public_config_shows_demo_accounts_only_in_demo_env(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "demo")
    body = (await client.get("/api/v1/public/config")).json()
    assert {a["role"] for a in body["demo_accounts"]} == {r.value for r in Role}
    assert all(a["password"] for a in body["demo_accounts"])


# ------------------------------------------------------------------- users


async def test_users_list_is_paginated_searchable_and_filterable(client, auth, make_user):
    _, headers = await auth(Role.ADMIN)
    tag = uuid.uuid4().hex[:8]
    for i in range(3):
        await make_user(Role.TEACHER, username=f"{tag}-t{i}", full_name=f"Zed {tag} {i}")
    await make_user(Role.STUDENT, username=f"{tag}-s0", full_name="Someone Else")

    page1 = (await client.get("/api/v1/users", headers=headers, params={"q": tag, "page_size": 2})).json()
    assert page1["total"] == 4 and page1["pages"] == 2 and len(page1["items"]) == 2 and page1["page"] == 1
    page2 = (await client.get("/api/v1/users", headers=headers, params={"q": tag, "page_size": 2, "page": 2})).json()
    assert len(page2["items"]) == 2
    assert not {u["id"] for u in page1["items"]} & {u["id"] for u in page2["items"]}

    teachers = (await client.get("/api/v1/users", headers=headers, params={"q": tag, "role": "teacher"})).json()
    assert teachers["total"] == 3 and all(u["role"] == "teacher" for u in teachers["items"])

    by_name = (await client.get("/api/v1/users", headers=headers, params={"q": "someone else"})).json()
    assert [u["username"] for u in by_name["items"]] == [f"{tag}-s0"]
    assert "password_hash" not in str(page1)


async def test_users_search_treats_like_wildcards_literally(client, auth):
    _, headers = await auth(Role.ADMIN)
    resp = await client.get("/api/v1/users", headers=headers, params={"q": "%"})
    assert resp.json()["total"] == 0


async def test_pagination_bounds_are_enforced(client, auth):
    _, headers = await auth(Role.ADMIN)
    for params in ({"page_size": 101}, {"page_size": 0}, {"page": 0}):
        assert (await client.get("/api/v1/users", headers=headers, params=params)).status_code == 422


# ---------------------------------------------------------------- settings


async def test_settings_update_validates_and_writes_audit_log(client, auth):
    admin, headers = await auth(Role.ADMIN)
    resp = await client.put(
        "/api/v1/settings",
        headers=headers,
        json={
            "name": "Test Academy",
            "fee_due_day": 15,
            "late_fine_amount": "250.50",
            "email": "hi@school.example.com",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Test Academy" and body["fee_due_day"] == 15 and body["late_fine_amount"] == "250.50"

    again = (await client.get("/api/v1/settings", headers=headers)).json()
    assert again["name"] == "Test Academy"

    async with SessionLocal() as db:
        log = await db.scalar(
            select(AuditLog).where(AuditLog.user_id == admin.id, AuditLog.entity == "school_settings")
        )
    assert log and log.action == "update" and log.diff["name"]["new"] == "Test Academy"


async def test_settings_update_rejects_bad_input(client, auth):
    _, headers = await auth(Role.ADMIN)
    for bad in (
        {"fee_due_day": 40},
        {"fee_due_day": 0},
        {"late_fine_amount": "-5"},
        {"email": "not-an-email"},
        {"unknown_field": 1},
        {"name": "x"},
    ):
        resp = await client.put("/api/v1/settings", headers=headers, json=bad)
        assert resp.status_code == 422, bad


async def test_late_fine_uses_decimal_not_float(client, auth):
    _, headers = await auth(Role.ADMIN)
    await client.put("/api/v1/settings", headers=headers, json={"late_fine_amount": "0.10"})
    assert (await client.get("/api/v1/settings", headers=headers)).json()["late_fine_amount"] == "0.10"
