import uuid

from app.models import Role
from tests.conftest import login

API = "/api/v1"


async def test_admin_creates_staff_account_with_one_time_password(client, auth):
    _, h = await auth(Role.ADMIN)
    name = f"HM-{uuid.uuid4().hex[:6]}"
    resp = await client.post(
        f"{API}/users", headers=h, json={"username": name, "full_name": "Head", "role": "headmaster"}
    )
    assert resp.status_code == 201, resp.text
    cred = resp.json()
    assert cred["username"] == name.lower()
    signed_in = await login(client, name, cred["temp_password"])
    assert signed_in.status_code == 200
    assert signed_in.json()["user"]["role"] == "headmaster"
    assert signed_in.json()["user"]["must_change_password"] is True

    again = await client.post(
        f"{API}/users", headers=h, json={"username": name.upper(), "full_name": "X", "role": "ceo"}
    )
    assert again.status_code == 409
    assert "username" in again.json()["fields"]

    teacher = await client.post(
        f"{API}/users", headers=h, json={"username": f"t{name}", "full_name": "T", "role": "teacher"}
    )
    assert teacher.status_code == 422  # profile-linked roles come from registration


async def test_headmaster_manages_only_teacher_student_parent_logins(client, auth, make_user):
    _, h = await auth(Role.HEADMASTER)
    teacher, _ = await make_user(Role.TEACHER)
    admin, _ = await make_user(Role.ADMIN)
    ceo, _ = await make_user(Role.CEO)

    reset = await client.post(f"{API}/users/{teacher.id}/reset-password", headers=h)
    assert reset.status_code == 200
    assert reset.json()["temp_password"]
    assert (await client.put(f"{API}/users/{teacher.id}/deactivate", headers=h)).json()["is_active"] is False
    assert (await client.put(f"{API}/users/{teacher.id}/activate", headers=h)).json()["is_active"] is True

    for target in (admin, ceo):
        assert (await client.post(f"{API}/users/{target.id}/reset-password", headers=h)).status_code == 404
        assert (await client.put(f"{API}/users/{target.id}/deactivate", headers=h)).status_code == 404


async def test_admin_sets_chosen_password_and_renames(client, auth, make_user):
    _, h = await auth(Role.ADMIN)
    student, _ = await make_user(Role.STUDENT)
    weak = await client.post(f"{API}/users/{student.id}/reset-password", headers=h, json={"password": "short"})
    assert weak.status_code == 422
    chosen = await client.post(f"{API}/users/{student.id}/reset-password", headers=h, json={"password": "Chosen123"})
    assert chosen.status_code == 200 and chosen.json()["must_change_password"] is False
    signed_in = await login(client, student.username, "Chosen123")
    assert signed_in.status_code == 200 and signed_in.json()["user"]["must_change_password"] is False

    new_name = f"S-{uuid.uuid4().hex[:6]}"
    resp = await client.put(f"{API}/users/{student.id}", headers=h, json={"username": new_name, "full_name": "Renamed"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["username"] == new_name.lower() and resp.json()["full_name"] == "Renamed"
    other, _ = await make_user(Role.TEACHER)
    taken = await client.put(f"{API}/users/{other.id}", headers=h, json={"username": new_name})
    assert taken.status_code == 409
