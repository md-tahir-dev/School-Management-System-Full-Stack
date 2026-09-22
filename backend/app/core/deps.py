import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden, unauthorized
from app.core.permissions import has_permission
from app.core.security import TokenError, decode_access_token
from app.db.session import get_db
from app.models import Role, User

DbSession = Annotated[AsyncSession, Depends(get_db)]
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)], db: DbSession
) -> User:
    """Authenticated user, even if they still have to change their temporary password
    (only /auth/me and /auth/change-password use this directly)."""
    if creds is None:
        raise unauthorized()
    try:
        payload = decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, ValueError, KeyError):
        raise unauthorized("Your session is invalid or has expired.", code="invalid_token") from None
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized("Your session is invalid or has expired.", code="invalid_token")
    return user


async def get_active_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Like get_current_user, but blocks accounts that must set a new password first."""
    if user.must_change_password:
        raise forbidden("You must change your temporary password first.", code="password_change_required")
    return user


CurrentUser = Annotated[User, Depends(get_active_user)]
CurrentUserAllowPending = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[..., User]:
    """`dependencies=[Depends(require_roles(Role.ADMIN, Role.CEO))]` or `user = Depends(...)`."""
    allowed = frozenset(roles)

    async def checker(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise forbidden()
        return user

    return checker


def require_permission(permission: str) -> Callable[..., User]:
    async def checker(user: CurrentUser) -> User:
        if not has_permission(user.role, permission):
            raise forbidden()
        return user

    return checker


def require_owner_or_roles(*roles: Role, owner_param: str = "user_id") -> Callable[..., User]:
    """Allows the listed roles, or the user whose id equals the `owner_param` path parameter.
    For resources owned via a profile row (student -> user) do the ownership check in the service."""
    allowed = frozenset(roles)

    async def checker(request: Request, user: CurrentUser) -> User:
        if user.role in allowed:
            return user
        if str(request.path_params.get(owner_param)) == str(user.id):
            return user
        raise forbidden()

    return checker
