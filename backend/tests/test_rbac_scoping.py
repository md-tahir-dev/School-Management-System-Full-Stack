"""Role x endpoint matrix, plus row-level scoping (teacher classes, own student, own children)."""

import uuid

from app.models import Role
from app.services.students import LoginOverrides
from tests.conftest import DEFAULT_PASSWORD, login
from tests.helpers import create_student, create_teacher, make_school, rand_cnic, tag

API = "/api/v1"
ALL = set(Role)
ADMIN = {Role.ADMIN}
SCHOOL = {Role.ADMIN, Role.CEO, Role.HEADMASTER}  # unscoped readers
MANAGERS = {Role.ADMIN, Role.HEADMASTER}  # settings/academic writers
U = "00000000-0000-4000-8000-000000000001"  # a well-formed id that does not exist

# (method, path, roles allowed to reach it). Allowed roles may get 404/422 on the fake id or empty body;
# what matters is that they are NOT rejected with 401/403, and everyone else IS rejected with 403.
MATRIX: list[tuple[str, str, set[Role]]] = [
    ("GET", "/settings", ALL),
    ("PUT", "/settings", MANAGERS),
    ("POST", "/settings/logo", MANAGERS),
    ("POST", "/settings/branding/favicon", MANAGERS),
    ("DELETE", "/settings/branding/login_image", MANAGERS),
    ("GET", "/academic-years", SCHOOL),
    ("POST", "/academic-years", MANAGERS),
    ("PUT", f"/academic-years/{U}", MANAGERS),
    ("POST", f"/academic-years/{U}/set-current", MANAGERS),
    ("GET", "/classes", ALL),
    ("POST", "/classes", MANAGERS),
    ("PUT", f"/classes/{U}", MANAGERS),
    ("DELETE", f"/classes/{U}", MANAGERS),
    ("GET", f"/classes/{U}/sections", ALL),
    ("POST", f"/classes/{U}/sections", MANAGERS),
    ("PUT", f"/sections/{U}", MANAGERS),
    ("DELETE", f"/sections/{U}", MANAGERS),
    ("GET", "/subjects", ALL),
    ("POST", "/subjects", MANAGERS),
    ("PUT", f"/subjects/{U}", MANAGERS),
    ("DELETE", f"/subjects/{U}", MANAGERS),
    ("GET", f"/classes/{U}/subjects", ALL),
    ("PUT", f"/classes/{U}/subjects", MANAGERS),
    ("GET", "/fee-structures", SCHOOL),
    ("PUT", "/fee-structures", MANAGERS),
    ("GET", "/users", SCHOOL),
    ("POST", "/users", ADMIN),
    ("PUT", f"/users/{U}", ADMIN),
    ("PUT", f"/users/{U}/activate", MANAGERS),
    ("PUT", f"/users/{U}/deactivate", MANAGERS),
    ("POST", f"/users/{U}/reset-password", MANAGERS),
    ("GET", "/students", ALL),
    ("POST", "/students", ADMIN),
    ("GET", "/students/guardian-lookup?father_cnic=12345-1234567-1", ADMIN),
    ("GET", f"/students/{U}", ALL),
    ("PUT", f"/students/{U}", ADMIN),
    ("DELETE", f"/students/{U}", ADMIN),
    ("POST", f"/students/{U}/photo", ADMIN),
    ("PUT", f"/students/{U}/status", ADMIN),
    ("PUT", f"/students/{U}/discount", ADMIN),
    ("GET", f"/students/{U}/ledger", SCHOOL | {Role.STUDENT, Role.PARENT}),
    ("GET", "/teachers", SCHOOL),
    ("POST", "/teachers", ADMIN),
    ("GET", "/teachers/me", {Role.TEACHER}),
    ("GET", f"/teachers/{U}", SCHOOL | {Role.TEACHER}),
    ("PUT", f"/teachers/{U}", ADMIN),
    ("DELETE", f"/teachers/{U}", ADMIN),
    ("POST", f"/teachers/{U}/photo", ADMIN),
    ("PUT", f"/teachers/{U}/assignments", ADMIN),
    ("PUT", f"/teachers/{U}/salary-structure", ADMIN),
    ("GET", "/parent/children", {Role.PARENT}),
    ("GET", f"/parent/children/{U}", {Role.PARENT}),
    ("GET", f"/parent/children/{U}/dashboard", {Role.PARENT}),
    ("GET", "/meta/options", ALL),
    ("GET", "/exams", ALL),
    ("POST", "/exams", MANAGERS),
    ("GET", f"/exams/{U}", ALL),
    ("PUT", f"/exams/{U}", MANAGERS),
    ("DELETE", f"/exams/{U}", MANAGERS),
    ("GET", f"/exams/{U}/subjects", ALL),
    ("PUT", f"/exams/{U}/subjects", MANAGERS),
    ("POST", f"/exams/{U}/subjects/reset", MANAGERS),
    ("POST", f"/exams/{U}/publish", MANAGERS),
    ("POST", f"/exams/{U}/unpublish", MANAGERS),
    ("GET", f"/exams/{U}/marks-sheet", MANAGERS | {Role.TEACHER}),
    ("PUT", f"/exams/{U}/marks", MANAGERS | {Role.TEACHER}),
    ("GET", f"/exams/{U}/students/{U}/entry", MANAGERS | {Role.TEACHER}),
    ("PUT", f"/exams/{U}/students/{U}/entry", MANAGERS | {Role.TEACHER}),
    ("GET", f"/exams/{U}/results", ALL),
    ("GET", f"/exams/{U}/results/export", ALL),
    ("GET", f"/exams/{U}/results/pdf", MANAGERS),
    ("GET", f"/exams/{U}/analytics", ALL),
    ("GET", f"/exams/{U}/marks-progress", MANAGERS | {Role.TEACHER}),
    ("GET", f"/results/{U}", ALL),
    ("GET", f"/results/{U}/pdf", ALL),
    ("GET", "/holidays", ALL),
    ("POST", "/holidays", MANAGERS),
    ("DELETE", f"/holidays/{U}", MANAGERS),
    # timetable
    ("GET", "/periods", ALL),
    ("POST", "/periods", MANAGERS),
    ("PUT", f"/periods/{U}", MANAGERS),
    ("DELETE", f"/periods/{U}", MANAGERS),
    ("GET", f"/timetable?class_id={U}", SCHOOL | {Role.TEACHER}),
    ("GET", "/timetable/me", {Role.TEACHER, Role.STUDENT, Role.PARENT}),
    ("PUT", "/timetable/cell", MANAGERS),
    ("DELETE", f"/timetable/cell/{U}", MANAGERS),
    ("GET", "/class-teachers", SCHOOL | {Role.TEACHER}),
    ("PUT", "/class-teachers", MANAGERS),
    ("GET", "/attendance", ALL),
    ("POST", "/attendance/bulk", MANAGERS | {Role.TEACHER}),
    ("GET", "/teacher-attendance", SCHOOL),
    ("POST", "/teacher-attendance/bulk", MANAGERS),
    ("GET", "/reports/attendance/class", ALL),
    ("GET", "/reports/attendance/overview", SCHOOL),
    ("GET", "/reports/attendance/low", SCHOOL),
    # diary and study material
    ("GET", "/diary?date=2026-01-01", ALL),
    ("POST", "/diary", MANAGERS | {Role.TEACHER}),
    ("PUT", f"/diary/{U}", MANAGERS | {Role.TEACHER}),
    ("DELETE", f"/diary/{U}", MANAGERS | {Role.TEACHER}),
    ("PUT", f"/diary/{U}/attachment", MANAGERS | {Role.TEACHER}),
    ("POST", f"/diary/{U}/submission", {Role.STUDENT}),
    ("GET", f"/diary/{U}/submissions", SCHOOL | {Role.TEACHER}),
    ("PUT", f"/diary/submissions/{U}", MANAGERS | {Role.TEACHER}),
    ("GET", "/materials", ALL),
    ("POST", "/materials", MANAGERS | {Role.TEACHER}),
    ("DELETE", f"/materials/{U}", MANAGERS | {Role.TEACHER}),
    # uploaded documents: login + row scope (unknown file -> 404 for every role)
    ("GET", f"/uploads/diary/{'0' * 32}.pdf", ALL),
    ("GET", f"/uploads/homework/{'0' * 32}.pdf", ALL),
    ("GET", f"/uploads/materials/{'0' * 32}.pdf", ALL),
    # online tests
    ("GET", "/tests", SCHOOL | {Role.TEACHER}),
    ("GET", "/tests/me", {Role.STUDENT, Role.PARENT}),
    ("POST", "/tests", MANAGERS | {Role.TEACHER}),
    ("GET", f"/tests/{U}", SCHOOL | {Role.TEACHER}),
    ("PUT", f"/tests/{U}", MANAGERS | {Role.TEACHER}),
    ("DELETE", f"/tests/{U}", MANAGERS | {Role.TEACHER}),
    ("PUT", f"/tests/{U}/questions", MANAGERS | {Role.TEACHER}),
    ("POST", f"/tests/{U}/publish", MANAGERS | {Role.TEACHER}),
    ("POST", f"/tests/{U}/close", MANAGERS | {Role.TEACHER}),
    ("POST", f"/tests/{U}/release", MANAGERS | {Role.TEACHER}),
    ("GET", f"/tests/{U}/attempts", SCHOOL | {Role.TEACHER}),
    ("POST", f"/tests/{U}/start", {Role.STUDENT}),
    ("GET", f"/tests/attempts/{U}", {Role.STUDENT}),
    ("PUT", f"/tests/attempts/{U}/answers", {Role.STUDENT}),
    ("POST", f"/tests/attempts/{U}/submit", {Role.STUDENT}),
    ("GET", f"/tests/attempts/{U}/result", ALL),
    ("PUT", f"/tests/attempts/{U}/grade", MANAGERS | {Role.TEACHER}),
    # fees (teachers get 403 from the service, so like the ledger they are listed as not allowed)
    ("POST", "/fees/payments", MANAGERS),
    ("GET", "/fees/payments", SCHOOL | {Role.STUDENT, Role.PARENT}),
    ("GET", f"/fees/payments/{U}", SCHOOL | {Role.STUDENT, Role.PARENT}),
    ("GET", f"/fees/payments/{U}/pdf", SCHOOL | {Role.STUDENT, Role.PARENT}),
    ("POST", f"/fees/payments/{U}/void", MANAGERS),
    ("GET", "/fees/defaulters", SCHOOL),
    ("GET", "/fees/summary?month=2026-01-01", SCHOOL),
    # salary (student/parent get 403 from the service on a record)
    ("POST", "/salary/generate", MANAGERS),
    ("GET", "/salary?month=2026-01-01", SCHOOL),
    ("GET", "/salary/me", {Role.TEACHER}),
    ("GET", "/salary/advances?month=2026-01-01", SCHOOL),
    ("POST", "/salary/advances", MANAGERS),
    ("DELETE", f"/salary/advances/{U}", MANAGERS),
    ("GET", f"/salary/{U}", SCHOOL | {Role.TEACHER}),
    ("POST", f"/salary/{U}/pay", MANAGERS),
    ("GET", f"/salary/{U}/pdf", SCHOOL | {Role.TEACHER}),
    # announcements, events, calendar, notifications
    ("GET", "/announcements", ALL),
    ("POST", "/announcements", MANAGERS | {Role.TEACHER}),
    ("DELETE", f"/announcements/{U}", MANAGERS | {Role.TEACHER}),
    ("GET", "/events?from=2026-01-01&to=2026-01-31", ALL),
    ("POST", "/events", MANAGERS),
    ("PUT", f"/events/{U}", MANAGERS),
    ("DELETE", f"/events/{U}", MANAGERS),
    ("GET", "/calendar?from=2026-01-01&to=2026-01-31", ALL),
    ("GET", "/notifications", ALL),
    ("GET", "/notifications/unread-count", ALL),
    ("POST", "/notifications/read-all", ALL),
    ("POST", f"/notifications/{U}/read", ALL),
    ("GET", "/student/dashboard", {Role.STUDENT}),  # service raises 403 for non-students, not the route guard
    ("GET", "/ceo/dashboard", {Role.CEO, Role.HEADMASTER}),
]


