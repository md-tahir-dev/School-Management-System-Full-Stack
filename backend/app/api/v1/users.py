import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select

from app.core.deps import DbSession, require_roles
from app.core.ratelimit import client_ip
from app.models import Role, User
from app.schemas.academic import ResetPasswordOut
from app.schemas.auth import UserOut
from app.schemas.common import Page, PageParams, page_params
from app.services import users as svc
from app.utils.pagination import like_pattern, paginate

# Read: Admin and CEO. Every write below additionally requires Admin.
router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_roles(Role.ADMIN, Role.CEO))])
Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]


@router.get("", response_model=Page[UserOut])
async def list_users(
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    role: Role | None = Query(None),
    is_active: bool | None = Query(None),
):
    stmt = select(User).order_by(User.role, User.username)
    if params.q:
        pattern = like_pattern(params.q)
        stmt = stmt.where(or_(User.username.ilike(pattern), User.full_name.ilike(pattern)))
    if role:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    return await paginate(db, stmt, params, UserOut)


@router.put("/{user_id}/activate", response_model=UserOut)
async def activate(user_id: uuid.UUID, request: Request, db: DbSession, admin: Admin):
    return await svc.set_user_active(db, admin, user_id, True, ip=client_ip(request))


@router.put("/{user_id}/deactivate", response_model=UserOut)
async def deactivate(user_id: uuid.UUID, request: Request, db: DbSession, admin: Admin):
    return await svc.set_user_active(db, admin, user_id, False, ip=client_ip(request))


@router.post("/{user_id}/reset-password", response_model=ResetPasswordOut)
async def reset_password(user_id: uuid.UUID, request: Request, db: DbSession, admin: Admin):
    """Returns the new temporary password once. The user must change it at next sign-in."""
    cred = await svc.reset_password(db, admin, user_id, ip=client_ip(request))
    return ResetPasswordOut(username=cred.username, temp_password=cred.temp_password)
