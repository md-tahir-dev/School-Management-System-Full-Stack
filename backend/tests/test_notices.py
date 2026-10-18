import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Notification, Role
from app.services.students import LoginOverrides
from tests.conftest import DEFAULT_PASSWORD
from tests.helpers import create_student, create_teacher, make_school
from tests.test_attendance import auth_as_existing
from tests.test_parent import family, parent_headers

API = "/api/v1"


async def _student(client, school, section):
    username = f"s{uuid.uuid4().hex[:8]}"
    reg = await create_student(
        school,
        section_id=str(section.id),
        create_student_login=True,
        logins=LoginOverrides(student=(username, DEFAULT_PASSWORD)),
    )
    return reg, await auth_as_existing(client, username)


async def _teacher(client, school):
    reg, username = await create_teacher(school)
    return reg, await auth_as_existing(client, username)


def _title(prefix="N"):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


async def _announce(client, h, status=201, **over):
    body = {"title": _title(), "message": "Hello", "audience": "all", **over}
    resp = await client.post(f"{API}/announcements", json=body, headers=h)
    assert resp.status_code == status, resp.text
    return resp.json()


async def _titles(client, h):
    resp = await client.get(f"{API}/announcements", params={"page_size": 100}, headers=h)
    assert resp.status_code == 200, resp.text
    return {a["title"] for a in resp.json()["items"]}


async def _notes(client, h):
    """Read via the DB: GET /notifications 500s (see test_list_notifications_endpoint)."""
    uid = uuid.UUID((await client.get(f"{API}/auth/me", headers=h)).json()["id"])
    async with SessionLocal() as db:
        rows = await db.scalars(select(Notification).where(Notification.user_id == uid))
        return {n.message: {"id": str(n.id), "link": n.link, "is_read": n.is_read} for n in rows}


async def _count(client, h):
    return (await client.get(f"{API}/notifications/unread-count", headers=h)).json()["count"]


def _target(school, section="a"):
    return {"class_id": str(school.klass.id), "section_id": str(getattr(school, f"sec_{section}").id)}


# ------------------------------------------------------------------ announcements
async def test_announcement_visibility_by_audience_and_class(client, auth):
    school, other = await make_school(), await make_school()
    _, hm_h = await auth(Role.HEADMASTER)
    _, ceo_h = await auth(Role.CEO)
    _, admin_h = await auth(Role.ADMIN)
    _, t_h = await _teacher(client, school)
    _, a_h = await _student(client, school, school.sec_a)
    _, b_h = await _student(client, school, school.sec_b)
    _, x_h = await _student(client, other, other.sec_a)
    username, _kids = await family(school, children=1)  # child is in section A
    p_h = await parent_headers(client, username)

    everyone = (await _announce(client, hm_h))["title"]
    teachers = (await _announce(client, hm_h, audience="teachers"))["title"]
    to_a = (await _announce(client, hm_h, audience="students", **_target(school)))["title"]
    to_a_parents = (await _announce(client, hm_h, audience="parents", **_target(school)))["title"]

    seen = {name: await _titles(client, h) for name, h in (("t", t_h), ("a", a_h), ("b", b_h), ("x", x_h), ("p", p_h))}
    assert {everyone, teachers} <= seen["t"] and not {to_a, to_a_parents} & seen["t"]
    assert everyone in seen["a"] and to_a in seen["a"] and not {teachers, to_a_parents} & seen["a"]
    assert everyone in seen["b"] and not {teachers, to_a, to_a_parents} & seen["b"]
    assert everyone in seen["x"] and not {teachers, to_a, to_a_parents} & seen["x"]
    assert everyone in seen["p"] and to_a_parents in seen["p"] and not {teachers, to_a} & seen["p"]
    for h in (ceo_h, admin_h, hm_h):
        assert {everyone, teachers, to_a, to_a_parents} <= await _titles(client, h)