async def test_role_by_endpoint_matrix(client, auth):
    tokens = {role: (await auth(role))[1] for role in Role}
    wrong = []
    for method, path, allowed in MATRIX:
        for role in Role:
            resp = await client.request(
                method, API + path, headers=tokens[role], json={} if method in ("POST", "PUT") else None
            )
            if role in allowed and resp.status_code in (401, 403):
                wrong.append(f"{role.value} should be allowed on {method} {path}, got {resp.status_code}")
            if role not in allowed and resp.status_code != 403:
                wrong.append(f"{role.value} should get 403 on {method} {path}, got {resp.status_code}")
        anon = await client.request(method, API + path, json={} if method in ("POST", "PUT") else None)
        if anon.status_code != 401:
            wrong.append(f"anonymous should get 401 on {method} {path}, got {anon.status_code}")
    assert not wrong, "\n".join(wrong)


async def test_ceo_can_read_everything_but_write_nothing(client, auth):
    _, h = await auth(Role.CEO)
    for path in (
        "/settings",
        "/academic-years",
        "/classes",
        "/subjects",
        "/fee-structures",
        "/users",
        "/students",
        "/teachers",
    ):
        assert (await client.get(API + path, headers=h)).status_code == 200, path
    school = await make_school()
    reg = await create_student(school)
    sid = reg.student.id
    assert (await client.get(f"{API}/students/{sid}", headers=h)).status_code == 200
    assert (await client.get(f"{API}/students/{sid}/ledger", headers=h)).status_code == 200
    writes = [
        ("PUT", "/settings", {"slogan": "x"}),
        ("POST", "/classes", {"name": "X"}),
        ("PUT", f"/students/{sid}", {"city": "x"}),
        ("DELETE", f"/students/{sid}", None),
        ("PUT", f"/students/{sid}/discount", {"discount_percent": "10"}),
        ("POST", "/students", {}),
        ("POST", "/teachers", {}),
    ]
    for method, path, body in writes:
        assert (await client.request(method, API + path, headers=h, json=body)).status_code == 403, (method, path)


