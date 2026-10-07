"""Small helpers shared across service modules."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError


async def flush_or_conflict(db: AsyncSession, message: str, *, code: str = "CONFLICT", field: str | None = None):
    """Flush the current unit of work; turn a unique/FK violation into a 409 AppError.

    Only ever called with a plain `await db.commit()` still ahead of it in the same request (see
    `app.db.session.get_db`, which rolls back once more if an exception escapes the route). Doing the
    rollback here AND letting the outer handler roll back again is safe as long as nothing after this
    call touches the session before the AppError is raised — don't add code between this and the
    caller's `raise`/return that reads or writes `db` on the failure path.
    """
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, code, message, fields={field: message} if field else None) from exc
