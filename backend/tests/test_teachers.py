import asyncio
import re
import uuid

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import AuditLog, Role, SalaryStructure, Teacher, TeacherAssignment, User
from tests.conftest import DEFAULT_PASSWORD, login
from tests.helpers import create_student, create_teacher, make_school, rand_cnic, tag, teacher_payload

API = "/api/v1"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 300


async def register(client, headers, school, **overrides):
    resp = await client.post(f"{API}/teachers", headers=headers, json=teacher_payload(school, **overrides))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_registration_creates_user_salary_structure_and_assignments(client, auth):
    admin, h = await auth(Role.ADMIN)
    school = await make_school()
    body = await register(client, h, school)
    teacher = body["teacher"]

    assert re.fullmatch(r"EMP-\d{4,}", teacher["employee_id"])
    cred = body["credentials"]["teacher"]
    assert cred["username"] == teacher["employee_id"].lower() and len(cred["temp_password"]) == 10

    assert teacher["salary_structure"] == {
        "basic": "50000.00",
        "house": "10000.00",
        "transport": "5000.00",
        "medical": "2500.00",
        "gross": "67500.00",
    }
    assert len(teacher["assignments"]) == 1
    a = teacher["assignments"][0]
    assert (a["class_name"], a["section_name"], a["subject_name"]) == (school.klass.name, "A", school.math.name)

    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == cred["username"]))
        assert user.role == Role.TEACHER and user.must_change_password is True
        assert cred["temp_password"] not in user.password_hash
        assert (
            await db.scalar(
                select(func.count())
                .select_from(SalaryStructure)
                .where(SalaryStructure.teacher_id == uuid.UUID(teacher["id"]))
            )
            == 1
        )
        log = await db.scalar(
            select(AuditLog).where(
                AuditLog.entity == "teacher", AuditLog.entity_id == teacher["id"], AuditLog.action == "create"
            )
        )
    assert log and log.user_id == admin.id and cred["temp_password"] not in str(log.diff)

    first_login = await login(client, cred["username"], cred["temp_password"])
    assert first_login.json()["user"]["must_change_password"] is True


