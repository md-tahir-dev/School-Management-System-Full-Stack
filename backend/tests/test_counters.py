import asyncio
import uuid
from datetime import date

from app.db.session import SessionLocal
from app.services.counters import (
    format_employee_id,
    format_receipt_no,
    format_roll_no,
    next_employee_id,
    next_receipt_no,
    next_roll_no,
    next_value,
)


def test_formats():
    assert format_roll_no(2026, 7) == "2026-0007"
    assert format_roll_no(2026, 12345) == "2026-12345"
    assert format_employee_id(42) == "EMP-0042"
    assert format_receipt_no(date(2026, 9, 3), 15) == "RCPT-202609-00015"


async def test_sequence_increments_and_is_scoped_by_key_and_year():
    key = f"k-{uuid.uuid4().hex[:6]}"
    async with SessionLocal() as db:
        assert [await next_value(db, key, 2026) for _ in range(3)] == [1, 2, 3]
        assert await next_value(db, key, 2027) == 1  # new year restarts
        assert await next_value(db, key + "-other", 2026) == 1
        await db.commit()
    async with SessionLocal() as db:
        assert await next_value(db, key, 2026) == 4  # persisted across transactions


async def test_rollback_does_not_burn_numbers():
    key = f"k-{uuid.uuid4().hex[:6]}"
    async with SessionLocal() as db:
        await next_value(db, key)
        await db.commit()
    async with SessionLocal() as db:
        assert await next_value(db, key) == 2
        await db.rollback()
    async with SessionLocal() as db:
        assert await next_value(db, key) == 2


async def test_concurrent_callers_never_get_duplicates():
    key = f"k-{uuid.uuid4().hex[:6]}"

    async def one() -> int:
        async with SessionLocal() as db:
            value = await next_value(db, key, 2026)
            await asyncio.sleep(0.01)  # hold the row lock a moment to force contention
            await db.commit()
            return value

    values = await asyncio.gather(*[one() for _ in range(25)])
    assert sorted(values) == list(range(1, 26))


async def test_typed_generators():
    async with SessionLocal() as db:
        roll = await next_roll_no(db, 2099)
        assert roll == "2099-0001"
        emp = await next_employee_id(db)
        assert emp.startswith("EMP-")
        r1 = await next_receipt_no(db, date(2099, 3, 5))
        r2 = await next_receipt_no(db, date(2099, 3, 28))
        r3 = await next_receipt_no(db, date(2099, 4, 1))
        assert (r1, r2, r3) == ("RCPT-209903-00001", "RCPT-209903-00002", "RCPT-209904-00001")
        await db.rollback()