# ------------------------------------------------------------------ scoping
async def sign_in(client, username):
    resp = await login(client, username, DEFAULT_PASSWORD)
    assert resp.status_code == 200, resp.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_teacher_sees_only_students_in_assigned_class_sections(client):
    school = await make_school()
    other_school = await make_school()
    s_a = (await create_student(school, section_id=str(school.sec_a.id))).student
    s_b = (await create_student(school, section_id=str(school.sec_b.id))).student
    s_far = (await create_student(other_school)).student
    _, teacher_login = await create_teacher(school)  # assigned to section A only
    h = await sign_in(client, teacher_login)

    listing = (await client.get(f"{API}/students", headers=h, params={"page_size": 100})).json()
    assert {s["id"] for s in listing["items"]} == {str(s_a.id)} and listing["total"] == 1
    assert (await client.get(f"{API}/students/{s_a.id}", headers=h)).status_code == 200
    for hidden in (s_b, s_far):
        assert (await client.get(f"{API}/students/{hidden.id}", headers=h)).status_code == 404  # existence not leaked
    assert (
        await client.get(f"{API}/students/{U}", headers=h)
    ).status_code == 404  # same answer as for a real hidden id
    assert (
        await client.get(f"{API}/students/{s_a.id}/ledger", headers=h)
    ).status_code == 403  # fees are not for teachers
    assert (await client.put(f"{API}/students/{s_a.id}", headers=h, json={"city": "x"})).status_code == 403
    # filters cannot be used to widen the scope
    widened = (await client.get(f"{API}/students", headers=h, params={"section_id": str(school.sec_b.id)})).json()
    assert widened["total"] == 0
    widened = (await client.get(f"{API}/students", headers=h, params={"class_id": str(other_school.klass.id)})).json()
    assert widened["total"] == 0


