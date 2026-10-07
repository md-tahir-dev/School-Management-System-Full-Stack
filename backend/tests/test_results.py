"""Part E (Results) of the Phase 3 spec, through the real HTTP API."""

import io
import uuid

from pypdf import PdfReader
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import AuditLog, ExamSubject, Result, Role
from tests.conftest import DEFAULT_PASSWORD, login
from tests.helpers import create_student, create_teacher, make_school

API = "/api/v1"


async def new_exam(client, admin_h, school, name=None):
    resp = await client.post(
        f"{API}/exams",
        json={
            "name": name or f"Mid-{uuid.uuid4().hex[:6]}", "type": "Mid Term",
            "academic_year_id": str(school.year.id), "class_id": str(school.klass.id),
        },
        headers=admin_h,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def enter(client, h, exam_id, school, subject, marks: dict, absent=(), reason=None, expect=200):
    """marks: {student_id: obtained}. Enters one subject for the listed students."""
    entries = [
        {"student_id": str(sid), "subject_id": str(subject.id), "obtained_marks": str(m), "is_absent": sid in absent}
        for sid, m in marks.items()
    ]
    body = {"entries": entries}
    if reason:
        body["reason"] = reason
    resp = await client.put(
        f"{API}/exams/{exam_id}/marks", params={"subject_id": str(subject.id), "section_id": str(school.sec_a.id)},
        json=body, headers=h,
    )
    assert resp.status_code == expect, resp.text
    return resp


async def results_of(client, h, exam_id):
    resp = await client.get(f"{API}/exams/{exam_id}/results", params={"page_size": 100}, headers=h)
    assert resp.status_code == 200, resp.text
    return {r["student_id"]: r for r in resp.json()["items"]}


async def scored_class(client, admin_h, percents):
    """One student per percentage; both subjects get the same mark so % == mark."""
    school = await make_school()
    students = [(await create_student(school)).student.id for _ in percents]
    exam = await new_exam(client, admin_h, school)
    for subject in (school.math, school.english):
        await enter(client, admin_h, exam["id"], school, subject, dict(zip(students, percents)))
    return school, students, exam


async def test_create_exam_copies_class_subjects_and_duplicate_is_409_without_breaking_session(client, auth):
    _, admin_h = await auth(Role.ADMIN)
    school = await make_school()
    exam = await new_exam(client, admin_h, school, name="Dup")
    subs = (await client.get(f"{API}/exams/{exam['id']}/subjects", headers=admin_h)).json()
    assert len(subs) == 2 and all(s["total_marks"] == "100.00" for s in subs)

    body = {"name": "Dup", "type": "Mid Term", "academic_year_id": str(school.year.id), "class_id": str(school.klass.id)}
    dup = await client.post(f"{API}/exams", json=body, headers=admin_h)
    assert dup.status_code == 409 and dup.json()["code"] == "EXAM_EXISTS"
    # Regression for the MissingGreenlet bug: requests after a duplicate error must keep working.
    for _ in range(3):
        assert (await client.get(f"{API}/exams", headers=admin_h)).status_code == 200
    ok = await client.post(f"{API}/exams", json={**body, "name": "Not a dup"}, headers=admin_h)
    assert ok.status_code == 201
    # duplicate on update too
    upd = await client.put(f"{API}/exams/{ok.json()['id']}", json=body, headers=admin_h)
    assert upd.status_code == 409 and upd.json()["code"] == "EXAM_EXISTS"
    assert (await client.get(f"{API}/exams", headers=admin_h)).status_code == 200


async def test_obtained_above_total_rejected_and_absent_forces_zero(client, auth):
    _, admin_h = await auth(Role.ADMIN)
    school = await make_school()
    sid = (await create_student(school)).student.id
    exam = await new_exam(client, admin_h, school)
    await enter(client, admin_h, exam["id"], school, school.math, {sid: 101}, expect=422)

    await enter(client, admin_h, exam["id"], school, school.math, {sid: 77}, absent={sid})
    sheet = (
        await client.get(
            f"{API}/exams/{exam['id']}/marks-sheet",
            params={"subject_id": str(school.math.id), "section_id": str(school.sec_a.id)}, headers=admin_h,
        )
    ).json()
    row = sheet["rows"][0]
    assert row["is_absent"] is True and float(row["obtained_marks"]) == 0


async def test_incomplete_result_stays_draft_without_grade_or_rank(client, auth):
    _, admin_h = await auth(Role.ADMIN)
    school = await make_school()
    sid = (await create_student(school)).student.id
    exam = await new_exam(client, admin_h, school)
    await enter(client, admin_h, exam["id"], school, school.math, {sid: 90})
    r = (await results_of(client, admin_h, exam["id"]))[str(sid)]
    assert r["status"] == "draft" and r["rank"] is None

    await enter(client, admin_h, exam["id"], school, school.english, {sid: 90})
    r = (await results_of(client, admin_h, exam["id"]))[str(sid)]
    assert r["status"] == "complete" and r["grade"] == "A+" and r["rank"] == 1


async def test_ties_share_rank_and_marks_change_reranks(client, auth):
    _, admin_h = await auth(Role.ADMIN)
    school, students, exam = await scored_class(client, admin_h, [95, 90, 90, 80])
    got = await results_of(client, admin_h, exam["id"])
    assert [got[str(s)]["rank"] for s in students] == [1, 2, 2, 4]

    # lift the last student to 99 in both subjects -> becomes rank 1, everyone else shifts down
    for subject in (school.math, school.english):
        await enter(client, admin_h, exam["id"], school, subject, {students[3]: 99})
    got = await results_of(client, admin_h, exam["id"])
    assert [got[str(s)]["rank"] for s in students] == [2, 3, 3, 1]


async def test_snapshot_survives_exam_subject_edit(client, auth):
    _, admin_h = await auth(Role.ADMIN)
    school = await make_school()
    sid = (await create_student(school)).student.id
    exam = await new_exam(client, admin_h, school)
    await enter(client, admin_h, exam["id"], school, school.math, {sid: 50})

    new_subjects = [
        {"subject_id": str(school.math.id), "total_marks": "50", "passing_marks": "20"},
        {"subject_id": str(school.english.id), "total_marks": "100", "passing_marks": "40"},
    ]
    assert (await client.put(f"{API}/exams/{exam['id']}/subjects", json=new_subjects, headers=admin_h)).status_code == 200
    async with SessionLocal() as db:
        result = await db.scalar(select(Result).where(Result.student_id == sid))
        from app.models import ResultItem

        item = await db.scalar(select(ResultItem).where(ResultItem.result_id == result.id))
    assert float(item.total_marks) == 100 and float(item.passing_marks) == 40  # history untouched


async def test_fail_rule_setting_changes_overall_result(client, auth):
    _, admin_h = await auth(Role.ADMIN)
    school = await make_school()
    sid = (await create_student(school)).student.id
    exam = await new_exam(client, admin_h, school)
    await enter(client, admin_h, exam["id"], school, school.math, {sid: 95})
    await enter(client, admin_h, exam["id"], school, school.english, {sid: 30})  # fails English (<40)
    r = (await results_of(client, admin_h, exam["id"]))[str(sid)]
    assert r["is_pass"] is False  # default rule: any failed subject fails the student

    await client.put(f"{API}/settings", json={"fail_if_any_subject_failed": False}, headers=admin_h)
    try:
        await enter(client, admin_h, exam["id"], school, school.english, {sid: 30})  # re-save recalculates
        r = (await results_of(client, admin_h, exam["id"]))[str(sid)]
        assert r["is_pass"] is True
    finally:
        await client.put(f"{API}/settings", json={"fail_if_any_subject_failed": True}, headers=admin_h)


async def test_teacher_scope_and_publish_lock_and_admin_reason_audit(client, auth):
    _, admin_h = await auth(Role.ADMIN)
    school = await make_school()
    sid = (await create_student(school)).student.id
    exam = await new_exam(client, admin_h, school)
    _, tname = await create_teacher(school)  # assigned to Math / section A only
    resp = await login(client, tname, DEFAULT_PASSWORD)
    client.cookies.clear()
    teacher_h = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    await enter(client, teacher_h, exam["id"], school, school.english, {sid: 70}, expect=403)  # unassigned subject
    await enter(client, teacher_h, exam["id"], school, school.math, {sid: 70})
    await enter(client, admin_h, exam["id"], school, school.english, {sid: 70})

    assert (await client.post(f"{API}/exams/{exam['id']}/publish", headers=admin_h)).status_code == 200
    await enter(client, teacher_h, exam["id"], school, school.math, {sid: 71}, expect=403)  # locked
    await enter(client, admin_h, exam["id"], school, school.math, {sid: 71}, expect=422)  # reason required
    await enter(client, admin_h, exam["id"], school, school.math, {sid: 71}, reason="Re-check of paper")

    async with SessionLocal() as db:
        logs = (await db.scalars(select(AuditLog).where(AuditLog.entity == "result_item"))).all()
    assert any(l.diff and l.diff.get("reason") == "Re-check of paper" and l.diff["old"] and l.diff["new"] for l in logs)

    # unpublish needs a reason
    assert (await client.post(f"{API}/exams/{exam['id']}/unpublish", json={}, headers=admin_h)).status_code == 422
    assert (
        await client.post(f"{API}/exams/{exam['id']}/unpublish", json={"reason": "Wrong marks"}, headers=admin_h)
    ).status_code == 200


async def test_unpublished_hidden_from_student_parent_ceo_visible_to_admin_teacher(client, auth):
    from tests.test_parent import family, parent_headers

    _, admin_h = await auth(Role.ADMIN)
    _, ceo_h = await auth(Role.CEO)
    school = await make_school()
    username, kids = await family(school, children=1)
    sid = kids[0].student.id
    exam = await new_exam(client, admin_h, school)
    for subject in (school.math, school.english):
        await enter(client, admin_h, exam["id"], school, subject, {sid: 88})
    result_id = (await results_of(client, admin_h, exam["id"]))[str(sid)]["student_id"]
    async with SessionLocal() as db:
        rid = (await db.scalar(select(Result).where(Result.student_id == sid))).id

    parent_h = await parent_headers(client, username)
    assert (await client.get(f"{API}/results/{rid}", headers=parent_h)).status_code == 404
    assert (await client.get(f"{API}/results/{rid}", headers=ceo_h)).status_code == 404
    assert (await client.get(f"{API}/results/{rid}", headers=admin_h)).status_code == 200
    dash = (await client.get(f"{API}/parent/children/{sid}/dashboard", headers=parent_h)).json()
    assert dash["latest_result"] is None

    await client.post(f"{API}/exams/{exam['id']}/publish", headers=admin_h)
    assert (await client.get(f"{API}/results/{rid}", headers=parent_h)).status_code == 200
    assert (await client.get(f"{API}/results/{rid}", headers=ceo_h)).status_code == 200
    dash = (await client.get(f"{API}/parent/children/{sid}/dashboard", headers=parent_h)).json()
    assert dash["latest_result"]["grade"] == "A" and dash["latest_result"]["rank"] == 1
    assert result_id  # student id echoed by the class sheet


async def test_analytics_match_hand_computed_example(client, auth):
    _, admin_h = await auth(Role.ADMIN)
    school, students, exam = await scored_class(client, admin_h, [90, 70, 30])
    a = (await client.get(f"{API}/exams/{exam['id']}/analytics", headers=admin_h)).json()
    assert float(a["class_average"]) == 63.33 and float(a["highest"]) == 90 and float(a["lowest"]) == 30
    assert float(a["pass_percent"]) == 66.67  # 90 and 70 pass; 30 fails
    assert a["grade_distribution"] == {"A+": 1, "B": 1, "F": 1}
    assert a["top_students"][0]["rank"] == 1 and a["complete_count"] == 3


async def test_delete_exam_blocked_with_results_and_allowed_when_empty(client, auth):
    _, admin_h = await auth(Role.ADMIN)
    school, students, exam = await scored_class(client, admin_h, [80])
    assert (await client.delete(f"{API}/exams/{exam['id']}", headers=admin_h)).status_code == 409
    empty = await new_exam(client, admin_h, school, name="Empty")
    assert (await client.delete(f"{API}/exams/{empty['id']}", headers=admin_h)).status_code == 204
    async with SessionLocal() as db:
        assert not (await db.scalars(select(ExamSubject).where(ExamSubject.exam_id == uuid.UUID(empty["id"])))).all()


async def test_pdf_card_draft_watermark_bulk_pdf_and_csv(client, auth):
    _, admin_h = await auth(Role.ADMIN)
    school, students, exam = await scored_class(client, admin_h, [85, 60])
    async with SessionLocal() as db:
        rid = (await db.scalar(select(Result).where(Result.student_id == students[0]))).id

    draft = await client.get(f"{API}/results/{rid}/pdf", headers=admin_h)
    assert draft.status_code == 200 and draft.headers["content-type"] == "application/pdf" and len(draft.content) > 1000
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(draft.content)).pages)
    assert "DRAFT" in text

    await client.post(f"{API}/exams/{exam['id']}/publish", headers=admin_h)
    final = await client.get(f"{API}/results/{rid}/pdf", headers=admin_h)
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(final.content)).pages)
    assert "DRAFT" not in text and "PASS" in text and "1 of 2" in text

    bulk = await client.get(f"{API}/exams/{exam['id']}/results/pdf", headers=admin_h)
    assert bulk.headers["content-type"] == "application/pdf"
    assert len(PdfReader(io.BytesIO(bulk.content)).pages) == 2  # one page per student

    csv = await client.get(f"{API}/exams/{exam['id']}/results/export", params={"format": "csv"}, headers=admin_h)
    assert csv.status_code == 200 and "Rank,Roll No" in csv.text
