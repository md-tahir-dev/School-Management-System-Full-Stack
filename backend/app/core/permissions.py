"""Single role -> permission matrix. Route guards use `require_roles` / `require_permission`;
row-level scoping (a teacher's own classes, a parent's own children) is enforced in the service layer.

Permissions are "module:action". Actions: read, write, and *_own for self-scoped access."""

from app.models.enums import Role

MODULES = (
    "students",
    "teachers",
    "fees",
    "salary",
    "results",
    "attendance",
    "tests",
    "materials",
    "announcements",
    "settings",
    "users",
    "reports",
    "audit",
)


def _all(actions: tuple[str, ...]) -> frozenset[str]:
    return frozenset(f"{m}:{a}" for m in MODULES for a in actions)


ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    # Full CRUD everywhere.
    Role.ADMIN: _all(("read", "write")),
    # Read-only everywhere.
    Role.CEO: _all(("read",)),
    # Academic head: reads everything, runs academics/finance/settings; no student/teacher writes.
    # users:write = activate/deactivate/reset teacher, student and parent logins only (services/users.py).
    Role.HEADMASTER: _all(("read",))
    | frozenset(
        f"{m}:write" for m in ("settings", "attendance", "results", "tests", "fees", "salary", "reports", "users")
    ),
    # Only assigned classes/students (scoped in the service layer).
    Role.TEACHER: frozenset(
        {
            "students:read",
            "attendance:read",
            "attendance:write",
            "results:read",
            "results:write",
            "tests:read",
            "tests:write",
            "materials:read",
            "materials:write",
            "announcements:read",
            "salary:read_own",
        }
    ),
    Role.STUDENT: frozenset(
        {
            "students:read_own",
            "results:read_own",
            "fees:read_own",
            "attendance:read_own",
            "tests:read_own",
            "tests:take",
            "materials:read",
            "announcements:read",
        }
    ),
    # Read-only, linked children only.
    Role.PARENT: frozenset(
        {
            "students:read_own",
            "results:read_own",
            "fees:read_own",
            "attendance:read_own",
            "materials:read",
            "announcements:read",
        }
    ),
}


# Role groups for route guards and service-layer checks. Change these, not the call sites.
SCHOOL_WIDE = (Role.ADMIN, Role.CEO, Role.HEADMASTER)  # unscoped readers
MANAGERS = (Role.ADMIN, Role.HEADMASTER)  # academic/settings/finance writers


def has_permission(role: Role, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
