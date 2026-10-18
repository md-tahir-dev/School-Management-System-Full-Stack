from fastapi import APIRouter

from app.core.config import settings
from app.core.demo import demo_accounts
from app.core.deps import DbSession
from app.schemas.settings import PublicConfig
from app.services.settings import get_school_settings

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/config", response_model=PublicConfig)
async def public_config(db: DbSession):
    """Branding for the login page. Demo credentials are included ONLY when APP_ENV=demo."""
    row = await get_school_settings(db)
    await db.commit()
    return PublicConfig(
        school_name=row.name,
        slogan=row.slogan,
        logo_url=row.logo_url,
        favicon_url=row.favicon_url,
        login_image_url=row.login_image_url,
        app_env=settings.app_env,
        demo_accounts=demo_accounts(),
    )
