import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.permissions import MANAGERS
from app.core.ratelimit import client_ip
from app.models import User
from app.schemas.attendance import HolidayIn, HolidayOut
from app.schemas.common import Page, PageParams, page_params
from app.services import holidays as svc

router = APIRouter(prefix="/holidays", tags=["holidays"])
Manager = Annotated[User, Depends(require_roles(*MANAGERS))]
Params = Annotated[PageParams, Depends(page_params)]


@router.get("", response_model=Page[HolidayOut])
async def list_holidays(_: CurrentUser, db: DbSession, params: Params, year: int | None = Query(None)):
    return await svc.list_holidays(db, params, year)


@router.post("", response_model=HolidayOut, status_code=status.HTTP_201_CREATED)
async def create_holiday(body: HolidayIn, request: Request, db: DbSession, admin: Manager):
    return await svc.create_holiday(db, admin, body, ip=client_ip(request))


@router.delete("/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holiday(holiday_id: uuid.UUID, request: Request, db: DbSession, admin: Manager):
    await svc.delete_holiday(db, admin, holiday_id, ip=client_ip(request))
