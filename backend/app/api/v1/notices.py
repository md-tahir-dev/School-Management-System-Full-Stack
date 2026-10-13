import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.permissions import MANAGERS
from app.core.ratelimit import client_ip
from app.models import Role, User
from app.schemas.common import Page, PageParams, page_params
from app.schemas.notices import (
    AnnouncementIn,
    AnnouncementOut,
    CalendarItem,
    EventIn,
    EventOut,
    NotificationOut,
    UnreadCount,
)
from app.services import notices as svc

router = APIRouter(tags=["announcements & calendar"])
Manager = Annotated[User, Depends(require_roles(*MANAGERS))]
Poster = Annotated[User, Depends(require_roles(*MANAGERS, Role.TEACHER))]
Params = Annotated[PageParams, Depends(page_params)]


@router.get("/announcements", response_model=Page[AnnouncementOut])
async def list_announcements(user: CurrentUser, db: DbSession, params: Params):
    return await svc.list_announcements(db, user, params)


@router.post("/announcements", response_model=AnnouncementOut, status_code=status.HTTP_201_CREATED)
async def create_announcement(body: AnnouncementIn, request: Request, db: DbSession, actor: Poster):
    return await svc.create_announcement(db, actor, body, client_ip(request))


@router.delete("/announcements/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_announcement(announcement_id: uuid.UUID, request: Request, db: DbSession, actor: Poster):
    await svc.delete_announcement(db, actor, announcement_id, client_ip(request))


@router.get("/events", response_model=list[EventOut])
async def list_events(
    user: CurrentUser,
    db: DbSession,
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
):
    return await svc.list_events(db, user, date_from, date_to)


@router.post("/events", response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(body: EventIn, request: Request, db: DbSession, actor: Manager):
    return await svc.create_event(db, actor, body, client_ip(request))


@router.put("/events/{event_id}", response_model=EventOut)
async def update_event(event_id: uuid.UUID, body: EventIn, request: Request, db: DbSession, actor: Manager):
    return await svc.update_event(db, actor, event_id, body, client_ip(request))


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: uuid.UUID, request: Request, db: DbSession, actor: Manager):
    await svc.delete_event(db, actor, event_id, client_ip(request))


@router.get("/calendar", response_model=list[CalendarItem])
async def calendar(
    user: CurrentUser, db: DbSession, date_from: date = Query(alias="from"), date_to: date = Query(alias="to")
):
    """Holidays, events and exam dates in one list (each visible to the reader)."""
    return await svc.calendar(db, user, date_from, date_to)


@router.get("/notifications", response_model=Page[NotificationOut])
async def list_notifications(user: CurrentUser, db: DbSession, params: Params, unread_only: bool = Query(False)):
    return await svc.list_notifications(db, user, params, unread_only)


@router.get("/notifications/unread-count", response_model=UnreadCount)
async def unread_count(user: CurrentUser, db: DbSession):
    return UnreadCount(count=await svc.unread_count(db, user))


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all(user: CurrentUser, db: DbSession):
    await svc.mark_read(db, user, None)


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_one(notification_id: uuid.UUID, user: CurrentUser, db: DbSession):
    await svc.mark_read(db, user, notification_id)
