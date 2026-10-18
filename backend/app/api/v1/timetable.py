import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.permissions import MANAGERS, SCHOOL_WIDE
from app.core.ratelimit import client_ip
from app.models import Role, User
from app.schemas.timetable import CellIn, ClassTeacherIn, ClassTeacherOut, EntryOut, PeriodIn, PeriodOut, TimetableOut
from app.services import timetable as svc

router = APIRouter(tags=["timetable"])
Manager = Annotated[User, Depends(require_roles(*MANAGERS))]


@router.get("/periods", response_model=list[PeriodOut])
async def list_periods(_: CurrentUser, db: DbSession):
    return await svc.list_periods(db)


@router.post("/periods", response_model=PeriodOut, status_code=status.HTTP_201_CREATED)
async def create_period(body: PeriodIn, request: Request, db: DbSession, actor: Manager):
    return await svc.create_period(db, actor, body, client_ip(request))


@router.put("/periods/{period_id}", response_model=PeriodOut)
async def update_period(period_id: uuid.UUID, body: PeriodIn, request: Request, db: DbSession, actor: Manager):
    return await svc.update_period(db, actor, period_id, body, client_ip(request))


@router.delete("/periods/{period_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_period(period_id: uuid.UUID, request: Request, db: DbSession, actor: Manager):
    await svc.delete_period(db, actor, period_id, client_ip(request))


@router.get("/timetable", response_model=TimetableOut)
async def class_timetable(
    user: Annotated[User, Depends(require_roles(*SCHOOL_WIDE, Role.TEACHER))],
    db: DbSession,
    class_id: uuid.UUID = Query(...),
    section_id: uuid.UUID | None = Query(None),
):
    return await svc.class_timetable(db, user, class_id, section_id)


@router.get("/timetable/me", response_model=TimetableOut)
async def my_timetable(
    user: Annotated[User, Depends(require_roles(Role.TEACHER, Role.STUDENT, Role.PARENT))],
    db: DbSession,
    student_id: uuid.UUID | None = Query(None),
):
    return await svc.my_timetable(db, user, student_id)


@router.put("/timetable/cell", response_model=EntryOut)
async def save_cell(body: CellIn, request: Request, db: DbSession, actor: Manager):
    return await svc.save_cell(db, actor, body, client_ip(request))


@router.delete("/timetable/cell/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cell(entry_id: uuid.UUID, request: Request, db: DbSession, actor: Manager):
    await svc.delete_cell(db, actor, entry_id, client_ip(request))


@router.get("/class-teachers", response_model=list[ClassTeacherOut])
async def list_class_teachers(_: Annotated[User, Depends(require_roles(*SCHOOL_WIDE, Role.TEACHER))], db: DbSession):
    return await svc.list_class_teachers(db)


@router.put("/class-teachers", status_code=status.HTTP_204_NO_CONTENT)
async def set_class_teacher(body: ClassTeacherIn, request: Request, db: DbSession, actor: Manager):
    await svc.set_class_teacher(db, actor, body, client_ip(request))
