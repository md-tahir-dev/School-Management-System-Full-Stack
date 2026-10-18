import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.db.session import SessionLocal
from app.models import Attempt, OnlineTest, Role
from app.services.students import LoginOverrides
from tests.conftest import DEFAULT_PASSWORD
from tests.helpers import create_student, create_teacher, make_school
from tests.test_attendance import auth_as_existing
from tests.test_parent import family, parent_headers

API = "/api/v1/tests"


def _now():
    return datetime.now(UTC)


async def _student(client, school, section):
    username = f"s{uuid.uuid4().hex[:8]}"
    reg = await create_student(
        school,
        section_id=str(section.id),
        create_student_login=True,
        logins=LoginOverrides(student=(username, DEFAULT_PASSWORD)),
    )
    return reg, await auth_as_existing(client, username)


async def _teacher(client, school, **kw):
    reg, username = await create_teacher(school, **kw)
    return reg, await auth_as_existing(client, username)


def _body(school, section="a", **over):
    body = {
        "title": "Quiz",
        "subject_id": str(school.math.id),
        "class_id": str(school.klass.id),
        "section_id": str(getattr(school, f"sec_{section}").id),
        "time_limit_min": 30,
        "start_at": (_now() - timedelta(minutes=1)).isoformat(),
        "end_at": (_now() + timedelta(hours=1)).isoformat(),
    }
    body.update(over)
    return body


MCQ = {"type": "mcq", "text": "2+2?", "options": ["3", "4"], "correct_answer": "4", "marks": "2"}
TF = {"type": "tf", "text": "Sky is green", "correct_answer": "false", "marks": "1"}
SHORT = {"type": "short", "text": "Capital of France?", "correct_answer": "Paris", "marks": "2"}
ESSAY = {"type": "short", "text": "Explain", "model_answer": "Because", "marks": "5"}


async def _create(client, h, school, status=201, **over):
    resp = await client.post(API, json=_body(school, **over), headers=h)
    assert resp.status_code == status, resp.text
    return resp.json()


async def _publish(client, h, school, questions, **over):
    t = await _create(client, h, school, **over)
    resp = await client.put(f"{API}/{t['id']}/questions", json={"questions": questions}, headers=h)
    assert resp.status_code == 200, resp.text
    resp = await client.post(f"{API}/{t['id']}/publish", headers=h)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _start(client, h, tid):
    resp = await client.post(f"{API}/{tid}/start", headers=h)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _qid(test, text):
    return next(q["id"] for q in test["questions"] if q["text"] == text)


async def _save_essay(client, h, test, aid):
    body = {"answers": [{"question_id": _qid(test, ESSAY["text"]), "answer": "x"}]}
    assert (await client.put(f"{API}/attempts/{aid}/answers", json=body, headers=h)).status_code == 200


async def _set_attempt(aid, **vals):
    async with SessionLocal() as db:
        a = await db.get(Attempt, uuid.UUID(aid))
        for k, v in vals.items():
            setattr(a, k, v)
        await db.commit()


async def _setup(client, questions=(MCQ, TF, SHORT, ESSAY)):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    test = await _publish(client, t_h, school, list(questions))
    reg, s_h = await _student(client, school, school.sec_a)
    return school, t_h, test, reg, s_h


# ------------------------------------------------------------------ create / validation
async def test_create_scope_and_window(client):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    t = await _create(client, t_h, school)
    assert t["status"] == "draft" and t["can_edit"] is True
    await _create(client, t_h, school, status=404, section="b")
    resp = await client.post(API, json=_body(school, end_at=(_now() - timedelta(hours=1)).isoformat()), headers=t_h)
    assert resp.status_code == 422 and resp.json()["code"] == "VALIDATION_ERROR"
    assert "body" in resp.json()["fields"] and "end_at" in resp.json()["fields"]["body"]


