import asyncio
import re
from datetime import date, timedelta
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import FeeLedger, FeeStructure, Role, SchoolClass, Section
from app.services.fees import academic_year_months
from app.services.settings import get_school_settings
from app.services.students import LoginOverrides
from tests.conftest import DEFAULT_PASSWORD
from tests.helpers import create_student, make_school, tag
from tests.test_parent import family, parent_headers

API = "/api/v1"
PAST = date(2020, 1, 10)


@pytest_asyncio.fixture
async def admin(auth):
    return (await auth(Role.ADMIN))[1]


@pytest_asyncio.fixture
async def late_fine():
    async def _set(amount):
        async with SessionLocal() as db:
            (await get_school_settings(db)).late_fine_amount = Decimal(amount)
            await db.commit()

    yield _set
    await _set(0)


async def ledger(client, h, sid):
    resp = await client.get(f"{API}/students/{sid}/ledger", headers=h)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def pay(client, h, sid, amount, expect=201):
    resp = await client.post(
        f"{API}/fees/payments", headers=h, json={"student_id": str(sid), "amount": str(amount), "method": "cash"}
    )
    assert resp.status_code == expect, resp.text
    return resp.json()


async def set_due(sid, overdue: int):
    """First `overdue` months become past due; the rest are pushed far into the future (deterministic)."""
    async with SessionLocal() as db:
        rows = (await db.scalars(select(FeeLedger).where(FeeLedger.student_id == sid).order_by(FeeLedger.month))).all()
        for i, r in enumerate(rows):
            r.due_date = date(2020, 1, 10 + i) if i < overdue else date(2099, 1, 1)
        await db.commit()


async def test_payment_allocates_oldest_month_first(client, admin):
    sid = (await create_student(await make_school())).student.id
    p1 = await pay(client, admin, sid, 3000)
    assert re.fullmatch(r"RCPT-\d{6}-\d{5}", p1["receipt_no"])
    assert [(a["amount"]) for a in p1["allocations"]] == ["2000.00", "1000.00"]
    rows = (await ledger(client, admin, sid))["items"]
    assert [r["status"] for r in rows[:3]] == ["paid", "partial", "unpaid"]
    assert rows[0]["receipt_no"] == p1["receipt_no"] and rows[0]["paid_date"]
    assert rows[1]["paid_amount"] == "1000.00"

    p2 = await pay(client, admin, sid, 1000)
    assert p2["receipt_no"] > p1["receipt_no"]
    rows = (await ledger(client, admin, sid))["items"]
    assert rows[1]["status"] == "paid" and rows[1]["receipt_no"] == p2["receipt_no"]


async def test_payment_validation(client, admin):
    sid = (await create_student(await make_school())).student.id
    over = await client.post(
        f"{API}/fees/payments", headers=admin, json={"student_id": str(sid), "amount": "24000.01", "method": "cash"}
    )
    assert over.status_code == 422 and "amount" in over.json()["fields"]
    for bad in ("0", "-5"):
        resp = await client.post(
            f"{API}/fees/payments", headers=admin, json={"student_id": str(sid), "amount": bad, "method": "cash"}
        )
        assert resp.status_code == 422 and "amount" in resp.json()["fields"]
    await pay(client, admin, sid, 24000)
    resp = await client.post(
        f"{API}/fees/payments", headers=admin, json={"student_id": str(sid), "amount": "1", "method": "cash"}
    )
    assert resp.status_code == 409 and resp.json()["code"] == "NOTHING_DUE"


async def test_late_fine_applied_once_to_unpaid_overdue_months(client, admin, late_fine):
    sid = (await create_student(await make_school())).student.id
    await late_fine("200")  # after make_school, which resets it
    await set_due(sid, 0)  # nothing overdue yet, whatever today's date is
    await pay(client, admin, sid, 2000)  # month 0 paid before it becomes overdue
    await set_due(sid, 3)
    rows = (await ledger(client, admin, sid))["items"]
    assert [r["fine"] for r in rows[:4]] == ["0.00", "200.00", "200.00", "0.00"]
    assert rows[1]["total_payable"] == "2200.00"
    again = await ledger(client, admin, sid)
    assert again["items"] == (await ledger(client, admin, sid))["items"]
    assert [r["fine"] for r in again["items"][:4]] == ["0.00", "200.00", "200.00", "0.00"]
    assert again["totals"]["total_payable"] == "24400.00"  # 12 x 2000 + 2 fines

    p = await pay(client, admin, sid, 2200)
    assert [a["amount"] for a in p["allocations"]] == ["2200.00"]
    assert (await ledger(client, admin, sid))["items"][1]["status"] == "paid"


