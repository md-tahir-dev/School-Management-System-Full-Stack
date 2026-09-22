"""Race-safe sequential IDs.

`INSERT ... ON CONFLICT DO UPDATE ... RETURNING` takes a row lock until the surrounding transaction
ends, so concurrent creators are serialized and can never receive the same number. If the caller's
transaction rolls back, the increment rolls back too (no gaps)."""

from datetime import date

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Counter


async def next_value(db: AsyncSession, key: str, year: int | None = None) -> int:
    stmt = (
        pg_insert(Counter)
        .values(key=key, year=year or 0, last_value=1)
        .on_conflict_do_update(index_elements=["key", "year"], set_={"last_value": Counter.last_value + 1})
        .returning(Counter.last_value)
    )
    return (await db.execute(stmt)).scalar_one()


def format_roll_no(year: int, n: int) -> str:
    return f"{year}-{n:04d}"


def format_employee_id(n: int) -> str:
    return f"EMP-{n:04d}"


def format_receipt_no(on: date, n: int) -> str:
    return f"RCPT-{on:%Y%m}-{n:05d}"


async def next_roll_no(db: AsyncSession, year: int) -> str:
    return format_roll_no(year, await next_value(db, "roll_no", year))


async def next_employee_id(db: AsyncSession) -> str:
    return format_employee_id(await next_value(db, "employee_id", 0))


async def next_receipt_no(db: AsyncSession, on: date) -> str:
    return format_receipt_no(on, await next_value(db, "receipt", on.year * 100 + on.month))
