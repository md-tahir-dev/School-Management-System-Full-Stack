from fastapi import APIRouter
from sqlalchemy import text

from app.core.deps import DbSession

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(db: DbSession):
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}