async def test_assignment_without_a_section_covers_the_whole_class(client):
    school = await make_school()
    s_a = (await create_student(school, section_id=str(school.sec_a.id))).student
    s_b = (await create_student(school, section_id=str(school.sec_b.id))).student
    whole_class = [{"class_id": str(school.klass.id), "section_id": None, "subject_id": str(school.math.id)}]
    _, teacher_login = await create_teacher(school, assignments=whole_class)
    h = await sign_in(client, teacher_login)
    ids = {s["id"] for s in (await client.get(f"{API}/students", headers=h, params={"page_size": 100})).json()["items"]}
    assert ids == {str(s_a.id), str(s_b.id)}


async def test_teacher_without_assignments_sees_no_students(client):
    school = await make_school()
    await create_student(school)
    _, teacher_login = await create_teacher(school, assignments=[])
    h = await sign_in(client, teacher_login)
    assert (await client.get(f"{API}/students", headers=h)).json()["total"] == 0


async def test_student_sees_only_themselves(client):
    school = await make_school()
    username = f"stu-{tag()}"
    mine = await create_student(
        school, create_student_login=True, logins=LoginOverrides(student=(username, DEFAULT_PASSWORD))
    )
    other = await create_student(school)
    h = await sign_in(client, username)

    listing = (await client.get(f"{API}/students", headers=h)).json()
    assert [s["id"] for s in listing["items"]] == [str(mine.student.id)]
    assert (await client.get(f"{API}/students/{mine.student.id}", headers=h)).status_code == 200
    assert (await client.get(f"{API}/students/{mine.student.id}/ledger", headers=h)).status_code == 200
    assert (await client.get(f"{API}/students/{other.student.id}", headers=h)).status_code == 404
    assert (await client.get(f"{API}/students/{other.student.id}/ledger", headers=h)).status_code == 404
    assert (await client.put(f"{API}/students/{mine.student.id}", headers=h, json={"city": "x"})).status_code == 403


async def test_parent_list_and_detail_are_limited_to_linked_children(client):
    school = await make_school()
    username = f"par-{tag()}"
    cnic, phone = rand_cnic(), "0300-" + str(uuid.uuid4().int)[:7]
    kid = await create_student(
        school,
        logins=LoginOverrides(parent=(username, DEFAULT_PASSWORD)),
        guardian={"father_cnic": cnic, "father_phone": phone},
    )
    stranger = await create_student(school)
    h = await sign_in(client, username)
    listing = (await client.get(f"{API}/students", headers=h)).json()
    assert [s["id"] for s in listing["items"]] == [str(kid.student.id)]
    assert (await client.get(f"{API}/students/{stranger.student.id}", headers=h)).status_code == 404


async def test_deleted_students_disappear_for_everyone(client, auth):
    school = await make_school()
    reg = await create_student(school)
    _, admin_h = await auth(Role.ADMIN)
    assert (await client.delete(f"{API}/students/{reg.student.id}", headers=admin_h)).status_code == 204
    _, ceo_h = await auth(Role.CEO)
    assert (await client.get(f"{API}/students/{reg.student.id}", headers=ceo_h)).status_code == 404
