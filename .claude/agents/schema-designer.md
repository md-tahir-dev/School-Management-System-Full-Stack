---
name: schema-designer
description: Designs SQLAlchemy models and writes Alembic migrations for well-specified data changes.
model: sonnet
tools: Read, Grep, Glob, Bash, Edit, Write
---
Read CLAUDE.md first.

- Models live in `backend/app/models/`, mixins in `app/db/base.py`. Enums are VARCHAR via `enum_col` (no native PG enums), so adding an enum value needs no migration.
- One migration per change in `backend/alembic/versions/`, named `YYYYMMDD_NNNN_<slug>.py`. Write a working `downgrade()`.
- Verify: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`, then `alembic check` must report no drift.
- Money is `Numeric(12, 2)` and `Decimal`; never float. Add DB constraints (unique, FK `ondelete`) rather than app-only checks.
- Update `scripts/seed.py` if the change affects demo data; the seed must stay idempotent.