async def test_teacher_posting_scope(client, auth):
    school = await make_school()
    _, hm_h = await auth(Role.HEADMASTER)
    _, t_h = await _teacher(client, school)  # assigned to section A only

    ok = await _announce(client, t_h, audience="students", **_target(school))
    assert ok["can_edit"] is True and ok["class_name"] == school.klass.name

    resp = await client.post(
        f"{API}/announcements",
        json={"title": "x", "message": "y", "audience": "students", **_target(school, "b")},
        headers=t_h,
    )
    assert resp.status_code == 404
    resp = await client.post(f"{API}/announcements", json={"title": "x", "message": "y"}, headers=t_h)
    assert resp.status_code == 422 and "class_id" in resp.json()["fields"]
    resp = await client.post(
        f"{API}/announcements",
        json={"title": "x", "message": "y", "audience": "teachers", **_target(school)},
        headers=t_h,
    )
    assert resp.status_code == 422 and "audience" in resp.json()["fields"]
    resp = await client.post(
        f"{API}/announcements",
        json={"title": "x", "message": "y", "class_id": str(school.klass.id), "section_id": str(uuid.uuid4())},
        headers=hm_h,
    )
    assert resp.status_code == 422 and "section_id" in resp.json()["fields"]


async def test_announcement_delete_rules(client, auth):
    school = await make_school()
    _, hm_h = await auth(Role.HEADMASTER)
    _, author_h = await _teacher(client, school)
    _, second_h = await _teacher(client, school)
    _, outsider_h = await _teacher(client, await make_school())

    # audience "all" so a second teacher of the same section can see it (but not edit it)
    ann = await _announce(client, author_h, **_target(school))
    url = f"{API}/announcements/{ann['id']}"
    assert (await client.delete(url, headers=outsider_h)).status_code == 404
    assert (await client.delete(url, headers=second_h)).status_code == 403
    assert (await client.delete(url, headers=author_h)).status_code == 204
    assert (await client.delete(url, headers=author_h)).status_code == 404

    mgr_target = await _announce(client, author_h, **_target(school))
    assert (await client.delete(f"{API}/announcements/{mgr_target['id']}", headers=hm_h)).status_code == 204
    assert mgr_target["title"] not in await _titles(client, author_h)


# ------------------------------------------------------------------ notifications
async def test_announcement_fans_out_notifications_and_read_state(client, auth):
    school = await make_school()
    _, hm_h = await auth(Role.HEADMASTER)
    _, a_h = await _student(client, school, school.sec_a)
    _, b_h = await _student(client, school, school.sec_b)
    username, _kids = await family(school, children=1)
    p_h = await parent_headers(client, username)

    before = await _count(client, a_h)
    ann = await _announce(client, hm_h, **_target(school))
    msg = f"Announcement: {ann['title']}"
    for h in (a_h, p_h):
        note = (await _notes(client, h)).get(msg)
        assert note is not None and note["link"] == "announcements" and note["is_read"] is False
    assert msg not in await _notes(client, b_h)
    assert await _count(client, a_h) == before + 1

    # another user can't mark someone else's notification: the owner's count is unchanged
    note_id = (await _notes(client, a_h))[msg]["id"]
    assert (await client.post(f"{API}/notifications/{note_id}/read", headers=b_h)).status_code == 204
    assert await _count(client, a_h) == before + 1

    assert (await client.post(f"{API}/notifications/{note_id}/read", headers=a_h)).status_code == 204
    assert await _count(client, a_h) == before
    assert (await _notes(client, a_h))[msg]["is_read"] is True

    await _announce(client, hm_h, **_target(school))
    assert await _count(client, a_h) >= 1
    assert (await client.post(f"{API}/notifications/read-all", headers=a_h)).status_code == 204
    assert await _count(client, a_h) == 0


async def test_diary_entry_notifies_section_students_and_parents(client):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    _, a_h = await _student(client, school, school.sec_a)
    _, b_h = await _student(client, school, school.sec_b)
    username, _kids = await family(school, children=1)
    p_h = await parent_headers(client, username)

    title, day = _title("Diary"), "2026-10-08"
    body = {**_target(school), "subject_id": str(school.math.id), "date": day, "title": title, "body": "Read"}
    assert (await client.post(f"{API}/diary", json=body, headers=t_h)).status_code == 201
    for h in (a_h, p_h):
        note = (await _notes(client, h)).get(f"New diary entry: {title}")
        assert note is not None and note["link"] == f"diary?date={day}"
    assert f"New diary entry: {title}" not in await _notes(client, b_h)


