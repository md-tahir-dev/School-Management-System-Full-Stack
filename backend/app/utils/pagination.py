import math
from collections.abc import Callable

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.common import Page, PageParams


def like_pattern(q: str) -> str:
    """Contains-match pattern with LIKE wildcards in user input escaped."""
    escaped = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


async def paginate(
    db: AsyncSession, stmt: Select, params: PageParams, schema: type, *, row_mapper: Callable | None = None
) -> Page:
    """Server-side pagination: one COUNT plus one LIMIT/OFFSET query. `stmt` must already be ordered.
    Select several columns/entities and pass `row_mapper(row) -> dict | object` to shape each item."""
    total = (await db.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    result = await db.execute(stmt.limit(params.page_size).offset(params.offset))
    rows = result.all() if row_mapper else result.scalars().all()
    return Page(
        items=[schema.model_validate(row_mapper(r) if row_mapper else r) for r in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
        pages=math.ceil(total / params.page_size) if total else 0,
    )