@pytest.mark.parametrize(
    "q",
    [
        {**MCQ, "options": ["4"]},
        {**MCQ, "options": ["4", "4"]},
        {**MCQ, "correct_answer": "5"},
        {**TF, "correct_answer": "maybe"},
    ],
)
async def test_question_validation(client, q):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    t = await _create(client, t_h, school)
    resp = await client.put(f"{API}/{t['id']}/questions", json={"questions": [q]}, headers=t_h)
    assert resp.status_code == 422 and resp.json()["code"] == "VALIDATION_ERROR" and resp.json()["fields"]


async def test_put_questions_replaces_and_published_is_locked(client):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    t = await _create(client, t_h, school)
    url = f"{API}/{t['id']}/questions"
    await client.put(url, json={"questions": [MCQ, TF]}, headers=t_h)
    resp = await client.put(url, json={"questions": [SHORT]}, headers=t_h)
    assert [q["text"] for q in resp.json()["questions"]] == [SHORT["text"]]
    assert resp.json()["total_marks"] == "2.00" or float(resp.json()["total_marks"]) == 2

    assert (await client.post(f"{API}/{t['id']}/publish", headers=t_h)).status_code == 200
    for r in (
        await client.put(url, json={"questions": [MCQ]}, headers=t_h),
        await client.put(f"{API}/{t['id']}", json=_body(school), headers=t_h),
    ):
        assert r.status_code == 409 and r.json()["code"] == "NOT_DRAFT"


async def test_publish_needs_questions_and_future_end(client):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    t = await _create(client, t_h, school)
    resp = await client.post(f"{API}/{t['id']}/publish", headers=t_h)
    assert resp.status_code == 422 and "questions" in resp.json()["fields"]

    await client.put(f"{API}/{t['id']}/questions", json={"questions": [MCQ]}, headers=t_h)
    async with SessionLocal() as db:
        row = await db.get(OnlineTest, uuid.UUID(t["id"]))
        row.end_at = _now() - timedelta(minutes=5)
        await db.commit()
    resp = await client.post(f"{API}/{t['id']}/publish", headers=t_h)
    assert resp.status_code == 422 and "end_at" in resp.json()["fields"]


async def test_delete_blocked_by_attempts(client):
    school, t_h, test, _, s_h = await _setup(client)
    await _start(client, s_h, test["id"])
    resp = await client.delete(f"{API}/{test['id']}", headers=t_h)
    assert resp.status_code == 409 and resp.json()["code"] == "HAS_ATTEMPTS"
    draft = await _create(client, t_h, school)
    assert (await client.delete(f"{API}/{draft['id']}", headers=t_h)).status_code == 204


# ------------------------------------------------------------------ visibility
async def test_visibility(client, auth):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    draft = await _create(client, t_h, school, title="Hidden")
    test = await _publish(client, t_h, school, [MCQ], title="Shown")
    _, a_h = await _student(client, school, school.sec_a)
    _, b_h = await _student(client, school, school.sec_b)

    async def mine(h, **params):
        resp = await client.get(f"{API}/me", params=params, headers=h)
        assert resp.status_code == 200, resp.text
        return {t["id"] for t in resp.json()}

    ids = await mine(a_h)
    assert test["id"] in ids and draft["id"] not in ids
    assert test["id"] not in await mine(b_h)

    for sec, expect in (("a", True), ("b", False)):
        username = f"parent-{uuid.uuid4().hex[:8]}"
        kid = await create_student(
            school,
            section_id=str(getattr(school, f"sec_{sec}").id),
            logins=LoginOverrides(parent=(username, DEFAULT_PASSWORD)),
        )
        p_h = await parent_headers(client, username)
        assert (await client.get(f"{API}/me", headers=p_h)).status_code == 422
        assert (test["id"] in await mine(p_h, student_id=str(kid.student.id))) is expect

    _, o_h = await _teacher(client, await make_school())
    assert (await client.get(f"{API}/{test['id']}", headers=o_h)).status_code == 404

    _, ceo_h = await auth(Role.CEO)
    listed = await client.get(f"{API}", params={"class_id": str(school.klass.id), "page_size": 100}, headers=ceo_h)
    got = {t["id"] for t in listed.json()["items"]}
    assert test["id"] in got and draft["id"] not in got


