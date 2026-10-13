import io
import uuid
import zipfile
from datetime import date
from pathlib import Path

from app.core.config import settings
from app.models import Role
from app.services.storage import sniff_document_type
from app.services.students import LoginOverrides
from tests.conftest import DEFAULT_PASSWORD
from tests.helpers import create_student, create_teacher, make_school
from tests.test_attendance import auth_as_existing
from tests.test_parent import family, parent_headers

API = "/api/v1"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
TODAY = date.today().isoformat()


def _docx(with_types=True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if with_types:
            z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


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


def _entry(school, section="a", subject="math", **over):
    body = {
        "class_id": str(school.klass.id),
        "section_id": str(getattr(school, f"sec_{section}").id) if section else None,
        "subject_id": str(getattr(school, subject).id) if subject else None,
        "date": TODAY,
        "title": "Chapter 1",
        "body": "Read it",
    }
    body.update(over)
    return body


async def _post(client, h, body, status=201):
    resp = await client.post(f"{API}/diary", json=body, headers=h)
    assert resp.status_code == status, resp.text
    return resp.json()


async def _diary(client, h, **params):
    resp = await client.get(f"{API}/diary", params={"date": TODAY, **params}, headers=h)
    assert resp.status_code == 200, resp.text
    return [e["id"] for e in resp.json()]


# ------------------------------------------------------------------ diary scope and writes
async def test_diary_visibility_and_write_scope(client):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    entry = await _post(client, t_h, _entry(school))
    eid = entry["id"]
    assert entry["can_edit"] is True and entry["subject_name"] == school.math.name

    _, a_h = await _student(client, school, school.sec_a)
    _, b_h = await _student(client, school, school.sec_b)
    assert await _diary(client, a_h) == [eid]
    assert await _diary(client, b_h) == []

    username, kids = await family(school, children=1)
    p_h = await parent_headers(client, username)
    assert await _diary(client, p_h, student_id=str(kids[0].student.id)) == [eid]
    resp = await client.get(f"{API}/diary", params={"date": TODAY}, headers=p_h)
    assert resp.status_code == 422 and "student_id" in resp.json()["fields"]

    # a teacher of another class cannot see, edit or delete it
    other = await make_school()
    _, o_h = await _teacher(client, other)
    assert (await client.put(f"{API}/diary/{eid}", json=_entry(other), headers=o_h)).status_code == 404
    assert (await client.delete(f"{API}/diary/{eid}", headers=o_h)).status_code == 404

    # teaches math only, not english
    resp = await client.post(f"{API}/diary", json=_entry(school, subject="english"), headers=t_h)
    assert resp.status_code == 404
    # a teacher must name a section when the class has sections
    resp = await client.post(f"{API}/diary", json=_entry(school, section=None), headers=t_h)
    assert resp.status_code == 422 and "section_id" in resp.json()["fields"]


async def test_general_note_needs_class_teacher(client, auth):
    school = await make_school()
    _, admin_h = await auth(Role.ADMIN)
    _, hm_h = await auth(Role.HEADMASTER)
    reg, t_h = await _teacher(client, school)
    note = _entry(school, subject=None)
    resp = await client.post(f"{API}/diary", json=note, headers=t_h)
    assert resp.status_code == 422 and "subject_id" in resp.json()["fields"]

    body = {"class_id": str(school.klass.id), "section_id": str(school.sec_a.id), "teacher_id": str(reg.teacher.id)}
    assert (await client.put(f"{API}/class-teachers", json=body, headers=admin_h)).status_code == 204
    assert (await _post(client, t_h, note))["subject_id"] is None
    assert (await _post(client, hm_h, note))["subject_id"] is None
    assert (await _post(client, hm_h, _entry(school, section=None, subject="english")))["section_id"] is None


async def test_only_author_or_manager_edits(client, auth):
    school = await make_school()
    _, hm_h = await auth(Role.HEADMASTER)
    _, author_h = await _teacher(client, school)
    _, second_h = await _teacher(client, school)
    entry = await _post(client, author_h, _entry(school))
    eid = entry["id"]

    assert eid in await _diary(client, second_h)
    resp = await client.put(f"{API}/diary/{eid}", json=_entry(school, title="Hacked"), headers=second_h)
    assert resp.status_code == 403
    assert (await client.delete(f"{API}/diary/{eid}", headers=second_h)).status_code == 403
    listed = (await client.get(f"{API}/diary", params={"date": TODAY}, headers=second_h)).json()
    assert listed[0]["can_edit"] is False

    resp = await client.put(f"{API}/diary/{eid}", json=_entry(school, title="Fixed"), headers=hm_h)
    assert resp.status_code == 200 and resp.json()["title"] == "Fixed"


async def test_diary_without_due_date(client):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    assert (await _post(client, t_h, _entry(school)))["due_date"] is None


async def test_due_date_before_entry_date_is_rejected(client):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    resp = await client.post(f"{API}/diary", json=_entry(school, date=TODAY, due_date="2020-01-01"), headers=t_h)
    assert resp.status_code == 422 and resp.json()["code"] == "VALIDATION_ERROR"
    assert "due_date" in resp.json()["fields"]["body"]  # cross-field rule is keyed to the whole body


async def test_attachment_upload_and_removal(client):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    eid = (await _post(client, t_h, _entry(school)))["id"]
    url = f"{API}/diary/{eid}/attachment"
    ok = await client.put(url, headers=t_h, files={"file": ("w.pdf", PDF, "application/pdf")})
    assert ok.status_code == 200 and ok.json()["attachment_url"].endswith(".pdf")
    assert (await client.put(url, headers=t_h)).json()["attachment_url"] is None


# ------------------------------------------------------------------ submissions
async def test_submission_flow(client):
    school = await make_school()
    reg, t_h = await _teacher(client, school)
    plain = await _post(client, t_h, _entry(school))
    work = await _post(client, t_h, _entry(school, submission_required=True, due_date=TODAY))

    a_reg, a_h = await _student(client, school, school.sec_a)
    b_reg, b_h = await _student(client, school, school.sec_b)
    pdf = {"file": ("hw.pdf", PDF, "application/pdf")}

    resp = await client.post(f"{API}/diary/{plain['id']}/submission", headers=a_h, files=pdf)
    assert resp.status_code == 409 and resp.json()["code"] == "SUBMISSION_NOT_REQUIRED"

    url = f"{API}/diary/{work['id']}/submission"
    first = await client.post(url, headers=a_h, files=pdf, data={"note": "done"})
    assert first.status_code == 200 and first.json()["file_url"].endswith(".pdf") and first.json()["late"] is False
    again = await client.post(url, headers=a_h, data={"note": "second try"})
    assert (
        again.status_code == 200 and again.json()["id"] == first.json()["id"] and again.json()["note"] == "second try"
    )
    # an empty submission is refused with a field error
    resp = await client.post(url, headers=a_h)
    assert resp.status_code == 422 and "file" in resp.json()["fields"]

    # sections: student of B can't see the entry; parent can't submit
    assert (await client.post(url, headers=b_h, files=pdf)).status_code == 404
    username, kids = await family(school, children=1)
    p_h = await parent_headers(client, username)
    assert (await client.post(url, headers=p_h, files=pdf)).status_code == 403

    # the teacher sees the whole active roster, with null where nothing was handed in
    other = await _student(client, school, school.sec_a)
    rows = (await client.get(f"{API}/diary/{work['id']}/submissions", headers=t_h)).json()
    by_student = {r["student_id"]: r["submission"] for r in rows}
    assert str(a_reg.student.id) in by_student and by_student[str(a_reg.student.id)]["id"] == first.json()["id"]
    assert str(other[0].student.id) in by_student and by_student[str(other[0].student.id)] is None
    assert str(b_reg.student.id) not in by_student and str(kids[0].student.id) in by_student

    # checking locks the work
    check = await client.put(
        f"{API}/diary/submissions/{first.json()['id']}", json={"checked": True, "remarks": "Good"}, headers=t_h
    )
    assert check.status_code == 200 and check.json()["checked"] is True and check.json()["remarks"] == "Good"
    resp = await client.post(url, headers=a_h, data={"note": "late edit"})
    assert resp.status_code == 409 and resp.json()["code"] == "ALREADY_CHECKED"


async def test_late_submission_is_flagged(client):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    past = await _post(client, t_h, _entry(school, date="2025-01-01", submission_required=True, due_date="2025-01-02"))
    _, a_h = await _student(client, school, school.sec_a)
    resp = await client.post(f"{API}/diary/{past['id']}/submission", headers=a_h, data={"note": "sorry"})
    assert resp.status_code == 200 and resp.json()["late"] is True


async def test_other_teacher_cannot_check_a_submission(client):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    work = await _post(client, t_h, _entry(school, submission_required=True))
    _, a_h = await _student(client, school, school.sec_a)
    sub = (await client.post(f"{API}/diary/{work['id']}/submission", headers=a_h, data={"note": "x"})).json()
    other = await make_school()
    _, o_h = await _teacher(client, other)
    resp = await client.put(f"{API}/diary/submissions/{sub['id']}", json={"checked": True}, headers=o_h)
    assert resp.status_code == 404


# ------------------------------------------------------------------ uploads
async def test_upload_type_sniffing(client):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    eid = (await _post(client, t_h, _entry(school)))["id"]
    url = f"{API}/diary/{eid}/attachment"

    for name, data in (
        ("run.exe", b"MZ\x90\x00" + b"\x00" * 50),
        ("x.pdf", b"random bytes"),
        ("fake.docx", _docx(False)),
    ):
        resp = await client.put(url, headers=t_h, files={"file": (name, data, "application/octet-stream")})
        assert resp.status_code == 422, name
        assert resp.json()["code"] == "INVALID_FILE_TYPE" and "file" in resp.json()["fields"]
    # a zip without [Content_Types].xml is not an Office file
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "x")
    resp = await client.put(url, headers=t_h, files={"file": ("a.docx", buf.getvalue(), "application/zip")})
    assert resp.status_code == 422 and resp.json()["code"] == "INVALID_FILE_TYPE"

    ok = await client.put(url, headers=t_h, files={"file": ("a.bin", _docx(), "application/octet-stream")})
    assert ok.status_code == 200 and ok.json()["attachment_url"].endswith(".docx")


