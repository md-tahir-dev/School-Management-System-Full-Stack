import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.permissions import SCHOOL_WIDE
from app.core.security import ahash_password, generate_temp_password, validate_password_strength
from app.models import RefreshToken, Role, User
from app.schemas.auth import UserCreate, UserUpdate
from app.schemas.fields import Credential
from app.services.audit import log_action
from app.services.dbutil import flush_or_conflict


async def revoke_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def _get_manageable(db: AsyncSession, actor: User, target_id: uuid.UUID) -> User:
    """Admins manage every account; a headmaster only teacher/student/parent ones (others look absent)."""
    target = await db.get(User, target_id)
    if target is None or (actor.role != Role.ADMIN and target.role in SCHOOL_WIDE):
        raise not_found("User")
    return target


async def create_user(db: AsyncSession, actor: User, body: UserCreate, *, ip: str | None = None) -> Credential:
    temp = generate_temp_password()
    user = User(
        username=body.username.lower(),
        full_name=body.full_name,
        role=body.role,
        password_hash=await ahash_password(temp),
        must_change_password=True,
    )
    db.add(user)
    await flush_or_conflict(db, "That username is already taken.", code="USERNAME_TAKEN", field="username")
    log_action(actor, "create", "user", user.id, {"username": user.username, "role": user.role.value}, db=db, ip=ip)
    await db.commit()
    return Credential(username=user.username, temp_password=temp)


async def set_user_active(
    db: AsyncSession, actor: User, target_id: uuid.UUID, active: bool, *, ip: str | None = None
) -> User:
    target = await _get_manageable(db, actor, target_id)
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


async def reset_password(
    db: AsyncSession, actor: User, target_id: uuid.UUID, password: str | None = None, *, ip: str | None = None
) -> Credential:
    """Sets `password`, or a random one the user must change at next sign-in. Shown to the actor once."""
    target = await _get_manageable(db, actor, target_id)
    if password is not None:
        problems = validate_password_strength(password)
        if problems:
            raise AppError(422, "weak_password", "Choose a stronger password.", fields={"password": problems[0]})
    new = password or generate_temp_password()
    target.password_hash = await ahash_password(new)
    target.must_change_password = password is None
    target.failed_login_count, target.first_failed_at, target.locked_until = 0, None, None
    await revoke_sessions(db, target.id)
    # the audit entry records that a reset happened, never the password
    log_action(actor, "reset_password", "user", target.id, {"username": target.username}, db=db, ip=ip)
    await db.commit()
    return Credential(username=target.username, temp_password=new)


async def update_user(db: AsyncSession, actor: User, target_id: uuid.UUID, body: UserUpdate, *, ip: str | None = None):
    target = await _get_manageable(db, actor, target_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "username" in changes:
        changes["username"] = changes["username"].lower()
    diff = {k: {"old": getattr(target, k), "new": v} for k, v in changes.items() if getattr(target, k) != v}
    for k in diff:
        setattr(target, k, changes[k])
    await flush_or_conflict(db, "That username is already taken.", code="USERNAME_TAKEN", field="username")
    if diff:
        log_action(actor, "update", "user", target.id, diff, db=db, ip=ip)
    await db.commit()
    return target
