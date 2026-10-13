import pytest

from app.core.permissions import MODULES, ROLE_PERMISSIONS, has_permission
from app.models import Role


def test_ceo_is_strictly_read_only():
    perms = ROLE_PERMISSIONS[Role.CEO]
    assert perms, "CEO must be able to read"
    assert not any(p.endswith(":write") for p in perms)
    assert all(has_permission(Role.CEO, f"{m}:read") for m in MODULES)


def test_admin_has_full_crud_on_every_module():
    for module in MODULES:
        assert has_permission(Role.ADMIN, f"{module}:read")
        assert has_permission(Role.ADMIN, f"{module}:write")


@pytest.mark.parametrize("role", [Role.STUDENT, Role.PARENT])
def test_students_and_parents_never_write(role):
    assert not any(p.endswith(":write") for p in ROLE_PERMISSIONS[role])


@pytest.mark.parametrize("permission", ["fees:write", "salary:write", "settings:write", "users:write", "audit:read"])
def test_teacher_cannot_touch_money_settings_or_users(permission):
    assert not has_permission(Role.TEACHER, permission)


def test_teacher_can_do_classroom_work():
    for p in ("attendance:write", "results:write", "tests:write", "materials:write", "salary:read_own"):
        assert has_permission(Role.TEACHER, p)


def test_parents_cannot_see_salary_or_other_children_lists():
    assert not has_permission(Role.PARENT, "salary:read_own")
    assert not has_permission(Role.PARENT, "students:read")


def test_headmaster_reads_everything_but_cannot_write_people_or_users():
    assert all(has_permission(Role.HEADMASTER, f"{m}:read") for m in MODULES)
    for module in ("students", "teachers", "users"):
        assert not has_permission(Role.HEADMASTER, f"{module}:write")
    for module in ("settings", "attendance", "results", "fees", "salary"):
        assert has_permission(Role.HEADMASTER, f"{module}:write")
