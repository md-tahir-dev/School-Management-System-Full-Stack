import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.security import ahash_password, generate_temp_password
from app.models import RefreshToken, Role, User
from app.schemas.fields import Credential
from app.services.audit import log_action


async def revoke_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def set_user_active(
    db: AsyncSession, actor: User, target_id: uuid.UUID, active: bool, *, ip: str | None = None
) -> User:
    target = await db.get(User, target_id)
    if target is None:
        raise not_found("User")
    if not active:
        if target.id == actor.id:
            raise AppError(409, "CANNOT_DEACTIVATE_SELF", "You can't deactivate your own account.")
        if target.role == Role.ADMIN and target.is_active:
            other_admins = await db.scalar(
                select(func.count()).where(User.role == Role.ADMIN, User.is_active.is_(True), User.id != target.id)
            )
            if not other_admins:
                raise AppError(409, "LAST_ADMIN", "This is the last active administrator and can't be deactivated.")
    if target.is_active == active:
        return target
    target.is_active = active
    if not active:
        await revoke_sessions(db, target.id)  # sign them out everywhere
    log_action(
        actor,
        "activate" if active else "deactivate",
        "user",
        target.id,
        {"is_active": {"old": str(not active), "new": str(active)}, "username": target.username},
        db=db,
        ip=ip,
    )
    await db.commit()
    return target


async def reset_password(db: AsyncSession, actor: User, target_id: uuid.UUID, *, ip: str | None = None) -> Credential:
    """New random password, shown to the admin once. The user must change it at next sign-in."""
    target = await db.get(User, target_id)
    if target is None:
        raise not_found("User")
    temp = generate_temp_password()
    target.password_hash = await ahash_password(temp)
    target.must_change_password = True
    target.failed_login_count, target.first_failed_at, target.locked_until = 0, None, None
    await revoke_sessions(db, target.id)
    # the audit entry records that a reset happened, never the password
    log_action(actor, "reset_password", "user", target.id, {"username": target.username}, db=db, ip=ip)
    await db.commit()
    return Credential(username=target.username, temp_password=temp)
