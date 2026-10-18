from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.permissions import MANAGERS, SCHOOL_WIDE
from app.core.ratelimit import client_ip
from app.models import User
from app.schemas.attendance import BulkAttendanceResult, BulkTeacherAttendanceIn, TeacherRosterOut
from app.services import teacher_attendance as svc

router = APIRouter(prefix="/teacher-attendance", tags=["teacher-attendance"])
Reader = Annotated[User, Depends(require_roles(*SCHOOL_WIDE))]
Manager = Annotated[User, Depends(require_roles(*MANAGERS))]


@router.get("", response_model=TeacherRosterOut)
async def get_roster(_: Reader, db: DbSession, user: CurrentUser, date_: date | None = Query(None, alias="date")):
    return await svc.get_roster(db, user, date_)


@router.post("/bulk", response_model=BulkAttendanceResult)
async def bulk_save(body: BulkTeacherAttendanceIn, request: Request, db: DbSession, admin: Manager):
    return await svc.bulk_save(db, admin, body, ip=client_ip(request))
