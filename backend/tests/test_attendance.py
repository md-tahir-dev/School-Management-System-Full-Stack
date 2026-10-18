"""Part E (Attendance) of the Phase 3 spec.

Note: `date.today()` in this environment can genuinely fall on a Sunday (the default weekly-off day),
so tests that aren't specifically about the weekly-off rule use `school_day()` to pick a weekday
instead of assuming "today" is markable.
"""

from datetime import date, timedelta

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Attendance, Notification, Role, SchoolHoliday, Student
from app.models.enums import StudentStatus
from app.services.settings import get_school_settings
from tests.conftest import DEFAULT_PASSWORD, login
from tests.helpers import create_student, create_teacher, make_school


def _old_admission():
    return (date.today() - timedelta(days=120)).isoformat()


API = "/api/v1"


def school_day(base: date | None = None, days_back: int = 1) -> date:
    """A weekday (not Sunday) at least `days_back` days before `base` (default: today)."""
    d = (base or date.today()) - timedelta(days=days_back)
    while d.isoweekday() == 7:
        d -= timedelta(days=1)
    return d


async def auth_as_existing(client, username):
    resp = await login(client, username, DEFAULT_PASSWORD)
    assert resp.status_code == 200, resp.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_roster_excludes_inactive_deleted_and_not_yet_admitted(client, auth):
    school = await make_school()
    day = school_day()
    active = await create_student(school, admission_date=_old_admission())
    inactive = await create_student(school, admission_date=_old_admission())
    deleted = await create_student(school, admission_date=_old_admission())
    future_admit = await create_student(school, admission_date=(day + timedelta(days=5)).isoformat())

    async with SessionLocal() as db:
        s = await db.get(Student, inactive.student.id)
        s.status = StudentStatus.INACTIVE
        d = await db.get(Student, deleted.student.id)
        d.is_deleted = True
        await db.commit()

    _, admin_h = await auth(Role.ADMIN)
    resp = await client.get(
        f"{API}/attendance",
        params={"class_id": str(school.klass.id), "section_id": str(school.sec_a.id), "date": day.isoformat()},
        headers=admin_h,
    )
    assert resp.status_code == 200
    ids = {row["student_id"] for row in resp.json()["students"]}
    assert str(active.student.id) in ids
    assert str(inactive.student.id) not in ids
    assert str(deleted.student.id) not in ids
    assert str(future_admit.student.id) not in ids


async def test_bulk_save_upserts_never_duplicates(client, auth):
    school = await make_school()
    s1 = await create_student(school, admission_date=_old_admission())
    _, admin_h = await auth(Role.ADMIN)
    day = school_day().isoformat()
    body = {
        "class_id": str(school.klass.id),
        "section_id": str(school.sec_a.id),
        "date": day,
        "records": [{"student_id": str(s1.student.id), "status": "present"}],
    }
    r1 = await client.post(f"{API}/attendance/bulk", json=body, headers=admin_h)
    assert r1.status_code == 200, r1.text

    body["records"][0]["status"] = "late"
    r2 = await client.post(f"{API}/attendance/bulk", json=body, headers=admin_h)
    assert r2.status_code == 200

    async with SessionLocal() as db:
        rows = (await db.scalars(select(Attendance).where(Attendance.student_id == s1.student.id))).all()
    assert len(rows) == 1
    assert rows[0].status.value == "late"


async def test_rejects_future_date_holiday_and_weekly_off(client, auth):
    school = await make_school()
    s1 = await create_student(school, admission_date=_old_admission())
    _, admin_h = await auth(Role.ADMIN)

    future = (date.today() + timedelta(days=3)).isoformat()
    body = {
        "class_id": str(school.klass.id),
        "section_id": str(school.sec_a.id),
        "date": future,
        "records": [{"student_id": str(s1.student.id), "status": "present"}],
    }
    resp = await client.post(f"{API}/attendance/bulk", json=body, headers=admin_h)
    assert resp.status_code == 422

    holiday_date = date.today() + timedelta(days=1)
    while holiday_date.isoweekday() == 7:
        holiday_date += timedelta(days=1)
    async with SessionLocal() as db:
        db.add(SchoolHoliday(date=holiday_date, name="Test Holiday"))
        await db.commit()
    body["date"] = holiday_date.isoformat()
    resp = await client.post(f"{API}/attendance/bulk", json=body, headers=admin_h)
    assert resp.status_code == 422

    sunday = date.today()
    while sunday.isoweekday() != 7:
        sunday -= timedelta(days=1)
    body["date"] = sunday.isoformat()
    resp = await client.post(f"{API}/attendance/bulk", json=body, headers=admin_h)
    assert resp.status_code == 422


async def test_teacher_backdate_limit_admin_unlimited(client, auth):
    school = await make_school()
    s1 = await create_student(school, admission_date=_old_admission())
    reg, username = await create_teacher(
        school,
        assignments=[
            {"class_id": str(school.klass.id), "section_id": str(school.sec_a.id), "subject_id": str(school.math.id)}
        ],
    )
    teacher_h = await auth_as_existing(client, username)
    _, admin_h = await auth(Role.ADMIN)

    async with SessionLocal() as db:
        school_settings = await get_school_settings(db)
        limit = school_settings.backdate_limit_days
        await db.commit()

    too_old = school_day(days_back=limit + 5)
    body = {
        "class_id": str(school.klass.id),
        "section_id": str(school.sec_a.id),
        "date": too_old.isoformat(),
        "records": [{"student_id": str(s1.student.id), "status": "present"}],
    }
    resp = await client.post(f"{API}/attendance/bulk", json=body, headers=teacher_h)
    assert resp.status_code == 422

    resp = await client.post(f"{API}/attendance/bulk", json=body, headers=admin_h)
    assert resp.status_code == 200, resp.text