def test_sniff_document_type():
    assert sniff_document_type(PDF) == "pdf"
    assert sniff_document_type(_docx()) == "docx"
    assert sniff_document_type(b"PK\x03\x04garbage") is None
    assert sniff_document_type(b"") is None


async def test_oversized_document_is_413(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_document_bytes", 100)
    school = await make_school()
    _, t_h = await _teacher(client, school)
    eid = (await _post(client, t_h, _entry(school)))["id"]
    resp = await client.put(
        f"{API}/diary/{eid}/attachment", headers=t_h, files={"file": ("big.pdf", PDF + b"0" * 200, "application/pdf")}
    )
    assert resp.status_code == 413 and resp.json()["code"] == "FILE_TOO_LARGE"


# ------------------------------------------------------------------ materials
def _material(school, **over):
    data = {
        "title": "Notes",
        "type": "notes",
        "class_id": str(school.klass.id),
        "section_id": str(school.sec_a.id),
        "subject_id": str(school.math.id),
    }
    data.update(over)
    return {k: v for k, v in data.items() if v is not None}


async def test_material_create_validation(client):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    url = f"{API}/materials"
    pdf = {"file": ("n.pdf", PDF, "application/pdf")}

    ok = await client.post(url, data=_material(school), files=pdf, headers=t_h)
    assert ok.status_code == 201 and ok.json()["file_url"].endswith(".pdf") and ok.json()["can_edit"] is True
    link = await client.post(url, data=_material(school, external_link="https://example.com/v"), headers=t_h)
    assert link.status_code == 201 and link.json()["external_link"] == "https://example.com/v"

    none = await client.post(url, data=_material(school), headers=t_h)
    assert none.status_code == 422 and "file" in none.json()["fields"]
    bad = await client.post(url, data=_material(school, external_link="ftp://x.org/f"), headers=t_h)
    assert bad.status_code == 422 and "external_link" in bad.json()["fields"]
    nosubject = await client.post(url, data=_material(school, subject_id=None), files=pdf, headers=t_h)
    assert nosubject.status_code == 422 and "subject_id" in nosubject.json()["fields"]


async def test_material_listing_filters_and_delete(client, auth):
    school = await make_school()
    _, hm_h = await auth(Role.HEADMASTER)
    _, t_h = await _teacher(client, school)
    _, other_h = await _teacher(client, school)
    link = {"external_link": "https://example.com/a"}
    notes = (await client.post(f"{API}/materials", data=_material(school, **link), headers=t_h)).json()
    # the headmaster may post for english, which the teacher does not teach
    book = await client.post(
        f"{API}/materials",
        data=_material(school, type="reference", subject_id=str(school.english.id), **link),
        headers=hm_h,
    )
    assert book.status_code == 201, book.text

    _, a_h = await _student(client, school, school.sec_a)
    _, b_h = await _student(client, school, school.sec_b)
    got = (await client.get(f"{API}/materials", headers=a_h)).json()
    assert {m["id"] for m in got["items"]} == {notes["id"], book.json()["id"]} or notes["id"] in {
        m["id"] for m in got["items"]
    }
    assert (await client.get(f"{API}/materials", headers=b_h)).json()["items"] == []

    username, kids = await family(school, children=1)
    p_h = await parent_headers(client, username)
    assert (await client.get(f"{API}/materials", headers=p_h)).status_code == 422
    resp = await client.get(f"{API}/materials", params={"student_id": str(kids[0].student.id)}, headers=p_h)
    assert notes["id"] in {m["id"] for m in resp.json()["items"]}

    by_subject = await client.get(f"{API}/materials", params={"subject_id": str(school.math.id)}, headers=a_h)
    assert [m["id"] for m in by_subject.json()["items"]] == [notes["id"]]
    by_type = await client.get(f"{API}/materials", params={"type": "reference"}, headers=a_h)
    assert [m["id"] for m in by_type.json()["items"]] == [book.json()["id"]]

    assert (await client.delete(f"{API}/materials/{notes['id']}", headers=other_h)).status_code == 403
    assert (await client.delete(f"{API}/materials/{notes['id']}", headers=t_h)).status_code == 204
    ids = {m["id"] for m in (await client.get(f"{API}/materials", headers=a_h)).json()["items"]}
    assert notes["id"] not in ids


# ------------------------------------------------------------------ file downloads
async def test_uploaded_documents_need_login_and_row_scope(client, auth):
    school = await make_school()
    _, t_h = await _teacher(client, school)
    work = await _post(client, t_h, _entry(school, submission_required=True))
    pdf = {"file": ("w.pdf", PDF, "application/pdf")}
    att = (await client.put(f"{API}/diary/{work['id']}/attachment", headers=t_h, files=pdf)).json()["attachment_url"]
    mat = (await client.post(f"{API}/materials", data=_material(school), files=pdf, headers=t_h)).json()["file_url"]

    # student A (sec a) with a parent login; A hands in homework
    s_user, p_user = f"s{uuid.uuid4().hex[:8]}", f"parent-{uuid.uuid4().hex[:8]}"
    await create_student(
        school,
        section_id=str(school.sec_a.id),
        create_student_login=True,
        logins=LoginOverrides(student=(s_user, DEFAULT_PASSWORD), parent=(p_user, DEFAULT_PASSWORD)),
    )
    a_h, p_h = await auth_as_existing(client, s_user), await parent_headers(client, p_user)
    hw = (await client.post(f"{API}/diary/{work['id']}/submission", headers=a_h, files=pdf)).json()["file_url"]
    assert all(u.startswith(f"{API}/uploads/") for u in (att, mat, hw))  # stored URLs unchanged

    _, a2_h = await _student(client, school, school.sec_a)  # classmate
    _, b_h = await _student(client, school, school.sec_b)  # other section
    _, other_t_h = await _teacher(client, await make_school())
    _, hm_h = await auth(Role.HEADMASTER)

    expect = {
        "anon": ({}, 401, 401, 401),
        "student": (a_h, 200, 200, 200),
        "parent": (p_h, 200, 200, 200),
        "classmate": (a2_h, 200, 200, 404),
        "other section": (b_h, 404, 404, 404),
        "teacher": (t_h, 200, 200, 200),
        "other school teacher": (other_t_h, 404, 404, 404),
        "headmaster": (hm_h, 200, 200, 200),
    }
    wrong = []
    for who, (h, *codes) in expect.items():
        for url, code in zip((att, mat, hw), codes, strict=True):
            resp = await client.get(url, headers=h)
            if resp.status_code != code:
                wrong.append(f"{who} {url.split('/')[-2]}: {resp.status_code} != {code}")
    assert not wrong, wrong

    ok = await client.get(hw, headers=a_h)
    assert ok.content == PDF and ok.headers["content-disposition"].startswith("attachment")
    assert ok.headers["content-security-policy"] == "sandbox" and ok.headers["x-content-type-options"] == "nosniff"

    # no static fallback for private folders; photos/logos stay public
    name = hw.rsplit("/", 1)[1]
    for path in (f"{API}/uploads//homework/{name}", f"{API}/uploads/photos/..%2Fhomework/{name}"):
        assert (await client.get(path)).status_code == 404, path
    assert (await client.get(f"{API}/uploads/homework/..%2F..%2Fx.pdf", headers=a_h)).status_code == 404
    assert (await client.get(f"{API}/uploads/photos/{name}", headers=a_h)).status_code == 404
    photos = Path(settings.upload_dir) / "photos"
    (photos / f"{'a' * 32}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    assert (await client.get(f"{API}/uploads/photos/{'a' * 32}.png")).status_code == 200
