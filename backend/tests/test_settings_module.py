import uuid

import pytest
from sqlalchemy import func, select, update

from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models import AcademicYear, AuditLog, Role, User
from app.services import users as user_svc
from tests.conftest import DEFAULT_PASSWORD, login
from tests.helpers import create_student, create_teacher, make_school, tag

API = "/api/v1"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200


# ---------------------------------------------------------- academic years
async def test_academic_year_crud_and_single_current(client, auth):
    _, h = await auth(Role.ADMIN)
    a = await client.post(
        f"{API}/academic-years",
        headers=h,
        json={"label": f"A{tag()}", "start_date": "2030-04-01", "end_date": "2031-03-31"},
    )
    assert a.status_code == 201 and a.json()["is_current"] is False
    b = await client.post(
        f"{API}/academic-years",
        headers=h,
        json={"label": f"B{tag()}", "start_date": "2031-04-01", "end_date": "2032-03-31"},
    )
    a_id, b_id = a.json()["id"], b.json()["id"]

    assert (await client.post(f"{API}/academic-years/{a_id}/set-current", headers=h)).json()["is_current"] is True
    assert (await client.post(f"{API}/academic-years/{b_id}/set-current", headers=h)).json()["is_current"] is True
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).where(AcademicYear.is_current.is_(True))) == 1
        assert (await db.get(AcademicYear, uuid.UUID(b_id))).is_current

    upd = await client.put(
        f"{API}/academic-years/{a_id}",
        headers=h,
        json={"label": f"A2{tag()}", "start_date": "2030-05-01", "end_date": "2031-04-30"},
    )
    assert upd.status_code == 200 and upd.json()["start_date"] == "2030-05-01"

    listing = (await client.get(f"{API}/academic-years", headers=h, params={"page_size": 100})).json()
    assert {"items", "total", "page", "page_size", "pages"} <= listing.keys()


async def test_academic_year_validation_and_duplicates(client, auth):
    _, h = await auth(Role.ADMIN)
    label = f"D{tag()}"
    body = {"label": label, "start_date": "2040-04-01", "end_date": "2041-03-31"}
    assert (await client.post(f"{API}/academic-years", headers=h, json=body)).status_code == 201
    dup = await client.post(f"{API}/academic-years", headers=h, json=body)
    assert dup.status_code == 409 and "label" in dup.json()["fields"]
    bad = await client.post(
        f"{API}/academic-years", headers=h, json={**body, "label": f"E{tag()}", "end_date": "2040-01-01"}
    )
    assert bad.status_code == 422 and "end_date" in bad.json()["fields"]


# ------------------------------------------------------- classes & sections
async def test_class_section_subject_crud(client, auth):
    _, h = await auth(Role.ADMIN)
    name = f"KG-{tag()}"
    c = await client.post(f"{API}/classes", headers=h, json={"name": name, "order": 3})
    assert c.status_code == 201 and c.json()["order"] == 3 and c.json()["student_count"] == 0
    cid = c.json()["id"]
    assert (await client.post(f"{API}/classes", headers=h, json={"name": name})).status_code == 409

    assert (await client.put(f"{API}/classes/{cid}", headers=h, json={"name": name + "x", "order": 1})).json()[
        "order"
    ] == 1

    s = await client.post(f"{API}/classes/{cid}/sections", headers=h, json={"name": "A"})
    assert s.status_code == 201
    assert (await client.post(f"{API}/classes/{cid}/sections", headers=h, json={"name": "A"})).status_code == 409
    sections = (await client.get(f"{API}/classes/{cid}/sections", headers=h)).json()
    assert sections["total"] == 1 and sections["items"][0]["student_count"] == 0
    assert (await client.put(f"{API}/sections/{s.json()['id']}", headers=h, json={"name": "B"})).json()["name"] == "B"
    assert (await client.delete(f"{API}/sections/{s.json()['id']}", headers=h)).status_code == 204

    sub = await client.post(f"{API}/subjects", headers=h, json={"name": f"Art-{tag()}"})
    assert sub.status_code == 201
    assert (await client.delete(f"{API}/subjects/{sub.json()['id']}", headers=h)).status_code == 204
    assert (await client.delete(f"{API}/classes/{cid}", headers=h)).status_code == 204
    assert (await client.delete(f"{API}/classes/{cid}", headers=h)).status_code == 404


