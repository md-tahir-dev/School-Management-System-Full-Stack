import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.permissions import MANAGERS
from app.core.ratelimit import client_ip
from app.models import Role, User
from app.schemas.attendance import BulkAttendanceIn, BulkAttendanceResult, RosterOut
from app.services import attendance as svc

router = APIRouter(prefix="/attendance", tags=["attendance"])
Writer = Annotated[User, Depends(require_roles(*MANAGERS, Role.TEACHER))]


@router.get("", response_model=RosterOut)
async def get_roster(
    user: CurrentUser,
    db: DbSession,
    class_id: uuid.UUID = Query(...),
    section_id: uuid.UUID = Query(...),
    date_: date | None = Query(None, alias="date"),
):
    return await svc.get_roster(db, user, class_id, section_id, date_)


@router.post("/bulk", response_model=BulkAttendanceResult)
async def bulk_save(body: BulkAttendanceIn, request: Request, db: DbSession, user: Writer):
    return await svc.bulk_save_attendance(db, user, body, ip=client_ip(request))