async def test_percentage_matches_documented_example(client, auth):
    """15 present, 2 late, 1 sick, 2 absent -> 17 / 19 = 89.47%. Walks backward from yesterday one
    weekday at a time and sums whichever month(s) the 20 records land in, so this holds regardless of
    what day of the month "today" happens to be."""
    school = await make_school()
    s1 = await create_student(school, admission_date=_old_admission())
    _, admin_h = await auth(Role.ADMIN)

    statuses = ["present"] * 15 + ["late"] * 2 + ["sick"] * 1 + ["absent"] * 2
    d = date.today() - timedelta(days=1)
    months_touched: set[str] = set()
    for status in statuses:
        while d.isoweekday() == 7:
            d -= timedelta(days=1)
        body = {
            "class_id": str(school.klass.id),
            "section_id": str(school.sec_a.id),
            "date": d.isoformat(),
            "records": [{"student_id": str(s1.student.id), "status": status}],
        }
        resp = await client.post(f"{API}/attendance/bulk", json=body, headers=admin_h)
        assert resp.status_code == 200, resp.text
        months_touched.add(d.strftime("%Y-%m"))
        d -= timedelta(days=1)

    totals = {"present": 0, "absent": 0, "late": 0, "sick": 0}
    for month in months_touched:
        resp = await client.get(
            f"{API}/students/{s1.student.id}/attendance/summary", params={"month": month}, headers=admin_h
        )
        assert resp.status_code == 200
        summary = resp.json()
        for k in totals:
            totals[k] += summary[k]
    assert (totals["present"], totals["late"], totals["sick"], totals["absent"]) == (15, 2, 1, 2)
    attended, denom = totals["present"] + totals["late"], sum(totals.values()) - totals["sick"]
    assert round(attended / denom * 100, 2) == 89.47


async def test_teacher_cannot_mark_unassigned_section(client, auth):
    school = await make_school()
    s1 = await create_student(school, admission_date=_old_admission())
    reg, username = await create_teacher(
        school,
        assignments=[
            {"class_id": str(school.klass.id), "section_id": str(school.sec_b.id), "subject_id": str(school.math.id)}
        ],
    )
    teacher_h = await auth_as_existing(client, username)
    body = {
        "class_id": str(school.klass.id),
        "section_id": str(school.sec_a.id),
        "date": school_day().isoformat(),
        "records": [{"student_id": str(s1.student.id), "status": "present"}],
    }
    resp = await client.post(f"{API}/attendance/bulk", json=body, headers=teacher_h)
    assert resp.status_code == 404  # out of scope is 404, never 403
    params = {"class_id": str(school.klass.id), "section_id": str(school.sec_a.id)}
    assert (await client.get(f"{API}/attendance", params=params, headers=teacher_h)).status_code == 404
    day = school_day().isoformat()
    report = await client.get(
        f"{API}/reports/attendance/class", params={**params, "from": day, "to": day}, headers=teacher_h
    )
    assert report.status_code == 404
    params["section_id"] = str(school.sec_b.id)
    report = await client.get(
        f"{API}/reports/attendance/class", params={**params, "from": day, "to": day}, headers=teacher_h
    )
    assert report.status_code == 200


async def test_parent_cannot_read_another_childs_calendar(client, auth):
    from tests.test_parent import family, parent_headers

    school = await make_school()
    _, kids_a = await family(school, children=1)
    username_b, kids_b = await family(school, children=1)
    h_b = await parent_headers(client, username_b)

    month = date.today().strftime("%Y-%m")
    resp = await client.get(
        f"{API}/students/{kids_a[0].student.id}/attendance/calendar", params={"month": month}, headers=h_b
    )
    assert resp.status_code == 404


async def test_absent_creates_exactly_one_notification_per_student_per_day(client, auth):
    from tests.test_parent import family

    school = await make_school()
    username, kids = await family(school, children=1)
    sid = kids[0].student.id
    _, admin_h = await auth(Role.ADMIN)

    async with SessionLocal() as db:
        student = await db.get(Student, sid)
        student.admission_date = date.today() - timedelta(days=120)
        section_id = str(student.section_id)
        class_id = str(student.class_id)
        await db.commit()

    day = school_day().isoformat()
    body = {
        "class_id": class_id,
        "section_id": section_id,
        "date": day,
        "records": [{"student_id": str(sid), "status": "absent"}],
    }
    for _ in range(3):  # re-save the same day 3 times
        resp = await client.post(f"{API}/attendance/bulk", json=body, headers=admin_h)
        assert resp.status_code == 200, resp.text

    async with SessionLocal() as db:
        from app.models import Guardian, StudentGuardian

        guardian_user_id = await db.scalar(
            select(Guardian.user_id)
            .join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
            .where(StudentGuardian.student_id == sid)
        )
        notifications = (await db.scalars(select(Notification).where(Notification.user_id == guardian_user_id))).all()
    assert len(notifications) == 1