async def test_classes_sort_by_order_field(client, auth):
    _, h = await auth(Role.ADMIN)
    t = tag()
    for name, order in ((f"Z-{t}", 1), (f"M-{t}", 2), (f"A-{t}", 3)):
        await client.post(f"{API}/classes", headers=h, json={"name": name, "order": order})
    items = (await client.get(f"{API}/classes", headers=h, params={"q": t})).json()["items"]
    assert [i["name"] for i in items] == [f"Z-{t}", f"M-{t}", f"A-{t}"]


async def test_cannot_delete_class_or_section_with_students(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    await create_student(school)

    resp = await client.delete(f"{API}/classes/{school.klass.id}", headers=h)
    assert resp.status_code == 409 and resp.json()["code"] == "CLASS_HAS_STUDENTS"
    assert "1 student" in resp.json()["detail"] and "rename" in resp.json()["detail"]

    resp = await client.delete(f"{API}/sections/{school.sec_a.id}", headers=h)
    assert resp.status_code == 409 and resp.json()["code"] == "SECTION_HAS_STUDENTS"
    # the empty section is fine
    assert (await client.delete(f"{API}/sections/{school.sec_b.id}", headers=h)).status_code == 204

    classes = (await client.get(f"{API}/classes", headers=h, params={"q": school.klass.name})).json()["items"]
    assert classes[0]["student_count"] == 1
    sec = (await client.get(f"{API}/classes/{school.klass.id}/sections", headers=h)).json()["items"]
    assert sec[0]["name"] == "A" and sec[0]["student_count"] == 1


async def test_cannot_delete_subject_used_by_a_class(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    resp = await client.delete(f"{API}/subjects/{school.math.id}", headers=h)
    assert resp.status_code == 409 and resp.json()["code"] == "SUBJECT_IN_USE"


# ------------------------------------------------------------ class subjects
async def test_class_subjects_replace_and_validation(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    url = f"{API}/classes/{school.klass.id}/subjects"
    current = (await client.get(url, headers=h)).json()
    assert len(current) == 2 and {i["total_marks"] for i in current} == {"100.00"}

    ok = await client.put(
        url, headers=h, json=[{"subject_id": str(school.math.id), "total_marks": "50", "passing_marks": "20"}]
    )
    assert ok.status_code == 200 and len(ok.json()) == 1 and ok.json()[0]["total_marks"] == "50.00"

    bad = await client.put(
        url, headers=h, json=[{"subject_id": str(school.math.id), "total_marks": "50", "passing_marks": "60"}]
    )
    assert bad.status_code == 422 and "0.passing_marks" in bad.json()["fields"]  # list bodies are index-prefixed
    dup = await client.put(
        url, headers=h, json=[{"subject_id": str(school.math.id), "total_marks": "50", "passing_marks": "20"}] * 2
    )
    assert dup.status_code == 422
    unknown = await client.put(
        url, headers=h, json=[{"subject_id": str(uuid.uuid4()), "total_marks": "50", "passing_marks": "20"}]
    )
    assert unknown.status_code == 422


async def test_class_subject_cannot_be_removed_while_a_teacher_teaches_it(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    await create_teacher(school)  # assigned to math in this class
    resp = await client.put(
        f"{API}/classes/{school.klass.id}/subjects",
        headers=h,
        json=[{"subject_id": str(school.english.id), "total_marks": "100", "passing_marks": "40"}],
    )
    assert resp.status_code == 409 and resp.json()["code"] == "SUBJECT_HAS_TEACHERS"


# ---------------------------------------------------------------- fee rules
async def test_fee_structures_and_school_rules(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school(fee=None)
    listing = {i["class_id"]: i for i in (await client.get(f"{API}/fee-structures", headers=h)).json()}
    assert listing[str(school.klass.id)]["monthly_fee"] == "0.00"

    put = await client.put(
        f"{API}/fee-structures", headers=h, json=[{"class_id": str(school.klass.id), "monthly_fee": "2500.50"}]
    )
    assert put.status_code == 200
    assert {i["class_id"]: i for i in put.json()}[str(school.klass.id)]["monthly_fee"] == "2500.50"
    assert (
        await client.put(
            f"{API}/fee-structures", headers=h, json=[{"class_id": str(school.klass.id), "monthly_fee": "-1"}]
        )
    ).status_code == 422
    assert (
        await client.put(f"{API}/fee-structures", headers=h, json=[{"class_id": str(uuid.uuid4()), "monthly_fee": "1"}])
    ).status_code == 422

    rules = await client.put(f"{API}/settings", headers=h, json={"fee_due_day": 5, "late_fine_amount": "150"})
    assert rules.json()["fee_due_day"] == 5
    await client.put(f"{API}/settings", headers=h, json={"fee_due_day": 10})


async def test_logo_upload_validates_real_content(client, auth):
    _, h = await auth(Role.ADMIN)
    ok = await client.post(f"{API}/settings/logo", headers=h, files={"file": ("logo.png", JPEG, "image/png")})
    assert ok.status_code == 200 and ok.json()["logo_url"].endswith(".jpg")  # type comes from the bytes, not the name
    assert (await client.get(ok.json()["logo_url"])).status_code == 200
    fake = await client.post(
        f"{API}/settings/logo", headers=h, files={"file": ("logo.png", b"<html>hi</html>", "image/png")}
    )
    assert fake.status_code == 422 and fake.json()["fields"]["file"]
    assert (await client.get(f"{API}/settings", headers=h)).json()["logo_url"] == ok.json()["logo_url"]


# ------------------------------------------------------------ user accounts
async def test_activate_deactivate_and_sessions_end(client, auth, make_user):
    admin, h = await auth(Role.ADMIN)
    target, pw = await make_user(Role.TEACHER)
    assert (await login(client, target.username, pw)).status_code == 200

    off = await client.put(f"{API}/users/{target.id}/deactivate", headers=h)
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert (await login(client, target.username, pw)).status_code == 403  # ACCOUNT_DISABLED
    on = await client.put(f"{API}/users/{target.id}/activate", headers=h)
    assert on.json()["is_active"] is True
    assert (await login(client, target.username, pw)).status_code == 200

    async with SessionLocal() as db:
        actions = set(
            (
                await db.scalars(
                    select(AuditLog.action).where(AuditLog.entity == "user", AuditLog.entity_id == str(target.id))
                )
            ).all()
        )
    assert {"deactivate", "activate"} <= actions


async def test_admin_cannot_deactivate_own_account(client, auth):
    admin, h = await auth(Role.ADMIN)
    resp = await client.put(f"{API}/users/{admin.id}/deactivate", headers=h)
    assert resp.status_code == 409 and resp.json()["code"] == "CANNOT_DEACTIVATE_SELF"


async def test_last_active_admin_cannot_be_deactivated(make_user):
    """Rule enforced in the service, even for a request from another (already deactivated) admin."""
    sole, _ = await make_user(Role.ADMIN)
    actor, _ = await make_user(Role.ADMIN)
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.role == Role.ADMIN, User.id != sole.id).values(is_active=False))
        await db.commit()
    async with SessionLocal() as db:
        with pytest.raises(AppError) as exc:
            await user_svc.set_user_active(db, actor, sole.id, False)
    assert exc.value.code == "LAST_ADMIN" and exc.value.status_code == 409
    async with SessionLocal() as db:
        assert (await db.get(User, sole.id)).is_active


async def test_reset_password_invalidates_old_password_and_forces_change(client, auth, make_user):
    admin, h = await auth(Role.ADMIN)
    target, old_pw = await make_user(Role.PARENT)
    first = await login(client, target.username, old_pw)
    old_refresh = first.headers.get_list("set-cookie")
    assert first.status_code == 200 and old_refresh

    reset = await client.post(f"{API}/users/{target.id}/reset-password", headers=h)
    body = reset.json()
    assert reset.status_code == 200 and body["username"] == target.username and len(body["temp_password"]) == 10
    assert body["must_change_password"] is True

    client.cookies.clear()
    assert (await login(client, target.username, old_pw)).status_code == 401  # old password is dead
    assert (await client.post(f"{API}/auth/refresh")).status_code == 401  # old sessions are dead too
    new = await login(client, target.username, body["temp_password"])
    assert new.status_code == 200 and new.json()["user"]["must_change_password"] is True
    blocked = await client.get(
        f"{API}/parent/children", headers={"Authorization": f"Bearer {new.json()['access_token']}"}
    )
    assert blocked.status_code == 403 and blocked.json()["code"] == "PASSWORD_CHANGE_REQUIRED"

    async with SessionLocal() as db:
        log = await db.scalar(
            select(AuditLog).where(AuditLog.action == "reset_password", AuditLog.entity_id == str(target.id))
        )
    assert log is not None and body["temp_password"] not in str(log.diff)  # the password is never logged


async def test_default_page_size_is_ten(client, auth):
    _, h = await auth(Role.ADMIN)
    assert (await client.get(f"{API}/users", headers=h)).json()["page_size"] == 10


_ = DEFAULT_PASSWORD
