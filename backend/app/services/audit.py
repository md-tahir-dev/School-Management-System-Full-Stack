import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def audit(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    action: str,
    entity: str,
    entity_id: Any = None,
    diff: dict | None = None,
    ip: str | None = None,
) -> None:
    """Adds an audit row to the current transaction (committed together with the change itself)."""
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            diff=diff,
            ip=ip,
        )
    )


def log_action(
    user, action: str, entity: str, entity_id: Any = None, diff: dict | None = None, *, db, ip: str | None = None
):
    """Phase 2 helper: `log_action(user, action, entity, entity_id, diff, db=session)`.
    `user` may be None for system actions (seed)."""
    audit(db, user_id=getattr(user, "id", None), action=action, entity=entity, entity_id=entity_id, diff=diff, ip=ip)