async def test_void_reverses_allocations_and_keeps_payment(client, admin, auth):
    sid = (await create_student(await make_school())).student.id
    p1 = await pay(client, admin, sid, 1000)
    p2 = await pay(client, admin, sid, 1500)  # 1000 finishes month 0, 500 starts month 1

    voided = await client.post(f"{API}/fees/payments/{p2['id']}/void", headers=admin, json={"reason": "wrong amount"})
    assert voided.status_code == 200
    body = voided.json()
    assert body["voided_at"] and body["void_reason"] == "wrong amount"
    rows = (await ledger(client, admin, sid))["items"]
    assert (rows[0]["status"], rows[0]["paid_amount"]) == ("partial", "1000.00")
    assert (rows[1]["status"], rows[1]["paid_amount"], rows[1]["paid_date"]) == ("unpaid", "0.00", None)

    again = await client.post(f"{API}/fees/payments/{p2['id']}/void", headers=admin, json={"reason": "again"})
    assert again.status_code == 409 and again.json()["code"] == "ALREADY_VOID"
    short = await client.post(f"{API}/fees/payments/{p1['id']}/void", headers=admin, json={"reason": "ab"})
    assert short.status_code == 422 and "reason" in short.json()["fields"]

    assert (
        await client.post(f"{API}/fees/payments/{p1['id']}/void", headers=admin, json={"reason": "oops"})
    ).status_code == 200
    assert (await ledger(client, admin, sid))["items"][0]["status"] == "unpaid"
    kept = await client.get(f"{API}/fees/payments/{p2['id']}", headers=admin)
    assert kept.status_code == 200 and kept.json()["receipt_no"] == p2["receipt_no"]

    for role in (Role.TEACHER, Role.CEO):
        h = (await auth(role))[1]
        resp = await client.post(f"{API}/fees/payments/{p1['id']}/void", headers=h, json={"reason": "nope nope"})
        assert resp.status_code == 403


async def test_payment_visibility(client, admin, auth):
    school = await make_school()
    username, kids = await family(school, children=2)
    _, strangers = await family(school, children=1)
    stu_name = f"stu-{tag()}"
    own = await create_student(
        school, create_student_login=True, logins=LoginOverrides(student=(stu_name, DEFAULT_PASSWORD))
    )
    mine = await pay(client, admin, kids[0].student.id, 500)
    theirs = await pay(client, admin, strangers[0].student.id, 500)
    stu_pay = await pay(client, admin, own.student.id, 500)

    h = await parent_headers(client, username)
    assert (await client.get(f"{API}/fees/payments/{mine['id']}", headers=h)).status_code == 200
    pdf = await client.get(f"{API}/fees/payments/{mine['id']}/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert (await client.get(f"{API}/fees/payments/{theirs['id']}", headers=h)).status_code == 404
    assert (await client.get(f"{API}/fees/payments/{theirs['id']}/pdf", headers=h)).status_code == 404

    sh = await parent_headers(client, stu_name)
    assert (await client.get(f"{API}/fees/payments/{stu_pay['id']}", headers=sh)).status_code == 200
    assert (await client.get(f"{API}/fees/payments/{mine['id']}", headers=sh)).status_code == 404

    th = (await auth(Role.TEACHER))[1]
    assert (await client.get(f"{API}/fees/payments", headers=th)).status_code == 403  # raised before the buggy paginate
    assert (await client.get(f"{API}/fees/payments/{mine['id']}", headers=th)).status_code == 403

    for role in (Role.CEO, Role.HEADMASTER):
        rh = (await auth(role))[1]
        assert (await client.get(f"{API}/fees/payments/{theirs['id']}", headers=rh)).status_code == 200
    ceo = (await auth(Role.CEO))[1]
    body = {"student_id": str(kids[0].student.id), "amount": "100", "method": "cash"}
    assert (await client.post(f"{API}/fees/payments", headers=ceo, json=body)).status_code == 403
    hm = (await auth(Role.HEADMASTER))[1]
    assert (await client.post(f"{API}/fees/payments", headers=hm, json=body)).status_code == 201


async def test_defaulters_list_only_overdue_unpaid(client, admin):
    school = await make_school()
    a = (await create_student(school)).student
    b = (await create_student(school)).student
    c = (await create_student(school)).student
    await set_due(a.id, 2)
    await set_due(b.id, 0)
    await set_due(c.id, 1)
    await pay(client, admin, c.id, 2000)  # c's only overdue month is settled

    resp = await client.get(f"{API}/fees/defaulters", headers=admin, params={"class_id": str(school.klass.id)})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["student_id"] for i in items] == [str(a.id)]
    assert (items[0]["months_due"], items[0]["amount_due"], items[0]["oldest_due_date"]) == (2, "4000.00", "2020-01-10")

    await pay(client, admin, a.id, 500)
    items = (await client.get(f"{API}/fees/defaulters", headers=admin, params={"q": a.full_name})).json()["items"]
    assert [i["student_id"] for i in items] == [str(a.id)] and items[0]["amount_due"] == "3500.00"
    other = await make_school()
    empty = await client.get(f"{API}/fees/defaulters", headers=admin, params={"class_id": str(other.klass.id)})
    assert empty.json()["total"] == 0


