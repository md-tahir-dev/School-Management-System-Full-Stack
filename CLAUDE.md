# Working on this codebase

Read [ROADMAP.md](ROADMAP.md) for what is built and what is next.

## Layout

```
backend/app/
  api/v1/      thin routers, one file per module, wired in router.py
  services/    all business logic + row-level scoping (scoping.py)
  models/      SQLAlchemy 2 async; enums.py holds Role and status enums
  schemas/     Pydantic in/out models
  core/        config, security (Argon2, JWT), deps (auth guards), permissions, errors, ratelimit
backend/alembic/versions/   one migration per feature slice (0001-0006)
backend/scripts/seed.py     idempotent; APP_ENV=demo seeds full sample data via the real services
frontend/
  app/(dashboard)/[role]/   one route tree for all roles; [...slug] = "coming in phase N" page
  lib/role-config.ts        every role's sidebar (single source of truth)
  lib/api.ts, lib/auth.tsx  fetch client with in-memory token + silent refresh
  lib/api-types.ts          generated: npm run gen:api (API must be running)
```

## Rules that are easy to break

- **Authorization is two layers.** Route: `require_roles` / `require_permission` (`core/deps.py`, matrix in `core/permissions.py`). Rows: service layer (teacher → assigned classes, parent → linked children, student → self). Out-of-scope records return **404, never 403**. Any new role or endpoint must be added to `tests/test_rbac_scoping.py`.
- **Roles live in four places:** `models/enums.py` (Role), `core/permissions.py`, `frontend/lib/role-config.ts`, `frontend/middleware.ts` (plus `lib/api-types.ts` via `npm run gen:api`). Change them together.
- **Role checks use groups, not hand-listed roles.** Backend: `SCHOOL_WIDE` (admin, ceo, headmaster: unscoped readers) and `MANAGERS` (admin, headmaster: settings/academics/attendance/results/finance writers) in `core/permissions.py`. Students and teachers writes stay admin-only; creating admin/CEO/headmaster accounts is admin-only, and a headmaster may activate/deactivate/reset only teacher, student and parent logins (`services/users._get_manageable`). Frontend mirrors them with `isSchoolWide()` / `isManager()` in `lib/role-config.ts`.
- **Branding is data.** School name, slogan, logo → `school_settings` row → `GET /public/config` (unauthenticated) → login page, sidebar, tab title/favicon (`app/layout.tsx` `generateMetadata`, revalidated every 60 s), result card, result PDF. Never hardcode a school name in UI.
- **Forms** use `components/forms.tsx` (`useApiForm`, `TextField`, `SelectField`): the API validates, and its `fields` errors (keyed like `guardian.father_cnic`) show next to the inputs. Use `errorText()` from `lib/api.ts` for toasts.
- **Multi-row writes are one transaction** (student/teacher registration: counters, guardian, users, ledger, audit). Use `services/dbutil.flush_or_conflict` for unique-violation → 409.
- **Counters** (`services/counters.py`, roll no `YYYY-NNNN`, `EMP-NNNN`) use `INSERT ... ON CONFLICT DO UPDATE RETURNING`; don't replace with SELECT-then-UPDATE.
- **Money is `Decimal`**, rounded half-up (`utils/money.py`). Never float.
- **Usernames are stored lowercase.**
- **Notifications**: producers call `services/notify.notify()` inside their transaction; links are role-relative paths.
- **Model gotcha**: a column named `date` shadows the `date` type in later annotations in the same class; give such columns an explicit `nullable=`.
- **Errors** have one shape: `{"detail", "code", "fields", "request_id"}` (`core/errors.py`); `frontend/lib/api.ts` depends on it.
- **Audit**: admin writes call `services/audit.log_action()`.
- **Schema changes** need an Alembic migration; `alembic check` must report no drift.

## Auth model

Access token: 15-min JWT, memory only. Refresh token: opaque, httpOnly cookie, stored as SHA-256, rotated on every use, reuse revokes the session (10 s grace for two tabs). Browser only talks to the Next origin; Next rewrites `/api/v1/*` to FastAPI (`BACKEND_URL` is build-time). The `sms_role` cookie is UX routing only, not trusted. Lockout: 5 fails / 15 min; per-IP limit 30 / 15 min.

## Known limitations

- Rate limiter is in-process; Redis is in docker-compose but unused. Move to Redis before running >1 API worker.
- Photos and logos are public (random names); diary/homework/material files go through `GET /uploads/{folder}/{name}`, which needs login and is row-scoped (`services/content.assert_can_download`). New upload folders are private unless mounted in `main.py`.
- Duplicate-student check can race under two identical concurrent requests.

## Deviations from the original spec

`classes.sort_order` (not `order`); `fee_ledger.paid_amount` + `fine_applied_at`; extra `users` lockout columns; `refresh_tokens` table; `school_settings.fail_if_any_subject_failed`; student status `expelled` (not `transferred`); `GET /classes/{id}/subjects`, `/fee-structures`, `/periods`, `/timetable*`, `/class-teachers`, `/diary`, `/events`, `/calendar`, `/salary`, `/tests/me` return plain arrays; all other lists are paginated (default `page_size` 10).

## Agent routing policy

Delegate matching work to the subagent named below instead of doing it in the main thread. Use the cheapest model that does the job reliably; escalate only when that fails or the task is inherently ambiguous. Agents live in [.claude/agents/](.claude/agents/) and each carries this repo's rules.

| Task | Agent |
|---|---|
| Bugs with unclear root cause, races, auth/session logic, cross-file state | `debugger` (opus) |
| Models, Alembic migrations, data modeling | `schema-designer` (sonnet) |
| pytest against an existing interface | `test-writer` (sonnet; haiku for pure boilerplate) |
| Codebase search, "where is X defined" | built-in `Explore` (haiku) |
| Review of a diff | `code-reviewer` (sonnet, read-only) |
| Auth, permissions/RBAC scoping, uploads, secrets, cookies/CORS, new network access | `security-reviewer` (opus, read-only) |
| Next.js/React components, Tailwind tokens, accessibility | `ui-engineer` (sonnet) |

Never do heavy multi-file debugging in the main thread: dispatch `debugger` and review its patch. Subagents report back; the main thread reviews their work, runs the gates (pytest, `alembic check`, ruff, `npm run lint && npm run typecheck && npm run build`), updates ROADMAP.md and commits.