async def test_payment_notifies_parent(client, auth):
    school = await make_school()
    _, admin_h = await auth(Role.ADMIN)
    username, kids = await family(school, children=1)
    p_h = await parent_headers(client, username)
    body = {"student_id": str(kids[0].student.id), "amount": "500", "method": "cash"}
    resp = await client.post(f"{API}/fees/payments", json=body, headers=admin_h)
    assert resp.status_code == 201, resp.text
    receipt = resp.json()["receipt_no"]
    notes = [n for m, n in (await _notes(client, p_h)).items() if receipt in m]
    assert len(notes) == 1 and notes[0]["link"] == "fees"


async def test_salary_payment_notifies_teacher(client, auth):
    school = await make_school()
    _, admin_h = await auth(Role.ADMIN)
    reg, username = await create_teacher(school)
    t_h = await auth_as_existing(client, username)
    month = "2047-05"
    resp = await client.post(f"{API}/salary/generate", json={"month": f"{month}-15"}, headers=admin_h)
    assert resp.status_code == 200, resp.text
    recs = await client.get(f"{API}/salary", params={"month": f"{month}-01"}, headers=admin_h)
    rec = next(r for r in recs.json() if r["teacher_id"] == str(reg.teacher.id))
    assert await _notes(client, t_h) == {}
    assert (await client.post(f"{API}/salary/{rec['id']}/pay", json={}, headers=admin_h)).status_code == 200
    notes = await _notes(client, t_h)
    assert len(notes) == 1
    ((msg, note),) = notes.items()
    assert "May 2047" in msg and note["link"] == "salary"


# ------------------------------------------------------------------ events
def _event(**over):
    return {"title": _title("Ev"), "start_date": "2041-03-10", **over}


async def test_only_managers_write_events(client, auth):
    _, admin_h = await auth(Role.ADMIN)
    _, hm_h = await auth(Role.HEADMASTER)
    _, ceo_h = await auth(Role.CEO)
    school = await make_school()
    _, t_h = await _teacher(client, school)

    for h in (t_h, ceo_h):
        assert (await client.post(f"{API}/events", json=_event(), headers=h)).status_code == 403
    ev = (await client.post(f"{API}/events", json=_event(), headers=admin_h)).json()
    for h in (t_h, ceo_h):
        assert (await client.put(f"{API}/events/{ev['id']}", json=_event(), headers=h)).status_code == 403
        assert (await client.delete(f"{API}/events/{ev['id']}", headers=h)).status_code == 403

    upd = await client.put(f"{API}/events/{ev['id']}", json=_event(title="Renamed"), headers=hm_h)
    assert upd.status_code == 200 and upd.json()["title"] == "Renamed"
    assert (await client.delete(f"{API}/events/{ev['id']}", headers=hm_h)).status_code == 204
    assert (await client.delete(f"{API}/events/{ev['id']}", headers=hm_h)).status_code == 404


async def test_event_date_rules(client, auth):
    _, admin_h = await auth(Role.ADMIN)
    bad = await client.post(f"{API}/events", json=_event(end_date="2041-03-09"), headers=admin_h)
    assert bad.status_code == 422 and bad.json()["code"] == "VALIDATION_ERROR"
    assert "end_date" in bad.json()["fields"]["body"]
    ok = await client.post(f"{API}/events", json=_event(), headers=admin_h)
    assert ok.status_code == 201 and ok.json()["end_date"] == "2041-03-10"


async def test_event_range_overlap_and_audience(client, auth):
    _, admin_h = await auth(Role.ADMIN)
    _, ceo_h = await auth(Role.CEO)
    school = await make_school()
    _, t_h = await _teacher(client, school)
    _, s_h = await _student(client, school, school.sec_a)

    span = (
        await client.post(f"{API}/events", json=_event(start_date="2042-06-10", end_date="2042-06-20"), headers=admin_h)
    ).json()
    staff = (
        await client.post(f"{API}/events", json=_event(start_date="2042-06-12", audience="teachers"), headers=admin_h)
    ).json()

    async def ids(h, a, b):
        resp = await client.get(f"{API}/events", params={"from": a, "to": b}, headers=h)
        assert resp.status_code == 200, resp.text
        return {e["id"] for e in resp.json()}

    assert {span["id"], staff["id"]} <= await ids(admin_h, "2042-06-01", "2042-06-30")
    assert span["id"] in await ids(admin_h, "2042-06-20", "2042-06-25")  # overlaps on the last day
    assert span["id"] not in await ids(admin_h, "2042-06-21", "2042-06-25")
    assert span["id"] not in await ids(admin_h, "2042-06-01", "2042-06-09")
    assert staff["id"] in await ids(t_h, "2042-06-12", "2042-06-12")
    assert staff["id"] in await ids(ceo_h, "2042-06-12", "2042-06-12")
    got = await ids(s_h, "2042-06-01", "2042-06-30")
    assert span["id"] in got and staff["id"] not in got


