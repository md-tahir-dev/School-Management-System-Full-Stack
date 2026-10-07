"""Holidays module: simple CRUD, paginated by year. Weekly-off days live on `school_settings` instead
(they're a rule, not a list of dates) and are read directly from there by the attendance service."""

import uuid
from datetime import date

from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found
from app.models import SchoolHoliday, User
from app.schemas.attendance import HolidayIn
from app.schemas.common import Page, PageParams
from app.services.audit import log_action
from app.services.dbutil import flush_or_conflict
from app.utils.pagination import paginate


async def list_holidays(db: AsyncSession, params: PageParams, year: int | None) -> Page:
    from app.schemas.attendance import HolidayOut

    stmt = select(SchoolHoliday).order_by(SchoolHoliday.date)
    if year:
        stmt = stmt.where(extract("year", SchoolHoliday.date) == year)
    return await paginate(db, stmt, params, HolidayOut)


async def create_holiday(db: AsyncSession, actor: User, body: HolidayIn, ip: str | None) -> SchoolHoliday:
    holiday = SchoolHoliday(date=body.date, name=body.name, created_by=actor.id)
    db.add(holiday)
    await flush_or_conflict(db, f"A holiday is already recorded on {body.date}.", field="date")
    log_action(actor, "create", "holiday", holiday.id, {"date": str(body.date), "name": body.name}, db=db, ip=ip)
    await db.commit()
    return holiday


async def delete_holiday(db: AsyncSession, actor: User, holiday_id: uuid.UUID, ip: str | None) -> None:
    holiday = await db.get(SchoolHoliday, holiday_id)
    if holiday is None:
        raise not_found("Holiday")
    await db.delete(holiday)
    log_action(actor, "delete", "holiday", holiday_id, {"date": str(holiday.date), "name": holiday.name}, db=db, ip=ip)
    await db.commit()


async def holiday_on(db: AsyncSession, day: date) -> SchoolHoliday | None:
    return await db.scalar(select(SchoolHoliday).where(SchoolHoliday.date == day))
