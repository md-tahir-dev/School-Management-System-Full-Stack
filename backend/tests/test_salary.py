from datetime import date
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.models import Role, SalaryStructure, TeacherAttendance
from app.models.enums import TeacherAttendanceStatus as S
from app.utils.money import money
from tests.conftest import DEFAULT_PASSWORD, login
from tests.helpers import create_teacher, make_school

API = "/api/v1"
GROSS = Decimal(67500)


@pytest_asyncio.fixture
async def admin(auth):
    return (await auth(Role.ADMIN))[1]


async def mark(teacher_id, month: str, statuses: list[S]):
    y, m = map(int, month.split("-"))
    async with SessionLocal() as db:
        for i, st in enumerate(statuses, start=3):
            db.add(TeacherAttendance(teacher_id=teacher_id, date=date(y, m, i), status=st))
        await db.commit()


async def generate(client, h, month):
    resp = await client.post(f"{API}/salary/generate", headers=h, json={"month": f"{month}-15"})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def records(client, h, month):
    resp = await client.get(f"{API}/salary", headers=h, params={"month": f"{month}-01"})
    assert resp.status_code == 200
    return {r["teacher_id"]: r for r in resp.json()}


async def advance(client, h, teacher_id, month, amount="1000"):
    return await client.post(
        f"{API}/salary/advances", headers=h, json={"teacher_id": str(teacher_id), "amount": amount, "month": month}
    )


async def test_generate_computes_absence_advance_and_floors_net(client, admin):
    school = await make_school()
    reg, _ = await create_teacher(school)
    broke, _ = await create_teacher(school)
    t, b = reg.teacher.id, broke.teacher.id
    # 2 absent count; leave and late do not; February 2031 has 28 days
    await mark(t, "2031-02", [S.ABSENT, S.ABSENT, S.LEAVE, S.LATE, S.PRESENT])
    assert (await advance(client, admin, t, "2031-02-20")).status_code == 201
    assert (await advance(client, admin, b, "2031-02-01", "999999")).status_code == 201

    out = await generate(client, admin, "2031-02")
    assert out["created"] >= 2
    recs = await records(client, admin, "2031-02")
    r = recs[str(t)]
    deduction = money(GROSS / 28 * 2)
    assert (r["gross"], r["absent_days"], r["status"]) == ("67500.00", 2, "unpaid")
    assert Decimal(r["absence_deduction"]) == deduction == Decimal("4821.43")
    assert Decimal(r["advance_deduction"]) == 1000
    assert Decimal(r["net"]) == GROSS - deduction - 1000
    assert recs[str(b)]["net"] == "0.00"


async def test_teacher_without_structure_is_reported_not_paid(client, admin):
    reg, _ = await create_teacher(await make_school())
    async with SessionLocal() as db:
        await db.execute(delete(SalaryStructure).where(SalaryStructure.teacher_id == reg.teacher.id))
        await db.commit()
    out = await generate(client, admin, "2031-03")
    assert reg.teacher.full_name in out["without_structure"]
    assert str(reg.teacher.id) not in await records(client, admin, "2031-03")


async def test_regenerate_recalculates_unpaid_and_skips_paid(client, admin):
    school = await make_school()
    paid_reg, _ = await create_teacher(school)
    open_reg, _ = await create_teacher(school)
    await generate(client, admin, "2031-04")
    recs = await records(client, admin, "2031-04")
    paid, still_open = recs[str(paid_reg.teacher.id)], recs[str(open_reg.teacher.id)]

    resp = await client.post(f"{API}/salary/{paid['id']}/pay", headers=admin, json={})
    assert resp.status_code == 200 and resp.json()["status"] == "paid" and resp.json()["paid_date"]
    again = await client.post(f"{API}/salary/{paid['id']}/pay", headers=admin, json={})
    assert again.status_code == 409 and again.json()["code"] == "ALREADY_PAID"

    await mark(paid_reg.teacher.id, "2031-04", [S.ABSENT])
    await mark(open_reg.teacher.id, "2031-04", [S.ABSENT])
    out = await generate(client, admin, "2031-04")
    assert out["skipped_paid"] >= 1 and out["recalculated"] >= 1 and out["created"] == 0
    recs = await records(client, admin, "2031-04")
    assert recs[paid["teacher_id"]]["absent_days"] == 0 and recs[paid["teacher_id"]]["net"] == paid["net"]
    assert recs[still_open["teacher_id"]]["absent_days"] == 1
    assert recs[still_open["teacher_id"]]["id"] == still_open["id"]  # same row, updated


