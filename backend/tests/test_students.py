import asyncio
import re
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from app.db.session import SessionLocal
from app.models import (
    AuditLog,
    Counter,
    FeeLedger,
    Guardian,
    Role,
    Student,
    StudentGuardian,
    User,
)
from app.models.enums import FeeStatus
from app.schemas.students import StudentCreate
from app.services import students as student_svc
from app.services.fees import academic_year_months
from tests.conftest import DEFAULT_PASSWORD, login
from tests.helpers import make_school, rand_cnic, rand_phone, student_payload, tag

API = "/api/v1"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 300
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 300


async def register(client, headers, school, **overrides):
    resp = await client.post(f"{API}/students", headers=headers, json=student_payload(school, **overrides))
    assert resp.status_code == 201, resp.text
    return resp.json()


# ------------------------------------------------------------- registration
async def test_registration_creates_student_guardian_parent_user_and_ledger(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    body = await register(client, h, school)

    student = body["student"]
    assert re.fullmatch(rf"{date.today().year}-\d{{4,}}", student["roll_no"])
    assert student["status"] == "active" and student["class_name"] == school.klass.name
    assert student["section_name"] == "A" and student["guardian"]["father_cnic"]

    parent = body["credentials"]["parent"]
    assert parent["username"] == student["guardian"]["father_phone"]  # normalized 03XX-XXXXXXX
    assert len(parent["temp_password"]) == 10 and body["credentials"]["student"] is None

    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == parent["username"]))
        assert user.role == Role.PARENT and user.must_change_password is True
        assert user.password_hash.startswith("$argon2") and parent["temp_password"] not in user.password_hash
        assert (
            await db.scalar(
                select(func.count()).select_from(FeeLedger).where(FeeLedger.student_id == uuid.UUID(student["id"]))
            )
            == 12
        )
        assert await db.scalar(
            select(AuditLog.id).where(
                AuditLog.entity == "student", AuditLog.entity_id == student["id"], AuditLog.action == "create"
            )
        )


