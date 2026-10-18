import uuid

from app.models import Role
from app.services.students import LoginOverrides
from tests.conftest import DEFAULT_PASSWORD
from tests.helpers import create_student, create_teacher, make_school
from tests.test_attendance import auth_as_existing

API = "/api/v1"


async def _period(client, h, *, is_break=False):
    n = uuid.uuid4().hex[:6]
    body = {"name": f"P-{n}", "start_time": "08:00", "end_time": "08:40", "is_break": is_break}
    resp = await client.post(f"{API}/periods", json=body, headers=h)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _student_login(school, section):
    username = f"s{uuid.uuid4().hex[:8]}"
    reg = await create_student(
        school,
        section_id=str(section.id),
        create_student_login=True,
        logins=LoginOverrides(student=(username, DEFAULT_PASSWORD)),
    )
    return reg, username


async def test_lecture_assigns_teacher_blocks_double_booking_and_shows_per_section(client, auth):
    school = await make_school()
    _, admin_h = await auth(Role.HEADMASTER)  # managers build the timetable
    period = await _period(client, admin_h)
    # teacher has no assignment in section B yet
    reg, username = await create_teacher(school, assignments=[])
    teacher_id = str(reg.teacher.id)
    teacher_h = await auth_as_existing(client, username)
    roster = {"class_id": str(school.klass.id), "section_id": str(school.sec_b.id)}
    assert (await client.get(f"{API}/attendance", params=roster, headers=teacher_h)).status_code == 404

    cell = {**roster, "weekday": 1, "period_id": period, "subject_id": str(school.math.id), "teacher_id": teacher_id}
    resp = await client.put(f"{API}/timetable/cell", json=cell, headers=admin_h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["teacher_id"] == teacher_id and resp.json()["subject_name"] == school.math.name
    # the lecture created the teaching assignment, so the teacher now has the section in scope
    assert (await client.get(f"{API}/attendance", params=roster, headers=teacher_h)).status_code == 200

    # same teacher, same slot, other section -> 409; re-saving the same cell is an update, not a clash
    clash = {**cell, "section_id": str(school.sec_a.id)}
    resp = await client.put(f"{API}/timetable/cell", json=clash, headers=admin_h)
    assert resp.status_code == 409 and resp.json()["fields"] == {"teacher_id": resp.json()["detail"]}
    assert (await client.put(f"{API}/timetable/cell", json={**cell, "room": "R1"}, headers=admin_h)).json()[
        "room"
    ] == "R1"

    mine = (await client.get(f"{API}/timetable/me", headers=teacher_h)).json()
    assert [e["section_id"] for e in mine["entries"]] == [str(school.sec_b.id)]
    assert any(p["id"] == period for p in mine["periods"])

    _, b_user = await _student_login(school, school.sec_b)
    _, a_user = await _student_login(school, school.sec_a)
    b = (await client.get(f"{API}/timetable/me", headers=await auth_as_existing(client, b_user))).json()
    a = (await client.get(f"{API}/timetable/me", headers=await auth_as_existing(client, a_user))).json()
    assert len(b["entries"]) == 1 and a["entries"] == []

    # removing the teacher's last lecture there also removes the assignment it created
    entry_id = b["entries"][0]["id"]
    assert (await client.delete(f"{API}/timetable/cell/{entry_id}", headers=admin_h)).status_code == 204
    assert (await client.get(f"{API}/attendance", params=roster, headers=teacher_h)).status_code == 404


async def test_cell_validation(client, auth):
    school = await make_school()
    _, admin_h = await auth(Role.ADMIN)
    period, brk = await _period(client, admin_h), await _period(client, admin_h, is_break=True)
    reg, _ = await create_teacher(school)
    base = {
        "class_id": str(school.klass.id),
        "section_id": str(school.sec_a.id),
        "weekday": 2,
        "period_id": period,
        "subject_id": str(school.math.id),
        "teacher_id": str(reg.teacher.id),
    }
    other = await make_school()
    for patch, field in (
        ({"period_id": brk}, "period_id"),
        ({"subject_id": str(other.math.id)}, "subject_id"),
        ({"section_id": None}, "section_id"),  # class has sections
        ({"section_id": str(other.sec_a.id)}, "section_id"),
    ):
        resp = await client.put(f"{API}/timetable/cell", json={**base, **patch}, headers=admin_h)
        assert resp.status_code == 422 and field in resp.json()["fields"], (patch, resp.text)


async def test_class_teacher_sees_whole_section_but_not_marks(client, auth):
    school = await make_school()
    _, admin_h = await auth(Role.ADMIN)
    reg, username = await create_teacher(school, assignments=[])
    teacher_h = await auth_as_existing(client, username)
    roster = {"class_id": str(school.klass.id), "section_id": str(school.sec_a.id)}
    body = {**roster, "teacher_id": str(reg.teacher.id)}
    assert (await client.put(f"{API}/class-teachers", json=body, headers=admin_h)).status_code == 204
    assert (await client.get(f"{API}/attendance", params=roster, headers=teacher_h)).status_code == 200
    s = await create_student(school, section_id=str(school.sec_a.id))
    assert (await client.get(f"{API}/students/{s.student.id}", headers=teacher_h)).status_code == 200
    listed = (await client.get(f"{API}/class-teachers", headers=teacher_h)).json()
    assert any(c["teacher_id"] == str(reg.teacher.id) and c["section_name"] == "A" for c in listed)

    exam = await client.post(
        f"{API}/exams",
        json={
            "name": "T",
            "type": "Unit Test",
            "class_id": str(school.klass.id),
            "academic_year_id": str(school.year.id),
        },
        headers=admin_h,
    )
    assert exam.status_code == 201, exam.text
    sheet = await client.get(
        f"{API}/exams/{exam.json()['id']}/marks-sheet", params={"subject_id": str(school.math.id)}, headers=teacher_h
    )
    assert sheet.status_code == 404  # class teacher isn't the subject teacher

    assert (
        await client.put(f"{API}/class-teachers", json={**body, "teacher_id": None}, headers=admin_h)
    ).status_code == 204
    assert (await client.get(f"{API}/attendance", params=roster, headers=teacher_h)).status_code == 404


async def test_only_managers_edit_and_out_of_scope_is_404(client, auth):
    school = await make_school()
    _, admin_h = await auth(Role.ADMIN)
    period = await _period(client, admin_h)
    reg, username = await create_teacher(school)  # teaches section A
    teacher_h = await auth_as_existing(client, username)
    cell = {
        "class_id": str(school.klass.id),
        "section_id": str(school.sec_a.id),
        "weekday": 3,
        "period_id": period,
        "subject_id": str(school.math.id),
        "teacher_id": str(reg.teacher.id),
    }
    for role in (Role.CEO, Role.TEACHER, Role.STUDENT, Role.PARENT):
        _, h = await auth(role)
        assert (await client.put(f"{API}/timetable/cell", json=cell, headers=h)).status_code == 403
        assert (
            await client.post(
                f"{API}/periods", json={"name": "x", "start_time": "09:00", "end_time": "09:30"}, headers=h
            )
        ).status_code == 403
    q = {"class_id": str(school.klass.id), "section_id": str(school.sec_a.id)}
    assert (await client.get(f"{API}/timetable", params=q, headers=teacher_h)).status_code == 200
    q["section_id"] = str(school.sec_b.id)
    assert (await client.get(f"{API}/timetable", params=q, headers=teacher_h)).status_code == 404