async def test_summary_for_month(client, admin):
    school = await make_school()
    a = (await create_student(school)).student
    b = (await create_student(school)).student
    month = date.today().replace(day=1).isoformat()

    async def summary():
        resp = await client.get(f"{API}/fees/summary", headers=admin, params={"month": month})
        assert resp.status_code == 200
        return resp.json()

    before = Decimal((await summary())["received_in_month"])
    await pay(client, admin, a.id, 500)
    gone = await pay(client, admin, b.id, 300)
    await client.post(f"{API}/fees/payments/{gone['id']}/void", headers=admin, json={"reason": "mistake"})
    s = await summary()
    mine = next(c for c in s["by_class"] if c["class_name"] == school.klass.name)
    assert (mine["billed"], mine["collected"], mine["outstanding"]) == ("4000.00", "500.00", "3500.00")
    assert Decimal(s["received_in_month"]) - before == Decimal(500)  # voided payment excluded
    assert Decimal(s["billed"]) - Decimal(s["collected"]) == Decimal(s["outstanding"])


async def test_class_change_reprices_only_untouched_months(client, admin):
    school = await make_school()
    sid = (await create_student(school)).student.id
    async with SessionLocal() as db:
        klass = SchoolClass(name=f"Class2-{tag()}", sort_order=2)
        db.add(klass)
        await db.flush()
        sec = Section(class_id=klass.id, name="A")
        db.add_all([sec, FeeStructure(class_id=klass.id, monthly_fee=Decimal(3000))])
        await db.commit()
    assert (
        await client.put(f"{API}/students/{sid}/discount", headers=admin, json={"discount_percent": "10"})
    ).status_code == 200
    await pay(client, admin, sid, 1800)  # month 0 paid
    await pay(client, admin, sid, 500)  # month 1 partial

    resp = await client.put(
        f"{API}/students/{sid}", headers=admin, json={"class_id": str(klass.id), "section_id": str(sec.id)}
    )
    assert resp.status_code == 200, resp.text
    rows = (await ledger(client, admin, sid))["items"]
    assert [(r["status"], r["base_fee"], r["total_payable"]) for r in rows[:2]] == [
        ("paid", "2000.00", "1800.00"),
        ("partial", "2000.00", "1800.00"),
    ]
    for r in rows[2:]:
        assert (r["base_fee"], r["discount"], r["total_payable"]) == ("3000.00", "300.00", "2700.00")


async def test_concurrent_payments_cannot_overpay(client, admin):
    sid = (await create_student(await make_school())).student.id
    await pay(client, admin, sid, 23000)  # 1000 left
    body = {"student_id": str(sid), "amount": "800", "method": "cash"}
    r = await asyncio.gather(*(client.post(f"{API}/fees/payments", headers=admin, json=body) for _ in range(2)))
    assert sorted(x.status_code for x in r) == [201, 422]
    assert (await ledger(client, admin, sid))["totals"]["balance"] == "200.00"


async def test_payment_list_scoped_by_role(client, admin, auth):
    school = await make_school()
    username, kids = await family(school, children=1)
    _, strangers = await family(school, children=1)
    mine = await pay(client, admin, kids[0].student.id, 500)
    await pay(client, admin, strangers[0].student.id, 500)
    h = await parent_headers(client, username)
    listed = (await client.get(f"{API}/fees/payments", headers=h)).json()
    assert [p["id"] for p in listed["items"]] == [mine["id"]]
    ceo = (await auth(Role.CEO))[1]
    got = await client.get(f"{API}/fees/payments", headers=ceo, params={"student_id": str(kids[0].student.id)})
    assert got.json()["total"] == 1


async def test_mid_year_admission_is_billed_and_fined_from_the_admission_month_only(client, admin, late_fine):
    school = await make_school()
    await late_fine("200")
    months = academic_year_months(school.year.start_date)
    sid = (await create_student(school, admission_date=str(months[5] + timedelta(days=14)))).student.id

    await set_due(sid, 12)  # every row the student has is overdue
    body = await ledger(client, admin, sid)
    assert [r["month"] for r in body["items"]] == [m.isoformat() for m in months[5:]]
    assert {r["fine"] for r in body["items"]} == {"200.00"}
    assert body["totals"]["total_payable"] == "15400.00"  # 7 x (2000 + 200), nothing for months 1-5


async def test_admission_date_edit_resyncs_untouched_months(client, admin):
    school = await make_school()
    months = academic_year_months(school.year.start_date)
    sid = (await create_student(school, admission_date=str(months[5]))).student.id
    url = f"{API}/students/{sid}"

    assert (await client.put(url, headers=admin, json={"admission_date": str(months[2])})).status_code == 200
    assert [r["month"] for r in (await ledger(client, admin, sid))["items"]] == [m.isoformat() for m in months[2:]]

    await pay(client, admin, sid, 1000)  # months[2] now has a payment: history, never deleted
    assert (await client.put(url, headers=admin, json={"admission_date": str(months[8])})).status_code == 200
    rows = (await ledger(client, admin, sid))["items"]
    assert [r["month"] for r in rows] == [m.isoformat() for m in [months[2], *months[8:]]]
    assert rows[0]["paid_amount"] == "1000.00"
