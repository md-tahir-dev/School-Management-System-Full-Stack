import uuid
from datetime import date

from sqlalchemy import update

from app.db.session import SessionLocal
from app.models import FeeLedger, Role
from app.models.enums import FeeStatus
from app.services.students import LoginOverrides
from tests.conftest import DEFAULT_PASSWORD, login
from tests.helpers import create_student, make_school, rand_cnic, rand_phone

API = "/api/v1"


async def parent_headers(client, username):
    resp = await login(client, username, DEFAULT_PASSWORD)
    assert resp.status_code == 200
    client.cookies.clear()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def family(school, *, children=2):
    """Registers siblings sharing one guardian; the parent can sign in with a known password."""
    cnic, phone = rand_cnic(), rand_phone()
    username = f"parent-{uuid.uuid4().hex[:8]}"
    out = []
    for i in range(children):
        out.append(
            await create_student(
                school,
                logins=LoginOverrides(parent=(username, DEFAULT_PASSWORD)) if i == 0 else None,
                guardian={"father_cnic": cnic, "father_phone": phone},
                full_name=f"Child {i} {uuid.uuid4().hex[:6]}",
                dob=f"20{12 + i}-03-0{i + 1}",
            )
        )
    return username, out


async def test_child_switcher_data_lists_only_own_children(client):
    school = await make_school()
    username, kids = await family(school, children=2)
    _, others = await family(school, children=1)
    h = await parent_headers(client, username)

    resp = (await client.get(f"{API}/parent/children", headers=h)).json()
    assert resp["total"] == 2 and {"items", "page", "page_size", "pages"} <= resp.keys()
    assert [c["id"] for c in resp["items"]] == [str(k.student.id) for k in kids]  # eldest first
    first = resp["items"][0]
    assert set(first) == {"id", "full_name", "roll_no", "class_name", "section_name", "photo_url"}
    assert first["class_name"] == school.klass.name and first["section_name"] == "A"
    assert str(others[0].student.id) not in str(resp)


async def test_dashboard_shows_current_month_fee_and_documented_placeholders(client):
    school = await make_school(fee="3000")
    username, kids = await family(school, children=1)
    sid = kids[0].student.id
    h = await parent_headers(client, username)

    dash = (await client.get(f"{API}/parent/children/{sid}/dashboard", headers=h)).json()
    assert dash["child"]["roll_no"] == kids[0].student.roll_no and dash["status"] == "active"
    fee = dash["fee_current_month"]
    assert fee["month"] == date.today().replace(day=1).isoformat()
    assert (fee["status"], fee["total_payable"], fee["paid_amount"]) == ("unpaid", "3000.00", "0.00")
    # keys exist now (null) so phases 3 to 6 can fill them without changing the schema
    for key in ("latest_result", "attendance_percentage", "upcoming_tests", "announcements"):
        assert key in dash and dash[key] is None

    async with SessionLocal() as db:
        await db.execute(
            update(FeeLedger)
            .where(FeeLedger.student_id == sid, FeeLedger.month == date.today().replace(day=1))
            .values(status=FeeStatus.PAID, paid_amount=3000)
        )
        await db.commit()
    dash = (await client.get(f"{API}/parent/children/{sid}/dashboard", headers=h)).json()
    assert dash["fee_current_month"]["status"] == "paid"


async def test_child_profile_and_ledger_are_readable_for_own_child(client):
    school = await make_school()
    username, kids = await family(school, children=1)
    sid = kids[0].student.id
    h = await parent_headers(client, username)
    profile = await client.get(f"{API}/parent/children/{sid}", headers=h)
    assert profile.status_code == 200 and profile.json()["guardian"]["father_name"]
    ledger = await client.get(f"{API}/students/{sid}/ledger", headers=h)
    assert ledger.status_code == 200 and len(ledger.json()["items"]) == 12


async def test_parent_cannot_reach_another_parents_child(client):
    school = await make_school()
    mine, _ = await family(school, children=1)
    _, theirs = await family(school, children=1)
    other_id = theirs[0].student.id
    h = await parent_headers(client, mine)
    for path in (
        f"/parent/children/{other_id}",
        f"/parent/children/{other_id}/dashboard",
        f"/students/{other_id}",
        f"/students/{other_id}/ledger",
    ):
        assert (await client.get(API + path, headers=h)).status_code == 404, (
            path
        )  # 404, not 403: existence is not leaked


async def test_parent_has_no_write_endpoints(client):
    school = await make_school()
    username, kids = await family(school, children=1)
    sid = kids[0].student.id
    h = await parent_headers(client, username)
    base = f"{API}/parent/children/{sid}"
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert (await client.request(method, base, headers=h, json={})).status_code == 405, method
        assert (await client.request(method, base + "/dashboard", headers=h, json={})).status_code == 405, method
    assert (await client.post(f"{API}/students", headers=h, json={})).status_code == 403
    assert (await client.put(f"{API}/students/{sid}", headers=h, json={"city": "x"})).status_code == 403
    assert (await client.delete(f"{API}/students/{sid}", headers=h)).status_code == 403
    assert (
        await client.put(f"{API}/students/{sid}/discount", headers=h, json={"discount_percent": "100"})
    ).status_code == 403


async def test_only_parents_use_parent_endpoints(client, auth):
    for role in (Role.ADMIN, Role.CEO, Role.TEACHER, Role.STUDENT):
        _, h = await auth(role)
        assert (await client.get(f"{API}/parent/children", headers=h)).status_code == 403, role
