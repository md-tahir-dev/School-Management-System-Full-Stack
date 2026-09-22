import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import DbSession, require_roles
from app.models import Role, User
from app.schemas.common import Page, PageParams, page_params
from app.schemas.parent import ChildDashboard, ChildSummary
from app.schemas.students import StudentDetail
from app.services import parents as svc
from app.services import students as student_svc

# Parents only, and only read endpoints: there is deliberately no write route in this router.
router = APIRouter(prefix="/parent", tags=["parent"])
ParentUser = Annotated[User, Depends(require_roles(Role.PARENT))]
Params = Annotated[PageParams, Depends(page_params)]


@router.get("/children", response_model=Page[ChildSummary])
async def children(user: ParentUser, db: DbSession, params: Params):
    return await svc.list_children(db, user, params)


@router.get("/children/{student_id}/dashboard", response_model=ChildDashboard)
async def child_dashboard(student_id: uuid.UUID, user: ParentUser, db: DbSession):
    return await svc.child_dashboard(db, user, student_id)


@router.get("/children/{student_id}", response_model=StudentDetail)
async def child_profile(student_id: uuid.UUID, user: ParentUser, db: DbSession):
    return await student_svc.get_detail(db, user, student_id)