# ------------------------------------------------------------------ attempt flow
async def test_start_hides_key_and_resumes(client):
    _, _, test, _, s_h = await _setup(client)
    v = await _start(client, s_h, test["id"])
    text = str(v)
    assert "correct_answer" not in text and "model_answer" not in text
    assert len(v["questions"]) == 4
    again = await _start(client, s_h, test["id"])
    assert again["attempt_id"] == v["attempt_id"]
    got = await client.get(f"{API}/attempts/{v['attempt_id']}", headers=s_h)
    assert got.status_code == 200 and "correct_answer" not in got.text


async def test_start_guards(client):
    school, t_h, test, _, s_h = await _setup(client)
    _, b_h = await _student(client, school, school.sec_b)
    assert (await client.post(f"{API}/{test['id']}/start", headers=b_h)).status_code == 404
    assert (await client.post(f"{API}/{test['id']}/start", headers=t_h)).status_code == 403
    username, _ = await family(school, children=1)
    p_h = await parent_headers(client, username)
    assert (await client.post(f"{API}/{test['id']}/start", headers=p_h)).status_code == 403

    future = await _publish(
        client,
        t_h,
        school,
        [MCQ],
        start_at=(_now() + timedelta(hours=1)).isoformat(),
        end_at=(_now() + timedelta(hours=2)).isoformat(),
    )
    resp = await client.post(f"{API}/{future['id']}/start", headers=s_h)
    assert resp.status_code == 409 and resp.json()["code"] == "NOT_OPEN"


async def test_submit_marking_grading_release(client):
    school, t_h, test, _, s_h = await _setup(client)
    v = await _start(client, s_h, test["id"])
    aid = v["attempt_id"]
    answers = [
        {"question_id": _qid(test, MCQ["text"]), "answer": "4"},
        {"question_id": _qid(test, TF["text"]), "answer": "true"},
        {"question_id": _qid(test, SHORT["text"]), "answer": "  paris "},
        {"question_id": _qid(test, ESSAY["text"]), "answer": "my essay"},
    ]
    saved = await client.put(f"{API}/attempts/{aid}/answers", json={"answers": answers}, headers=s_h)
    assert saved.status_code == 200 and len(saved.json()["answers"]) == 4

    res = await client.post(f"{API}/attempts/{aid}/submit", headers=s_h)
    assert res.status_code == 200
    r = res.json()
    assert r["status"] == "submitted" and r["score"] is None and r["answers"] == [] and r["released"] is False

    rows = (await client.get(f"{API}/{test['id']}/attempts", headers=t_h)).json()
    assert rows[0]["needs_grading"] == 1 and rows[0]["status"] == "submitted"
    teacher_view = (await client.get(f"{API}/attempts/{aid}/result", headers=t_h)).json()
    assert float(teacher_view["score"]) == 4  # mcq 2 + short 2, tf wrong 0

    essay = _qid(test, ESSAY["text"])
    bad = await client.put(f"{API}/attempts/{aid}/grade", json={"marks": {essay: "6"}}, headers=t_h)
    assert bad.status_code == 422 and essay in bad.json()["fields"]

    ok = await client.put(f"{API}/attempts/{aid}/grade", json={"marks": {essay: "3.5"}}, headers=t_h)
    assert ok.status_code == 200 and ok.json()["status"] == "graded" and float(ok.json()["score"]) == 7.5

    hidden = (await client.get(f"{API}/attempts/{aid}/result", headers=s_h)).json()
    assert hidden["score"] is None and hidden["answers"] == []

    assert (await client.post(f"{API}/{test['id']}/release", headers=t_h)).status_code == 200
    shown = (await client.get(f"{API}/attempts/{aid}/result", headers=s_h)).json()
    assert float(shown["score"]) == 7.5 and len(shown["answers"]) == 4
    by_text = {a["text"]: a for a in shown["answers"]}
    assert by_text[TF["text"]]["correct_answer"] == "false"
    assert float(by_text[TF["text"]]["marks_awarded"]) == 0


