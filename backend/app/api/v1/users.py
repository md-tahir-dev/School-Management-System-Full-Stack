import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, Request, status
from sqlalchemy import or_, select

from app.core.deps import DbSession, require_roles
from app.core.permissions import MANAGERS, SCHOOL_WIDE
from app.core.ratelimit import client_ip
from app.models import Role, User
from app.schemas.academic import ResetPasswordOut
from app.schemas.auth import PasswordSet, UserCreate, UserOut, UserUpdate
from app.schemas.common import Page, PageParams, page_params
from app.services import users as svc
from app.utils.pagination import like_pattern, paginate

# Read: school-wide roles. Creating accounts: admin. Activate/deactivate/reset: managers, but a headmaster
# only reaches teacher/student/parent accounts (services/users._get_manageable).
router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_roles(*SCHOOL_WIDE))])
Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]
Manager = Annotated[User, Depends(require_roles(*MANAGERS))]


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


@router.post("", response_model=ResetPasswordOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, request: Request, db: DbSession, admin: Admin):
    """Admin, CEO or headmaster account. Returns the temporary password once."""
    cred = await svc.create_user(db, admin, body, ip=client_ip(request))
    return ResetPasswordOut(username=cred.username, temp_password=cred.temp_password)


@router.put("/{user_id}", response_model=UserOut)
async def update_user(user_id: uuid.UUID, body: UserUpdate, request: Request, db: DbSession, admin: Admin):
    """Rename an account or change its username (admin only)."""
    return await svc.update_user(db, admin, user_id, body, ip=client_ip(request))


@router.put("/{user_id}/activate", response_model=UserOut)
async def activate(user_id: uuid.UUID, request: Request, db: DbSession, actor: Manager):
    return await svc.set_user_active(db, actor, user_id, True, ip=client_ip(request))


@router.put("/{user_id}/deactivate", response_model=UserOut)
async def deactivate(user_id: uuid.UUID, request: Request, db: DbSession, actor: Manager):
    return await svc.set_user_active(db, actor, user_id, False, ip=client_ip(request))


@router.post("/{user_id}/reset-password", response_model=ResetPasswordOut)
async def reset_password(
    user_id: uuid.UUID, request: Request, db: DbSession, actor: Manager, body: PasswordSet | None = Body(None)
):
    """Sets the given password, or a random one (returned once) that must be changed at next sign-in."""
    password = body.password if body else None
    cred = await svc.reset_password(db, actor, user_id, password, ip=client_ip(request))
    return ResetPasswordOut(
        username=cred.username, temp_password=cred.temp_password, must_change_password=password is None
    )
