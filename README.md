# School Management System

FastAPI + PostgreSQL backend, Next.js 14 frontend. White-label: school name, slogan and logo come from the database, not the code.

- **Status, roadmap, open decisions:** [ROADMAP.md](ROADMAP.md)
- **Architecture, conventions, gotchas:** [CLAUDE.md](CLAUDE.md)
- **API reference:** http://localhost:8000/docs once running

## Run

```bash
cp .env.example .env          # set POSTGRES_PASSWORD and JWT_SECRET (openssl rand -hex 32)
docker compose up --build     # web :3000, api :8000
```

Without Docker (Python 3.12, Node 20+, PostgreSQL 15+ running):

```bash
cd backend && pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+asyncpg://sms:sms@localhost:5432/sms JWT_SECRET=$(openssl rand -hex 32)
alembic upgrade head && APP_ENV=demo python -m scripts.seed
APP_ENV=demo uvicorn app.main:app --port 8000

cd frontend && npm install && npm run dev    # proxies /api/v1/* to :8000
```

Windows: `run_services.bat` / `stop_services.bat` (creates `backend/.env` on first run; fill it in, run again).

Demo logins (`APP_ENV=demo`), password `Demo@12345`: `admin`, `headmaster`, `ceo`, `teacher`, `student`, `parent`.
Outside demo mode the seed creates one admin from `FIRST_ADMIN_USERNAME` / `FIRST_ADMIN_PASSWORD`.

## Test

```bash
# backend: needs an empty database sms_test; schema is built from the real migrations
TEST_DATABASE_URL=postgresql+asyncpg://sms:sms@localhost:5432/sms_test pytest -q   # 299 tests
ruff check . && ruff format --check .

cd frontend && npm run lint && npm run typecheck && npm run build
```

CI (`.github/workflows/ci.yml`) runs all of the above on every push.
