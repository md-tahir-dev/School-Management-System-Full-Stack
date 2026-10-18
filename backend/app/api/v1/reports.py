import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.permissions import SCHOOL_WIDE
from app.models import User
from app.schemas.attendance import ClassAttendanceReport, LowAttendanceOut, OverviewOut
from app.services import reports as svc

router = APIRouter(prefix="/reports", tags=["reports"])
SchoolWide = Annotated[User, Depends(require_roles(*SCHOOL_WIDE))]


@router.get("/attendance/class", response_model=ClassAttendanceReport)
async def class_report(
    user: CurrentUser,
    db: DbSession,
    class_id: uuid.UUID = Query(...),
    section_id: uuid.UUID = Query(...),
    from_: date = Query(..., alias="from"),
    to: date = Query(...),
    format: str | None = Query(None),
):
    report = await svc.class_report(db, user, class_id, section_id, from_, to)
    if format == "csv":
        return PlainTextResponse(svc.class_report_csv(report), media_type="text/csv")
    return report


@router.get("/attendance/overview", response_model=OverviewOut)
async def overview(_: SchoolWide, db: DbSession, user: CurrentUser, date_: date = Query(..., alias="date")):
    return await svc.overview(db, user, date_)


@router.get("/attendance/low", response_model=LowAttendanceOut)
async def low_attendance(_: SchoolWide, db: DbSession, user: CurrentUser, threshold: int = Query(75, ge=1, le=100)):
    return await svc.low_attendance(db, user, threshold)