async def test_credentials_are_only_in_the_registration_response(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    body = await register(client, h, school)
    sid = body["student"]["id"]
    for path in (f"/students/{sid}", "/students?page_size=100"):
        assert "temp_password" not in (await client.get(API + path, headers=h)).text


async def test_ledger_has_12_months_correct_due_dates_and_discount_math(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school(fee="2000")
    body = await register(client, h, school, discount_percent="50")
    ledger = (await client.get(f"{API}/students/{body['student']['id']}/ledger", headers=h)).json()

    items = ledger["items"]
    assert len(items) == 12
    expected_months = academic_year_months(school.year.start_date)
    assert [i["month"] for i in items] == [m.isoformat() for m in expected_months]
    for item, month in zip(items, expected_months, strict=True):
        assert item["due_date"] == month.replace(day=10).isoformat()
        assert item["base_fee"] == "2000.00" and item["discount"] == "1000.00"
        assert item["total_payable"] == "1000.00" and item["fine"] == "0.00"
        assert item["status"] == "unpaid" and item["paid_amount"] == "0.00"
    assert ledger["totals"] == {"total_payable": "12000.00", "paid_amount": "0.00", "balance": "12000.00"}
    assert body["student"]["discount_percent"] == "50.00"


async def test_no_fee_structure_creates_zero_rows_and_warns(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school(fee=None)
    body = await register(client, h, school)
    assert body["warnings"] and "fee" in body["warnings"][0].lower()
    ledger = (await client.get(f"{API}/students/{body['student']['id']}/ledger", headers=h)).json()
    assert len(ledger["items"]) == 12 and {i["base_fee"] for i in ledger["items"]} == {"0.00"}


async def test_student_login_is_optional_and_uses_the_roll_number(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    body = await register(client, h, school, create_student_login=True)
    cred = body["credentials"]["student"]
    assert cred["username"] == body["student"]["roll_no"].lower() and body["student"]["has_login"] is True
    resp = await login(client, cred["username"], cred["temp_password"])
    assert resp.status_code == 200 and resp.json()["user"]["role"] == "student"
    assert resp.json()["user"]["must_change_password"] is True


async def test_sibling_shares_guardian_and_parent_account(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    cnic, phone = rand_cnic(), rand_phone()
    guardian = {"father_cnic": cnic, "father_phone": phone}
    first = await register(client, h, school, guardian=guardian)
    second = await register(client, h, school, guardian={**guardian, "father_name": "Ignored Name"})

    assert first["credentials"]["parent"] is not None
    assert second["credentials"]["parent"] is None  # no second account, no new password
    assert first["student"]["guardian"]["id"] == second["student"]["guardian"]["id"]
    assert second["student"]["guardian"]["father_name"] == first["student"]["guardian"]["father_name"]

    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(Guardian).where(Guardian.father_cnic == cnic)) == 1
        assert await db.scalar(select(func.count()).select_from(User).where(User.username == phone)) == 1
        g_id = uuid.UUID(first["student"]["guardian"]["id"])
        assert (
            await db.scalar(
                select(func.count()).select_from(StudentGuardian).where(StudentGuardian.guardian_id == g_id)
            )
            == 2
        )


async def test_duplicate_student_is_rejected_with_existing_roll_no(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    first = await register(client, h, school)
    g = first["student"]["guardian"]
    again = await client.post(
        f"{API}/students",
        headers=h,
        json=student_payload(
            school,
            full_name=first["student"]["full_name"].upper(),
            dob=first["student"]["dob"],
            guardian={"father_cnic": g["father_cnic"], "father_phone": g["father_phone"]},
        ),
    )
    assert again.status_code == 409 and again.json()["code"] == "DUPLICATE_STUDENT"
    assert first["student"]["roll_no"] in again.json()["detail"]
    assert again.json()["details"]["roll_no"] == first["student"]["roll_no"]


async def test_same_phone_under_a_different_cnic_is_rejected_cleanly(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    first = await register(client, h, school)
    phone = first["student"]["guardian"]["father_phone"]
    resp = await client.post(
        f"{API}/students", headers=h, json=student_payload(school, guardian={"father_phone": phone})
    )
    assert resp.status_code == 409 and resp.json()["code"] == "PHONE_ALREADY_USED"
    assert "guardian.father_phone" in resp.json()["fields"]


async def test_registration_validation_reports_field_level_errors(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    bad = student_payload(school, dob="2030-01-01", blood_group="Z+", emergency_phone="123")
    bad["guardian"]["father_cnic"] = "12345"
    bad["guardian"]["father_phone"] = "0200-1234567"
    resp = await client.post(f"{API}/students", headers=h, json=bad)
    assert resp.status_code == 422 and resp.json()["code"] == "VALIDATION_ERROR"
    fields = resp.json()["fields"]
    assert {"dob", "blood_group", "emergency_phone", "guardian.father_cnic", "guardian.father_phone"} <= fields.keys()
    assert "12345" not in resp.text  # input is never echoed back


async def test_class_and_section_rules(client, auth):
    _, h = await auth(Role.ADMIN)
    school, other = await make_school(), await make_school()
    # section from another class
    r = await client.post(f"{API}/students", headers=h, json=student_payload(school, section_id=str(other.sec_a.id)))
    assert r.status_code == 422 and "section_id" in r.json()["fields"]
    # class has sections, so one is required
    r = await client.post(f"{API}/students", headers=h, json=student_payload(school, section_id=None))
    assert r.status_code == 422 and "section_id" in r.json()["fields"]
    r = await client.post(f"{API}/students", headers=h, json=student_payload(school, class_id=str(uuid.uuid4())))
    assert r.status_code == 422 and "class_id" in r.json()["fields"]


async def test_unknown_or_immutable_fields_are_rejected(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    resp = await client.post(f"{API}/students", headers=h, json=student_payload(school, roll_no="2026-9999"))
    assert resp.status_code == 422 and "roll_no" in resp.json()["fields"]


# ----------------------------------------------- transaction & concurrency
async def test_fifty_concurrent_registrations_get_unique_roll_numbers():
    school = await make_school()

    async def one():
        payload = StudentCreate(**student_payload(school))
        async with SessionLocal() as db:
            return (await student_svc.register_student(db, payload, None)).student.roll_no

    roll_numbers = await asyncio.gather(*[one() for _ in range(50)])
    assert len(set(roll_numbers)) == 50
    assert all(re.fullmatch(rf"{date.today().year}-\d{{4,}}", r) for r in roll_numbers)
    numbers = sorted(int(r.split("-")[1]) for r in roll_numbers)
    assert numbers == list(range(numbers[0], numbers[0] + 50))  # no gaps, no duplicates


async def test_error_at_ledger_step_rolls_everything_back(monkeypatch):
    school = await make_school()
    payload = StudentCreate(**student_payload(school, create_student_login=True))
    cnic, phone, name = payload.guardian.father_cnic, payload.guardian.father_phone, payload.full_name
    year = date.today().year

    async with SessionLocal() as db:
        counter_before = await db.scalar(
            select(Counter.last_value).where(Counter.key == "roll_no", Counter.year == year)
        )

    async def boom(*args, **kwargs):
        raise RuntimeError("ledger generation failed")

    monkeypatch.setattr(student_svc, "generate_fee_ledger", boom)
    async with SessionLocal() as db:
        with pytest.raises(RuntimeError):
            await student_svc.register_student(db, payload, None)

    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(Guardian).where(Guardian.father_cnic == cnic)) == 0
        assert await db.scalar(select(func.count()).select_from(User).where(User.username == phone)) == 0
        assert await db.scalar(select(func.count()).select_from(Student).where(Student.full_name == name)) == 0
        assert (
            await db.scalar(select(func.count()).select_from(User).where(User.full_name == name)) == 0
        )  # student login too
        counter_after = await db.scalar(
            select(Counter.last_value).where(Counter.key == "roll_no", Counter.year == year)
        )
    assert counter_after == counter_before  # the roll number was not burned


async def test_concurrent_siblings_end_up_with_one_guardian_and_one_parent_user():
    school = await make_school()
    cnic, phone = rand_cnic(), rand_phone()

    async def one():
        payload = StudentCreate(**student_payload(school, guardian={"father_cnic": cnic, "father_phone": phone}))
        async with SessionLocal() as db:
            return await student_svc.register_student(db, payload, None)

    results = await asyncio.gather(*[one() for _ in range(6)])
    assert sum(1 for r in results if r.parent_credential) == 1  # exactly one parent account was issued
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(Guardian).where(Guardian.father_cnic == cnic)) == 1
        assert await db.scalar(select(func.count()).select_from(User).where(User.username == phone)) == 1


# --------------------------------------------- parent's first login (spec DoD)
async def test_parent_first_login_forces_password_change_then_sees_both_children(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    guardian = {"father_cnic": rand_cnic(), "father_phone": rand_phone()}
    first = await register(client, h, school, guardian=guardian, full_name="Older Child", dob="2012-01-01")
    await register(client, h, school, guardian=guardian, full_name="Younger Child", dob="2016-01-01")
    cred = first["credentials"]["parent"]

    resp = await login(client, cred["username"], cred["temp_password"])
    assert resp.json()["user"]["must_change_password"] is True
    ph = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    assert (await client.get(f"{API}/parent/children", headers=ph)).json()["code"] == "PASSWORD_CHANGE_REQUIRED"

    changed = await client.post(
        f"{API}/auth/change-password",
        headers=ph,
        json={"current_password": cred["temp_password"], "new_password": "Brand-new-77"},
    )
    assert changed.status_code == 200
    ph = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    kids = (await client.get(f"{API}/parent/children", headers=ph)).json()
    assert [k["full_name"] for k in kids["items"]] == ["Older Child", "Younger Child"] and kids["total"] == 2


# ----------------------------------------------------------- list & profile
async def test_student_list_search_filters_sorting_and_pagination(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    t = tag()
    names = [f"Charlie {t}", f"Alice {t}", f"Bob {t}"]
    for i, name in enumerate(names):
        await register(client, h, school, full_name=name, section_id=str((school.sec_a if i < 2 else school.sec_b).id))

    base = {"class_id": str(school.klass.id)}
    everyone = (await client.get(f"{API}/students", headers=h, params={**base, "page_size": 100})).json()
    assert everyone["total"] == 3 and everyone["page_size"] == 100
    by_name = (await client.get(f"{API}/students", headers=h, params={**base, "sort": "name"})).json()["items"]
    assert [s["full_name"] for s in by_name] == [f"Alice {t}", f"Bob {t}", f"Charlie {t}"]
    by_roll = (await client.get(f"{API}/students", headers=h, params={**base, "sort": "roll_no"})).json()["items"]
    assert [s["full_name"] for s in by_roll] == names  # registration order
    by_class = (await client.get(f"{API}/students", headers=h, params={**base, "sort": "class"})).json()["items"]
    assert [s["section_name"] for s in by_class] == ["A", "A", "B"]

    only_b = (
        await client.get(f"{API}/students", headers=h, params={**base, "section_id": str(school.sec_b.id)})
    ).json()
    assert only_b["total"] == 1 and only_b["items"][0]["full_name"] == f"Bob {t}"
    by_q = (await client.get(f"{API}/students", headers=h, params={"q": f"alice {t}"})).json()
    assert by_q["total"] == 1
    father = by_q["items"][0]["father_name"]
    assert (await client.get(f"{API}/students", headers=h, params={"q": father})).json()["total"] == 1
    roll = by_q["items"][0]["roll_no"]
    assert (await client.get(f"{API}/students", headers=h, params={"q": roll})).json()["total"] >= 1

    p1 = (await client.get(f"{API}/students", headers=h, params={**base, "page_size": 2})).json()
    p2 = (await client.get(f"{API}/students", headers=h, params={**base, "page_size": 2, "page": 2})).json()
    assert (p1["pages"], len(p1["items"]), len(p2["items"])) == (2, 2, 1)
    assert (await client.get(f"{API}/students", headers=h, params={"sort": "bogus"})).status_code == 422
    assert (await client.get(f"{API}/students", headers=h, params={"q": "%"})).json()["total"] == 0


async def test_guardian_lookup_for_the_registration_form(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    body = await register(client, h, school, full_name="Sibling One")
    cnic = body["student"]["guardian"]["father_cnic"]
    found = (await client.get(f"{API}/students/guardian-lookup", headers=h, params={"father_cnic": cnic})).json()
    assert found["found"] is True and found["children"] == ["Sibling One"]
    assert found["guardian"]["father_name"] == body["student"]["guardian"]["father_name"]
    missing = (
        await client.get(f"{API}/students/guardian-lookup", headers=h, params={"father_cnic": rand_cnic()})
    ).json()
    assert missing == {"found": False, "guardian": None, "children": []}
    assert (
        await client.get(f"{API}/students/guardian-lookup", headers=h, params={"father_cnic": "bad"})
    ).status_code == 422


# --------------------------------------------------------------------- edit
async def test_edit_student_roll_no_is_immutable_and_changes_are_audited(client, auth):
    admin, h = await auth(Role.ADMIN)
    school = await make_school()
    body = await register(client, h, school)
    sid, roll = body["student"]["id"], body["student"]["roll_no"]

    bad = await client.put(f"{API}/students/{sid}", headers=h, json={"roll_no": "2099-0001"})
    assert bad.status_code == 422 and "roll_no" in bad.json()["fields"]

    ok = await client.put(
        f"{API}/students/{sid}",
        headers=h,
        json={"city": "Lahore", "section_id": str(school.sec_b.id), "guardian": {"father_occupation": "Engineer"}},
    )
    assert ok.status_code == 200
    got = ok.json()
    assert got["roll_no"] == roll and got["city"] == "Lahore" and got["section_name"] == "B"
    assert got["guardian"]["father_occupation"] == "Engineer"
    assert got["guardian"]["father_cnic"] == body["student"]["guardian"]["father_cnic"]  # identity key untouched

    cnic_change = await client.put(f"{API}/students/{sid}", headers=h, json={"guardian": {"father_cnic": rand_cnic()}})
    assert cnic_change.status_code == 422

    async with SessionLocal() as db:
        log = await db.scalar(
            select(AuditLog).where(AuditLog.entity_id == sid, AuditLog.action == "update", AuditLog.user_id == admin.id)
        )
    assert log and log.diff["city"]["new"] == "Lahore" and "guardian.father_occupation" in log.diff


async def test_moving_to_a_class_requires_a_valid_section(client, auth):
    _, h = await auth(Role.ADMIN)
    school, other = await make_school(), await make_school()
    sid = (await register(client, h, school))["student"]["id"]
    r = await client.put(f"{API}/students/{sid}", headers=h, json={"class_id": str(other.klass.id)})
    assert r.status_code == 422 and "section_id" in r.json()["fields"]  # old section belongs to the old class
    ok = await client.put(
        f"{API}/students/{sid}", headers=h, json={"class_id": str(other.klass.id), "section_id": str(other.sec_b.id)}
    )
    assert ok.status_code == 200 and ok.json()["class_name"] == other.klass.name


async def test_status_change_requires_reason_for_expelled(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    sid = (await register(client, h, school))["student"]["id"]
    no_reason = await client.put(f"{API}/students/{sid}/status", headers=h, json={"status": "expelled"})
    assert no_reason.status_code == 422 and "reason" in no_reason.json()["fields"]
    ok = await client.put(
        f"{API}/students/{sid}/status", headers=h, json={"status": "expelled", "reason": "Repeated violations"}
    )
    assert ok.json()["status"] == "expelled" and ok.json()["status_reason"] == "Repeated violations"
    assert (await client.put(f"{API}/students/{sid}/status", headers=h, json={"status": "graduated"})).json()[
        "status"
    ] == "graduated"
    assert (
        await client.put(f"{API}/students/{sid}/status", headers=h, json={"status": "transferred"})
    ).status_code == 422
    listed = (
        await client.get(f"{API}/students", headers=h, params={"class_id": str(school.klass.id), "status": "graduated"})
    ).json()
    assert listed["total"] == 1


async def test_discount_change_recalculates_only_unpaid_rows(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school(fee="2000")
    sid = (await register(client, h, school))["student"]["id"]
    items = (await client.get(f"{API}/students/{sid}/ledger", headers=h)).json()["items"]
    async with SessionLocal() as db:  # simulate Phase 4 payments: one paid month, one partial month
        await db.execute(
            update(FeeLedger)
            .where(FeeLedger.id == uuid.UUID(items[0]["id"]))
            .values(status=FeeStatus.PAID, paid_amount=Decimal("2000"))
        )
        await db.execute(
            update(FeeLedger)
            .where(FeeLedger.id == uuid.UUID(items[1]["id"]))
            .values(status=FeeStatus.PARTIAL, paid_amount=Decimal("500"))
        )
        await db.commit()

    resp = await client.put(f"{API}/students/{sid}/discount", headers=h, json={"discount_percent": "25"})
    assert resp.status_code == 200 and resp.json() == {"discount_percent": "25.00", "recalculated_rows": 10}

    after = (await client.get(f"{API}/students/{sid}/ledger", headers=h)).json()["items"]
    for row in after[:2]:  # paid + partial rows are history: untouched
        assert (row["discount"], row["total_payable"]) == ("0.00", "2000.00")
    for row in after[2:]:
        assert (row["discount"], row["total_payable"]) == ("500.00", "1500.00")
    assert (await client.get(f"{API}/students/{sid}", headers=h)).json()["discount_percent"] == "25.00"
    for bad in ("101", "-1", "abc"):
        assert (
            await client.put(f"{API}/students/{sid}/discount", headers=h, json={"discount_percent": bad})
        ).status_code == 422


async def test_soft_delete_hides_student_and_deactivates_login(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    body = await register(client, h, school, create_student_login=True)
    sid, cred = body["student"]["id"], body["credentials"]["student"]

    assert (await client.delete(f"{API}/students/{sid}", headers=h)).status_code == 204
    assert (await client.get(f"{API}/students/{sid}", headers=h)).status_code == 404
    listed = (await client.get(f"{API}/students", headers=h, params={"class_id": str(school.klass.id)})).json()
    assert listed["total"] == 0
    assert (await login(client, cred["username"], cred["temp_password"])).status_code == 403
    async with SessionLocal() as db:
        row = await db.get(Student, uuid.UUID(sid))
        assert row.is_deleted is True and row.status.value == "active"  # status is left as it was
    # the same student can be registered again after removal
    again = await client.post(
        f"{API}/students",
        headers=h,
        json=student_payload(
            school,
            full_name=body["student"]["full_name"],
            dob=body["student"]["dob"],
            guardian={
                "father_cnic": body["student"]["guardian"]["father_cnic"],
                "father_phone": body["student"]["guardian"]["father_phone"],
            },
        ),
    )
    assert again.status_code == 201


# -------------------------------------------------------------------- photo
async def test_photo_upload_checks_content_size_and_renames(client, auth, tmp_path):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    sid = (await register(client, h, school))["student"]["id"]
    url = f"{API}/students/{sid}/photo"

    ok = await client.post(url, headers=h, files={"file": ("my holiday.jpeg", JPEG, "image/jpeg")})
    assert ok.status_code == 200
    photo = ok.json()["photo_url"]
    assert re.fullmatch(r"/api/v1/uploads/photos/[0-9a-f]{32}\.jpg", photo)  # random name, not "my holiday"
    served = await client.get(photo)
    assert (
        served.status_code == 200 and served.content == JPEG and served.headers["x-content-type-options"] == "nosniff"
    )

    png = await client.post(url, headers=h, files={"file": ("x.png", PNG, "image/png")})
    assert png.status_code == 200 and png.json()["photo_url"].endswith(".png")
    assert (await client.get(photo)).status_code == 404  # the replaced file was removed

    # extension and Content-Type lie: the bytes decide
    for name, data, ctype in (
        ("a.jpg", b"<script>alert(1)</script>", "image/jpeg"),
        ("b.png", b"GIF89a....", "image/png"),
        ("c.jpg", b"", "image/jpeg"),
    ):
        bad = await client.post(url, headers=h, files={"file": (name, data, ctype)})
        assert bad.status_code == 422 and bad.json()["code"] == "INVALID_FILE_TYPE", name
    big = await client.post(url, headers=h, files={"file": ("big.jpg", JPEG + b"0" * (2 * 1024 * 1024), "image/jpeg")})
    assert big.status_code == 413 and big.json()["code"] == "FILE_TOO_LARGE"
    assert (await client.post(url, headers=h)).status_code == 422  # no file


# ------------------------------------------------------------------- errors
async def test_password_is_default_constant_is_valid():
    assert DEFAULT_PASSWORD
