import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.deps import require_owner_or_roles, require_permission, require_roles
from app.core.errors import register_exception_handlers
from app.models import Role, User


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (Role.ADMIN, 200),
        (Role.CEO, 200),
        (Role.TEACHER, 403),
        (Role.STUDENT, 403),
        (Role.PARENT, 403),
    ],
)
async def test_users_list_role_matrix(client, auth, role, expected):
    _, headers = await auth(role)
    assert (await client.get("/api/v1/users", headers=headers)).status_code == expected


async def test_users_list_requires_authentication(client):
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("role", "expected"),
    [(Role.ADMIN, 200), (Role.CEO, 403), (Role.TEACHER, 403), (Role.STUDENT, 403), (Role.PARENT, 403)],
)
async def test_only_admin_can_change_settings(client, auth, role, expected):
    _, headers = await auth(role)
    resp = await client.put("/api/v1/settings", headers=headers, json={"slogan": f"set by {role.value}"})
    assert resp.status_code == expected


@pytest.mark.parametrize("role", list(Role))
async def test_every_role_can_read_settings(client, auth, role):
    _, headers = await auth(role)
    assert (await client.get("/api/v1/settings", headers=headers)).status_code == 200


def _mini_app() -> FastAPI:
    """Exercises the dependency factories on their own, independent of real routes."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/profile/{user_id}")
    async def profile(user_id: str, user: User = Depends(require_owner_or_roles(Role.ADMIN))):
        return {"ok": True}

    @app.get("/staff-only")
    async def staff(user: User = Depends(require_roles(Role.ADMIN, Role.TEACHER))):
        return {"ok": True}

    @app.get("/needs-perm")
    async def needs_perm(user: User = Depends(require_permission("attendance:write"))):
        return {"ok": True}

    return app


async def test_require_owner_or_roles(auth):
    owner, owner_headers = await auth(Role.STUDENT)
    _, other_headers = await auth(Role.STUDENT)
    _, admin_headers = await auth(Role.ADMIN)
    async with AsyncClient(transport=ASGITransport(app=_mini_app()), base_url="http://t") as c:
        assert (await c.get(f"/profile/{owner.id}", headers=owner_headers)).status_code == 200
        assert (await c.get(f"/profile/{owner.id}", headers=other_headers)).status_code == 403
        assert (await c.get(f"/profile/{owner.id}", headers=admin_headers)).status_code == 200
        assert (await c.get(f"/profile/{owner.id}")).status_code == 401


async def test_require_roles_and_permission(auth):
    _, teacher = await auth(Role.TEACHER)
    _, parent = await auth(Role.PARENT)
    _, ceo = await auth(Role.CEO)
    async with AsyncClient(transport=ASGITransport(app=_mini_app()), base_url="http://t") as c:
        assert (await c.get("/staff-only", headers=teacher)).status_code == 200
        assert (await c.get("/staff-only", headers=parent)).status_code == 403
        assert (await c.get("/needs-perm", headers=teacher)).status_code == 200
        assert (await c.get("/needs-perm", headers=ceo)).status_code == 403  # CEO is read-only
        assert (await c.get("/needs-perm", headers=parent)).status_code == 403