async def test_advances_add_list_delete_and_paid_month_lock(client, admin):
    reg, _ = await create_teacher(await make_school())
    t = reg.teacher.id
    created = await advance(client, admin, t, "2031-05-17", "700")
    assert created.status_code == 201 and created.json()["month"] == "2031-05-01"
    listed = await client.get(f"{API}/salary/advances", headers=admin, params={"month": "2031-05-01"})
    assert str(created.json()["id"]) in [a["id"] for a in listed.json()]
    other_month = await client.get(f"{API}/salary/advances", headers=admin, params={"month": "2031-06-01"})
    assert created.json()["id"] not in [a["id"] for a in other_month.json()]

    await generate(client, admin, "2031-05")
    rec = (await records(client, admin, "2031-05"))[str(t)]
    assert rec["advance_deduction"] == "700.00"
    await client.post(f"{API}/salary/{rec['id']}/pay", headers=admin, json={})

    blocked = await advance(client, admin, t, "2031-05-01")
    assert blocked.status_code == 422 and "month" in blocked.json()["fields"]
    locked = await client.delete(f"{API}/salary/advances/{created.json()['id']}", headers=admin)
    assert locked.status_code == 409

    free = await advance(client, admin, t, "2031-06-01", "300")
    assert (await client.delete(f"{API}/salary/advances/{free.json()['id']}", headers=admin)).status_code == 204
    gone = await client.get(f"{API}/salary/advances", headers=admin, params={"month": "2031-06-01"})
    assert free.json()["id"] not in [a["id"] for a in gone.json()]


async def test_teacher_sees_only_own_salary(client, admin):
    school = await make_school()
    me, username = await create_teacher(school)
    other, _ = await create_teacher(school)
    await generate(client, admin, "2031-07")
    recs = await records(client, admin, "2031-07")
    mine, theirs = recs[str(me.teacher.id)], recs[str(other.teacher.id)]
    resp = await login(client, username, DEFAULT_PASSWORD)
    client.cookies.clear()
    h = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    own = (await client.get(f"{API}/salary/me", headers=h)).json()
    assert own and {r["teacher_id"] for r in own} == {str(me.teacher.id)}
    assert (await client.get(f"{API}/salary/{mine['id']}", headers=h)).status_code == 200
    pdf = await client.get(f"{API}/salary/{mine['id']}/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert (await client.get(f"{API}/salary/{theirs['id']}", headers=h)).status_code == 404
    assert (await client.get(f"{API}/salary/{theirs['id']}/pdf", headers=h)).status_code == 404
    assert (await client.get(f"{API}/salary", headers=h, params={"month": "2031-07-01"})).status_code == 403
    assert (await client.post(f"{API}/salary/{mine['id']}/pay", headers=h, json={})).status_code == 403


async def test_ceo_reads_but_cannot_generate_or_pay(client, admin, auth):
    reg, _ = await create_teacher(await make_school())
    await generate(client, admin, "2031-08")
    rec = (await records(client, admin, "2031-08"))[str(reg.teacher.id)]
    ceo = (await auth(Role.CEO))[1]
    assert str(reg.teacher.id) in await records(client, ceo, "2031-08")
    assert (await client.get(f"{API}/salary/{rec['id']}", headers=ceo)).status_code == 200
    assert (await client.post(f"{API}/salary/generate", headers=ceo, json={"month": "2031-08-01"})).status_code == 403
    assert (await client.post(f"{API}/salary/{rec['id']}/pay", headers=ceo, json={})).status_code == 403
    assert (await advance(client, ceo, reg.teacher.id, "2031-08-01")).status_code == 403


async def test_student_and_parent_get_403_everywhere(client, admin, auth):
    reg, _ = await create_teacher(await make_school())
    await generate(client, admin, "2031-09")
    rec = (await records(client, admin, "2031-09"))[str(reg.teacher.id)]
    for role in (Role.STUDENT, Role.PARENT):
        h = (await auth(role))[1]
        for path in (
            "/salary?month=2031-09-01",
            "/salary/me",
            "/salary/advances?month=2031-09-01",
            f"/salary/{rec['id']}",
            f"/salary/{rec['id']}/pdf",
        ):
            assert (await client.get(API + path, headers=h)).status_code == 403, (role, path)
        assert (await client.post(f"{API}/salary/generate", headers=h, json={"month": "2031-09-01"})).status_code == 403
        assert (await client.post(f"{API}/salary/{rec['id']}/pay", headers=h, json={})).status_code == 403