# ------------------------------------------------------------------ deadline
async def test_save_after_deadline_expires_attempt(client):
    school, t_h, test, _, s_h = await _setup(client)
    aid = (await _start(client, s_h, test["id"]))["attempt_id"]
    mcq = _qid(test, MCQ["text"])
    ok = await client.put(
        f"{API}/attempts/{aid}/answers",
        json={
            "answers": [{"question_id": mcq, "answer": "4"}, {"question_id": _qid(test, ESSAY["text"]), "answer": "x"}]
        },
        headers=s_h,
    )
    assert ok.status_code == 200
    await _set_attempt(aid, expires_at=_now() - timedelta(minutes=2))
    late = await client.put(
        f"{API}/attempts/{aid}/answers", json={"answers": [{"question_id": mcq, "answer": "3"}]}, headers=s_h
    )
    assert late.status_code == 409 and late.json()["code"] == "TIME_UP"
    res = await client.post(f"{API}/attempts/{aid}/submit", headers=s_h)
    assert res.json()["status"] == "expired"
    staff = (await client.get(f"{API}/attempts/{aid}/result", headers=t_h)).json()
    assert float(staff["score"]) == 2  # the saved (correct) answer was scored, the late one ignored


async def test_submit_after_expiry_ignores_body(client):
    _, t_h, test, _, s_h = await _setup(client)
    aid = (await _start(client, s_h, test["id"]))["attempt_id"]
    await _save_essay(client, s_h, test, aid)
    await _set_attempt(aid, expires_at=_now() - timedelta(minutes=2))
    body = {"answers": [{"question_id": _qid(test, MCQ["text"]), "answer": "4"}]}
    res = await client.post(f"{API}/attempts/{aid}/submit", json=body, headers=s_h)
    assert res.status_code == 200 and res.json()["status"] == "expired"
    staff = (await client.get(f"{API}/attempts/{aid}/result", headers=t_h)).json()
    assert float(staff["score"]) == 0


async def test_close_expires_in_progress_attempts(client):
    _, t_h, test, _, s_h = await _setup(client)
    aid = (await _start(client, s_h, test["id"]))["attempt_id"]
    await _save_essay(client, s_h, test, aid)
    resp = await client.post(f"{API}/{test['id']}/close", headers=t_h)
    assert resp.status_code == 200 and resp.json()["status"] == "closed"
    rows = (await client.get(f"{API}/{test['id']}/attempts", headers=t_h)).json()
    assert [r["status"] for r in rows if r["attempt_id"] == aid] == ["expired"]


# ------------------------------------------------------------------ ownership
async def test_other_student_cannot_touch_attempt(client):
    school, _, test, _, s_h = await _setup(client)
    aid = (await _start(client, s_h, test["id"]))["attempt_id"]
    _, other_h = await _student(client, school, school.sec_a)
    mcq = _qid(test, MCQ["text"])
    assert (await client.get(f"{API}/attempts/{aid}", headers=other_h)).status_code == 404
    put = await client.put(
        f"{API}/attempts/{aid}/answers", json={"answers": [{"question_id": mcq, "answer": "4"}]}, headers=other_h
    )
    assert put.status_code == 404
    assert (await client.post(f"{API}/attempts/{aid}/submit", headers=other_h)).status_code == 404
    assert (await client.get(f"{API}/attempts/{aid}/result", headers=other_h)).status_code == 404


async def test_parent_reads_only_own_childs_result(client):
    school = await make_school()
    username, kids = await family(school, children=1)
    p_h = await parent_headers(client, username)
    _, _, test, _, s_h = await _setup(client)
    aid = (await _start(client, s_h, test["id"]))["attempt_id"]
    await client.post(f"{API}/attempts/{aid}/submit", headers=s_h)
    resp = await client.get(f"{API}/attempts/{aid}/result", params={"student_id": str(kids[0].student.id)}, headers=p_h)
    assert resp.status_code == 404
