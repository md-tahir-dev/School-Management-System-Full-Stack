from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Request, UploadFile

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.permissions import MANAGERS
from app.core.ratelimit import client_ip
from app.models import User
from app.schemas.academic import LogoOut
from app.schemas.settings import SchoolSettingsOut, SchoolSettingsUpdate
from app.services.audit import audit
from app.services.settings import get_school_settings
from app.services.storage import StorageBackend, get_storage

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SchoolSettingsOut)
async def read_settings(_: CurrentUser, db: DbSession):
    row = await get_school_settings(db)
    await db.commit()
    return row


@router.put("", response_model=SchoolSettingsOut)
async def update_settings(
    body: SchoolSettingsUpdate,
    request: Request,
    db: DbSession,
    admin: User = Depends(require_roles(*MANAGERS)),
):
    row = await get_school_settings(db)
    changes = body.model_dump(exclude_unset=True)
    diff = {}
    for field, new in changes.items():
        old = getattr(row, field)
        if old != new:
            diff[field] = {"old": str(old) if old is not None else None, "new": str(new) if new is not None else None}
            setattr(row, field, new)
    if diff:
        audit(
            db,
            user_id=admin.id,
            action="update",
            entity="school_settings",
            entity_id=row.id,
            diff=diff,
            ip=client_ip(request),
        )
    await db.commit()
    return row


# White-label images: stored under the public "logos" upload folder. Login photos may be larger.
BrandingKind = Literal["logo", "favicon", "login_image"]
_BRANDING_MAX_BYTES = {"logo": 2 * 1024 * 1024, "favicon": 2 * 1024 * 1024, "login_image": 5 * 1024 * 1024}


async def _set_branding(db, storage: StorageBackend, actor: User, kind: str, url: str | None, ip: str | None):
    row = await get_school_settings(db)
    field = f"{kind}_url"
    old = getattr(row, field)
    setattr(row, field, url)
    audit(
        db,
        user_id=actor.id,
        action="update",
        entity="school_settings",
        entity_id=row.id,
        diff={field: {"old": old, "new": url}},
        ip=ip,
    )
    await db.commit()
    await storage.delete(old)
    return row


@router.post("/branding/{kind}", response_model=SchoolSettingsOut)
async def upload_branding(
    kind: BrandingKind,
    request: Request,
    db: DbSession,
    storage: Annotated[StorageBackend, Depends(get_storage)],
    actor: User = Depends(require_roles(*MANAGERS)),
    file: UploadFile = File(...),
):
    """Logo, favicon (square PNG works best) or login-page image. JPEG, PNG or WebP, checked from the bytes."""
    url = await storage.save_image(file, "logos", _BRANDING_MAX_BYTES[kind])
    return await _set_branding(db, storage, actor, kind, url, client_ip(request))


@router.delete("/branding/{kind}", response_model=SchoolSettingsOut)
async def clear_branding(
    kind: BrandingKind,
    request: Request,
    db: DbSession,
    storage: Annotated[StorageBackend, Depends(get_storage)],
    actor: User = Depends(require_roles(*MANAGERS)),
):
    """Back to the default (no logo / logo as favicon / plain login page)."""
    return await _set_branding(db, storage, actor, kind, None, client_ip(request))


@router.post("/logo", response_model=LogoOut)
async def upload_logo(
    request: Request,
    db: DbSession,
    storage: Annotated[StorageBackend, Depends(get_storage)],
    admin: User = Depends(require_roles(*MANAGERS)),
    file: UploadFile = File(...),
):
    """JPEG, PNG or WebP, max 2 MB. The type is checked from the file's bytes, not its name."""
    row = await get_school_settings(db)
    url = await storage.save_image(file, "logos")
    old = row.logo_url
    row.logo_url = url
    audit(
        db,
        user_id=admin.id,
        action="update",
        entity="school_settings",
        entity_id=row.id,
        diff={"logo_url": {"old": old, "new": url}},
        ip=client_ip(request),
    )
    await db.commit()
    await storage.delete(old)
    return LogoOut(logo_url=url)
