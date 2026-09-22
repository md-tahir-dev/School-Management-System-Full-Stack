from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SchoolSettings


async def get_school_settings(db: AsyncSession) -> SchoolSettings:
    """The app has exactly one settings row; create a placeholder if the DB was never seeded."""
    row = await db.scalar(select(SchoolSettings).order_by(SchoolSettings.created_at).limit(1))
    if row is None:
        row = SchoolSettings(name="My School")
        db.add(row)
        await db.flush()
    return row
