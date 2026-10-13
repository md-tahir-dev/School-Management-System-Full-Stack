"""In-app notifications. Producers call `notify` inside their own transaction; the rows commit with it.

Links are role-relative paths ("diary?date=2026-10-08"); the web app prefixes the reader's role."""

import uuid
from collections.abc import Iterable

from sqlalchemy import ColumnElement, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Guardian, Notification, Student, StudentGuardian
from app.models.enums import StudentStatus


async def notify(db: AsyncSession, user_ids: Iterable[uuid.UUID | None], message: str, link: str | None = None) -> int:
    ids = {u for u in user_ids if u is not None}
    if ids:
        await db.execute(insert(Notification), [{"user_id": u, "message": message, "link": link} for u in ids])
    return len(ids)


async def family_user_ids(
    db: AsyncSession, where: ColumnElement[bool], *, students: bool = True, parents: bool = True
) -> set[uuid.UUID]:
    """Login ids of active students matching `where` (a condition on Student) and/or their guardians."""
    live = (Student.is_deleted.is_(False), Student.status == StudentStatus.ACTIVE, where)
    ids: set[uuid.UUID] = set()
    if students:
        ids |= set(await db.scalars(select(Student.user_id).where(*live, Student.user_id.is_not(None))))
    if parents:
        ids |= set(
            await db.scalars(
                select(Guardian.user_id)
                .join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
                .join(Student, Student.id == StudentGuardian.student_id)
                .where(*live, Guardian.user_id.is_not(None))
            )
        )
    return ids
