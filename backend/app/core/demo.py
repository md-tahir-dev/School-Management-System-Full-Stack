"""Demo accounts: single source for the seed script and the login-page hint (APP_ENV=demo only)."""

from app.core.config import settings
from app.models.enums import Role

DEMO_USERS: tuple[tuple[Role, str, str], ...] = (
    (Role.CEO, "ceo", "Demo CEO"),
    (Role.ADMIN, "admin", "Demo Admin"),
    (Role.HEADMASTER, "headmaster", "Demo Headmaster"),
    (Role.TEACHER, "teacher", "Demo Teacher"),
    (Role.STUDENT, "student", "Demo Student"),
    (Role.PARENT, "parent", "Demo Parent"),
)


def demo_accounts() -> list[dict[str, str]] | None:
    if settings.app_env != "demo":
        return None
    return [{"role": r.value, "username": u, "password": settings.seed_demo_password} for r, u, _ in DEMO_USERS]