# ------------------------------------------------------------------ calendar
async def _exam(client, h, school, name, start, end=None):
    body = {
        "name": name,
        "type": "Unit Test",
        "academic_year_id": str(school.year.id),
        "class_id": str(school.klass.id),
        "start_date": start,
        "end_date": end,
    }
    resp = await client.post(f"{API}/exams", json=body, headers=h)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_calendar_merges_holidays_events_and_scoped_exams(client, auth):
    _, admin_h = await auth(Role.ADMIN)
    school, other = await make_school(), await make_school()
    _, t_h = await _teacher(client, school)
    _, s_h = await _student(client, school, school.sec_a)
    _, o_h = await _student(client, other, other.sec_a)

    hol_name, ev_title = _title("Hol"), _title("Ev")
    day = "2043-09-15"
    assert (
        await client.post(f"{API}/holidays", json={"date": day, "name": hol_name}, headers=admin_h)
    ).status_code == 201
    assert (
        await client.post(f"{API}/events", json={"title": ev_title, "start_date": day}, headers=admin_h)
    ).status_code == 201
    exam_name, other_name = _title("Exam"), _title("OtherExam")
    exam_id = await _exam(client, admin_h, school, exam_name, "2043-09-16", "2043-09-18")
    await _exam(client, admin_h, other, other_name, "2043-09-17")

    async def items(h):
        resp = await client.get(f"{API}/calendar", params={"from": "2043-09-01", "to": "2043-09-30"}, headers=h)
        assert resp.status_code == 200, resp.text
        return resp.json()

    mine = f"{exam_name} ({school.klass.name})"
    theirs = f"{other_name} ({other.klass.name})"
    for h in (admin_h, t_h, s_h):
        got = {(i["kind"], i["title"]) for i in await items(h)}
        assert {("holiday", hol_name), ("event", ev_title)} <= got
    admin_titles = {i["title"] for i in await items(admin_h)}
    assert {mine, theirs} <= admin_titles
    exam_item = next(i for i in await items(s_h) if i["id"] == exam_id)
    assert (exam_item["kind"], exam_item["start_date"], exam_item["end_date"]) == ("exam", "2043-09-16", "2043-09-18")
    # students see their own class's exams, teachers the classes they teach
    assert {mine} == {i["title"] for i in await items(s_h) if i["kind"] == "exam"} & {mine, theirs}
    assert {mine} == {i["title"] for i in await items(t_h) if i["kind"] == "exam"} & {mine, theirs}
    assert {theirs} == {i["title"] for i in await items(o_h) if i["kind"] == "exam"} & {mine, theirs}
    # an exam with no end date shows as a single day
    single = next(i for i in await items(admin_h) if i["title"] == theirs)
    assert single["start_date"] == single["end_date"] == "2043-09-17"


async def test_calendar_range_is_capped(client, auth):
    _, admin_h = await auth(Role.ADMIN)
    resp = await client.get(f"{API}/calendar", params={"from": "2043-01-01", "to": "2044-03-01"}, headers=admin_h)
    assert resp.status_code == 422 and "to" in resp.json()["fields"]
    resp = await client.get(f"{API}/calendar", params={"from": "2043-01-01", "to": "2043-12-31"}, headers=admin_h)
    assert resp.status_code == 200


async def test_list_notifications_endpoint(client, auth):
    _, hm_h = await auth(Role.HEADMASTER)
    school = await make_school()
    _, a_h = await _student(client, school, school.sec_a)
    ann = await _announce(client, hm_h, **_target(school))
    resp = await client.get(f"{API}/notifications", params={"unread_only": True}, headers=a_h)
    assert resp.status_code == 200
    assert [n["message"] for n in resp.json()["items"]] == [f"Announcement: {ann['title']}"]
