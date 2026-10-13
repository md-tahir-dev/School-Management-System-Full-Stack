"""Part D: the Student and CEO dashboards (the Parent dashboard already existed in `parent.py` and
is extended in `app.services.parents`)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, DbSession, require_roles
from app.models import Role, User
from app.services import dashboard as svc

router = APIRouter(tags=["dashboard"])


@router.get("/student/dashboard", response_model=dict[str, Any])
async def student_dashboard(user: CurrentUser, db: DbSession):
    return await svc.student_own_dashboard(db, user)


@router.get("/ceo/dashboard", response_model=dict[str, Any])
async def ceo_dashboard(
    _: Annotated[User, Depends(require_roles(Role.CEO, Role.HEADMASTER))], user: CurrentUser, db: DbSession
):
    return await svc.ceo_dashboard(db, user)