async def test_gross_is_computed_by_the_server_not_accepted_from_the_client(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    payload = teacher_payload(school)
    payload["salary"]["gross"] = "999999"
    resp = await client.post(f"{API}/teachers", headers=h, json=payload)
    assert resp.status_code == 422 and "salary.gross" in resp.json()["fields"]


async def test_employee_ids_are_sequential_and_unique_under_concurrency(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    results = await asyncio.gather(
        *[client.post(f"{API}/teachers", headers=h, json=teacher_payload(school)) for _ in range(8)]
    )
    assert all(r.status_code == 201 for r in results)
    ids = sorted(int(r.json()["teacher"]["employee_id"].split("-")[1]) for r in results)
    assert ids == list(range(ids[0], ids[0] + 8))


async def test_teacher_validation_and_duplicate_cnic(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    first = await register(client, h, school)
    dup = await client.post(f"{API}/teachers", headers=h, json=teacher_payload(school, cnic=first["teacher"]["cnic"]))
    assert dup.status_code == 409 and dup.json()["code"] == "CNIC_ALREADY_REGISTERED" and "cnic" in dup.json()["fields"]

    bad = await client.post(
        f"{API}/teachers",
        headers=h,
        json=teacher_payload(
            school, cnic="123", phone="0200-1", designation="Wizard", qualification="Hogwarts", dob="2015-01-01"
        ),
    )
    assert bad.status_code == 422
    assert {"cnic", "phone", "designation", "qualification", "dob"} <= bad.json()["fields"].keys()
    neg = teacher_payload(school)
    neg["salary"]["basic"] = "-5"
    assert (await client.post(f"{API}/teachers", headers=h, json=neg)).status_code == 422
    # nothing was left behind by the failed attempts
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(Teacher).where(Teacher.cnic == "123")) == 0


async def test_assignments_must_exist_in_class_subjects(client, auth):
    _, h = await auth(Role.ADMIN)
    school, other = await make_school(), await make_school()
    wrong_subject = [{"class_id": str(school.klass.id), "section_id": None, "subject_id": str(other.math.id)}]
    resp = await client.post(f"{API}/teachers", headers=h, json=teacher_payload(school, assignments=wrong_subject))
    assert resp.status_code == 422 and "not taught in" in resp.json()["fields"]["assignments"]

    wrong_section = [
        {"class_id": str(school.klass.id), "section_id": str(other.sec_a.id), "subject_id": str(school.math.id)}
    ]
    assert (
        await client.post(f"{API}/teachers", headers=h, json=teacher_payload(school, assignments=wrong_section))
    ).status_code == 422

    twice = teacher_payload(school)["assignments"] * 2
    assert (
        await client.post(f"{API}/teachers", headers=h, json=teacher_payload(school, assignments=twice))
    ).status_code == 422

    async with SessionLocal() as db:  # the failed registrations rolled back completely
        assert (
            await db.scalar(
                select(func.count()).select_from(TeacherAssignment).where(TeacherAssignment.class_id == school.klass.id)
            )
            == 0
        )


async def test_replace_assignments_and_salary_structure(client, auth):
    admin, h = await auth(Role.ADMIN)
    school = await make_school()
    tid = (await register(client, h, school))["teacher"]["id"]

    new = [
        {"class_id": str(school.klass.id), "section_id": None, "subject_id": str(school.math.id)},
        {"class_id": str(school.klass.id), "section_id": str(school.sec_b.id), "subject_id": str(school.english.id)},
    ]
    resp = await client.put(f"{API}/teachers/{tid}/assignments", headers=h, json=new)
    assert resp.status_code == 200 and len(resp.json()["assignments"]) == 2
    assert (await client.put(f"{API}/teachers/{tid}/assignments", headers=h, json=[])).json()["assignments"] == []

    sal = await client.put(f"{API}/teachers/{tid}/salary-structure", headers=h, json={"basic": "80000", "house": "0.5"})
    assert sal.status_code == 200 and sal.json()["gross"] == "80000.50" and sal.json()["transport"] == "0.00"
    async with SessionLocal() as db:
        log = await db.scalar(select(AuditLog).where(AuditLog.entity_id == tid, AuditLog.action == "salary_structure"))
    assert log.diff["gross"] == {"old": "67500.00", "new": "80000.50"}


async def test_edit_teacher_employee_id_is_immutable(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    other = await register(client, h, school)
    t = (await register(client, h, school))["teacher"]

    assert (
        await client.put(f"{API}/teachers/{t['id']}", headers=h, json={"employee_id": "EMP-9999"})
    ).status_code == 422
    ok = await client.put(
        f"{API}/teachers/{t['id']}",
        headers=h,
        json={"designation": "Senior Teacher", "city": "Multan", "phone": "03211234567"},
    )
    assert (
        ok.status_code == 200 and ok.json()["designation"] == "Senior Teacher" and ok.json()["phone"] == "0321-1234567"
    )
    clash = await client.put(f"{API}/teachers/{t['id']}", headers=h, json={"cnic": other["teacher"]["cnic"]})
    assert clash.status_code == 409


async def test_teacher_list_filters_and_pagination(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    t = tag()
    await register(client, h, school, full_name=f"Zoya {t}", designation="Coordinator", employment_type="part_time")
    await register(
        client,
        h,
        school,
        full_name=f"Aamir {t}",
        assignments=[{"class_id": str(school.klass.id), "section_id": None, "subject_id": str(school.english.id)}],
    )

    listing = (await client.get(f"{API}/teachers", headers=h, params={"q": t})).json()
    assert [x["full_name"] for x in listing["items"]] == [f"Aamir {t}", f"Zoya {t}"]
    aamir = listing["items"][0]
    assert aamir["subjects"] == [school.english.name] and aamir["classes"] == [
        school.klass.name
    ]  # no section = whole class
    assert listing["items"][1]["classes"] == [f"{school.klass.name}-A"]
    assert (await client.get(f"{API}/teachers", headers=h, params={"q": t, "designation": "Coordinator"})).json()[
        "total"
    ] == 1
    assert (await client.get(f"{API}/teachers", headers=h, params={"q": t, "employment_type": "part_time"})).json()[
        "total"
    ] == 1
    assert (await client.get(f"{API}/teachers", headers=h, params={"q": t, "subject_id": str(school.math.id)})).json()[
        "total"
    ] == 1
    p = (await client.get(f"{API}/teachers", headers=h, params={"q": t, "page_size": 1, "page": 2})).json()
    assert (p["total"], p["pages"], len(p["items"])) == (2, 2, 1)


async def test_cannot_delete_the_only_teacher_of_a_class_subject_unless_forced(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    sole = (await register(client, h, school))["teacher"]
    resp = await client.delete(f"{API}/teachers/{sole['id']}", headers=h)
    assert resp.status_code == 409 and resp.json()["code"] == "SOLE_TEACHER"
    assert school.math.name in resp.json()["detail"]

    forced = await client.delete(f"{API}/teachers/{sole['id']}?force=true", headers=h)
    assert forced.status_code == 204
    assert (await client.get(f"{API}/teachers/{sole['id']}", headers=h)).status_code == 404
    async with SessionLocal() as db:
        teacher = await db.get(Teacher, uuid.UUID(sole["id"]))
        assert teacher.is_deleted and not (await db.get(User, teacher.user_id)).is_active

    # once a second teacher covers the same class-subject, the first can be removed without force
    a = (await register(client, h, school))["teacher"]
    await register(client, h, school)
    assert (await client.delete(f"{API}/teachers/{a['id']}", headers=h)).status_code == 204


async def test_photo_upload_for_teacher(client, auth):
    _, h = await auth(Role.ADMIN)
    school = await make_school()
    tid = (await register(client, h, school))["teacher"]["id"]
    ok = await client.post(f"{API}/teachers/{tid}/photo", headers=h, files={"file": ("me.jpg", JPEG, "image/jpeg")})
    assert ok.status_code == 200 and ok.json()["photo_url"].startswith("/api/v1/uploads/photos/")
    assert (
        await client.post(f"{API}/teachers/{tid}/photo", headers=h, files={"file": ("me.jpg", b"nope", "image/jpeg")})
    ).status_code == 422


# ---------------------------------------------------- who can see salary data
async def test_teacher_sees_only_their_own_profile_and_salary(client):
    school = await make_school()
    mine, my_user = await create_teacher(school)
    theirs, _ = await create_teacher(school)
    token = (await login(client, my_user, DEFAULT_PASSWORD)).json()["access_token"]
    th = {"Authorization": f"Bearer {token}"}

    me = await client.get(f"{API}/teachers/me", headers=th)
    assert me.status_code == 200 and me.json()["id"] == str(mine.teacher.id)
    assert me.json()["salary_structure"]["gross"] == "67500.00"
    assert (await client.get(f"{API}/teachers/{mine.teacher.id}", headers=th)).status_code == 200
    other = await client.get(f"{API}/teachers/{theirs.teacher.id}", headers=th)
    assert other.status_code == 404  # existence is not leaked
    assert (await client.get(f"{API}/teachers", headers=th)).status_code == 403
    assert (
        await client.put(f"{API}/teachers/{mine.teacher.id}/salary-structure", headers=th, json={"basic": "1"})
    ).status_code == 403


async def test_ceo_can_see_salary_but_not_change_it(client, auth):
    school = await make_school()
    reg, _ = await create_teacher(school)
    _, ch = await auth(Role.CEO)
    seen = await client.get(f"{API}/teachers/{reg.teacher.id}", headers=ch)
    assert seen.status_code == 200 and seen.json()["salary_structure"]["gross"] == "67500.00"
    assert (await client.get(f"{API}/teachers", headers=ch)).status_code == 200
    assert (
        await client.put(f"{API}/teachers/{reg.teacher.id}/salary-structure", headers=ch, json={"basic": "1"})
    ).status_code == 403
    assert (await client.delete(f"{API}/teachers/{reg.teacher.id}", headers=ch)).status_code == 403


async def test_students_and_parents_see_no_teacher_or_salary_data(client, auth):
    school = await make_school()
    reg, _ = await create_teacher(school)
    for role in (Role.STUDENT, Role.PARENT):
        _, h = await auth(role)
        for path in ("/teachers", f"/teachers/{reg.teacher.id}", "/teachers/me"):
            assert (await client.get(API + path, headers=h)).status_code == 403, (role, path)


async def test_teacher_me_without_profile_is_404(client, auth):
    _, h = await auth(Role.TEACHER)  # a bare teacher account with no profile row
    assert (await client.get(f"{API}/teachers/me", headers=h)).status_code == 404


_ = (create_student, rand_cnic)
