import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError, unauthorized
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    needs_rehash,
    validate_password_strength,
    verify_password,
)
from app.models import RefreshToken, User
from app.services.audit import audit


@dataclass
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str
    user: User


def _now() -> datetime:
    return datetime.now(UTC)


def _invalid_credentials() -> AppError:
    return unauthorized("Incorrect username or password.", code="invalid_credentials")


def _locked(until: datetime) -> AppError:
    seconds = max(1, int((until - _now()).total_seconds()))
    minutes = -(-seconds // 60)
    return AppError(
        429,
        "account_locked",
        f"Too many failed attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
        details={"retry_after_seconds": seconds},
        headers={"Retry-After": str(seconds)},
    )


async def _issue(
    db: AsyncSession,
    user: User,
    *,
    family_id: uuid.UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[IssuedTokens, RefreshToken]:
    access, expires_in = create_access_token(user.id, user.role.value)
    raw, hashed = generate_refresh_token()
    row = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        token_hash=hashed,
        expires_at=_now() + timedelta(days=settings.refresh_token_days),
        ip=ip,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(row)
    return IssuedTokens(access, expires_in, raw, user), row


async def login(
    db: AsyncSession, username: str, password: str, *, ip: str | None, user_agent: str | None
) -> IssuedTokens:
    now = _now()
    normalized = username.strip().lower()  # usernames are stored lowercase
    user = await db.scalar(select(User).where(User.username == normalized))

    if user is None:
        verify_password(password, None)  # burn the same time as a real check
        raise _invalid_credentials()

    if user.locked_until and user.locked_until > now:
        raise _locked(user.locked_until)

    if not verify_password(password, user.password_hash):
        window = timedelta(minutes=settings.login_window_minutes)
        if user.first_failed_at is None or now - user.first_failed_at > window:
            user.failed_login_count, user.first_failed_at = 1, now
        else:
            user.failed_login_count += 1
        newly_locked = user.failed_login_count >= settings.login_max_attempts
        if newly_locked:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            user.failed_login_count, user.first_failed_at = 0, None
            audit(db, user_id=user.id, action="lock", entity="user", entity_id=user.id, ip=ip)
        await db.commit()
        raise _locked(user.locked_until) if newly_locked else _invalid_credentials()

    if not user.is_active:
        raise AppError(403, "account_disabled", "This account has been deactivated. Contact the school office.")

    user.failed_login_count, user.first_failed_at, user.locked_until = 0, None, None
    user.last_login = now
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    issued, _ = await _issue(db, user, ip=ip, user_agent=user_agent)
    audit(db, user_id=user.id, action="login", entity="user", entity_id=user.id, ip=ip)
    await db.commit()
    return issued


async def _revoke_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


async def refresh(db: AsyncSession, raw_token: str | None, *, ip: str | None, user_agent: str | None) -> IssuedTokens:
    """Rotates the refresh token. Presenting an already-used token revokes the whole login family
    (it means the token leaked), except within a short grace window that absorbs multi-tab races."""
    invalid = unauthorized("Your session has expired. Please sign in again.", code="invalid_refresh_token")
    if not raw_token:
        raise invalid
    now = _now()
    row = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)).with_for_update()
    )
    if row is None:
        raise invalid

    if row.revoked_at is not None:
        within_grace = (now - row.revoked_at).total_seconds() <= settings.refresh_reuse_grace_seconds
        if not (within_grace and row.replaced_by is not None):
            await _revoke_family(db, row.family_id)
            await db.commit()
        raise invalid

    if row.expires_at <= now:
        raise invalid

    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        await _revoke_family(db, row.family_id)
        await db.commit()
        raise invalid

    issued, new_row = await _issue(db, user, family_id=row.family_id, ip=ip, user_agent=user_agent)
    row.revoked_at = now
    row.replaced_by = new_row.id
    await db.commit()
    return issued


async def logout(db: AsyncSession, raw_token: str | None) -> None:
    if not raw_token:
        return
    row = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if row is not None:
        await _revoke_family(db, row.family_id)
        await db.commit()


async def change_password(
    db: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
    *,
    ip: str | None,
    user_agent: str | None,
) -> IssuedTokens:
    if not verify_password(current_password, user.password_hash):
        raise AppError(400, "wrong_password", "Your current password is incorrect.")
    problems = validate_password_strength(new_password)
    if problems:
        raise AppError(422, "weak_password", "Choose a stronger password.", details=problems)
    if new_password == current_password:
        raise AppError(422, "weak_password", "Your new password must be different from the current one.")

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    # sign out every other device, then keep this one signed in with a fresh session
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    issued, _ = await _issue(db, user, ip=ip, user_agent=user_agent)
    audit(db, user_id=user.id, action="change_password", entity="user", entity_id=user.id, ip=ip)
    await db.commit()
    return issued
