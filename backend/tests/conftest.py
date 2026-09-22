import os
import uuid
from pathlib import Path

# Must be set before `app` is imported anywhere.
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://sms:sms@localhost:5432/sms_test")
os.environ["LOGIN_IP_LIMIT"] = "100000"
os.environ["COOKIE_SECURE"] = "false"
os.environ["UPLOAD_DIR"] = __import__("tempfile").mkdtemp(prefix="sms-uploads-")

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic.config import Config  # noqa: E402

from alembic import command  # noqa: E402
from app.core.ratelimit import limiter  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PASSWORD = "Passw0rd!x"


@pytest.fixture(scope="session", autouse=True)
def _migrated_db():
    """Builds the schema from the real Alembic migrations (also proves downgrade -> upgrade works)."""
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest_asyncio.fixture
async def client():
    limiter.reset()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


@pytest_asyncio.fixture
async def make_user():
    async def _make(role: Role = Role.ADMIN, password: str = DEFAULT_PASSWORD, **fields) -> tuple[User, str]:
        username = fields.pop("username", f"{role.value}-{uuid.uuid4().hex[:8]}")
        async with SessionLocal() as db:
            user = User(
                username=username,
                password_hash=hash_password(password),
                role=role,
                full_name=fields.pop("full_name", f"Test {role.value}"),
                **fields,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        return user, password

    return _make


async def login(client: httpx.AsyncClient, username: str, password: str = DEFAULT_PASSWORD) -> httpx.Response:
    return await client.post("/api/v1/auth/login", json={"username": username, "password": password})


def cookie_value(response: httpx.Response, name: str) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{name}="):
            return header.split(";", 1)[0].split("=", 1)[1]
    return None


@pytest_asyncio.fixture
async def auth(client, make_user):
    """auth(Role.TEACHER) -> (user, {"Authorization": "Bearer ..."})"""

    async def _auth(role: Role = Role.ADMIN, **fields):
        user, password = await make_user(role, **fields)
        resp = await login(client, user.username, password)
        assert resp.status_code == 200, resp.text
        client.cookies.clear()  # keep tests explicit: only the bearer header authenticates
        return user, {"Authorization": f"Bearer {resp.json()['access_token']}"}

    return _auth
