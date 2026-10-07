
---

## Phase 3 — Attendance & Results

Backend only (frontend is Part F of the Phase 3 spec and hasn't been built — see below).

### What's new
- **Migration `0003`**: `school_holidays`, `exam_subjects`, publish-workflow columns on `exams`, `status`/`remarks` on `results`, `is_absent` on `result_items`, `remarks`/`updated_by` on attendance tables, and new `school_settings` columns (`weekly_off_days`, `attendance_alert_threshold`, `backdate_limit_days`, `timezone`). Verified: upgrade → downgrade → upgrade on a clean DB, `alembic check` reports zero drift.
- **Attendance**: roster, bulk upsert (Postgres `ON CONFLICT`), holiday/weekly-off/future-date/backdate-limit rules, the documented percentage formula, class/overview/low-attendance reports, teacher attendance, CSV export.
- **Results**: exam CRUD with a per-exam subject snapshot, grid + per-student marks entry, publish/unpublish workflow, SQL-window-function ranking (ties share rank), analytics, a WeasyPrint+Jinja2 result-card PDF (bundled Noto Sans + Noto Nastaliq Urdu fonts so Urdu names render correctly), bulk "one PDF per class" export, CSV export.
- **Dashboards**: Parent dashboard's `latest_result`/`attendance` placeholders are now filled; new `GET /student/dashboard` and `GET /ceo/dashboard`; student profile now reports `attendance_percentage` and `latest_result_grade`.
- **Bug fix carried over from Phase 2 notes**: the `MissingGreenlet` error hit while building `exams.py` in an earlier session was root-caused to inconsistent rollback handling. Fixed by extracting the tested `flush_or_conflict` helper (`app/services/dbutil.py`) that `academic.py` already relied on, and having `exams.py` use the same one instead of a re-derived version.

### Test results (this session, real Postgres, not mocked)
```
217 passed  (184 Phase 1+2 regression, unchanged behavior except one test updated to match
             the now-implemented dashboard fields — 33 new Phase 3 tests)
```
Covers: roster exclusion rules, upsert semantics, date/holiday/weekly-off/backdate validation, the
documented 89.47% percentage example, teacher/parent scope enforcement, absence-notification dedup,
grade boundary rounding (89.995→A+, 49.995→D, 49.994→F), the fail-if-any-subject-failed toggle,
obtained>total rejection, absent-forces-zero, draft/complete status, rank ties `[1,2,2,4]` and
re-ranking on edit, exam-subject snapshot survival, teacher-lock-after-publish + admin-reason audit,
unpublished-result visibility per role, analytics against a hand-computed example, exam deletion
guard, and the result PDF (draft watermark, publish removes it, bulk "one page per student" export).

### Seed data
`scripts/seed.py` now also seeds: 3 holidays, ~30 school days of attendance per section (one student
deliberately kept under 75%), 10 days of teacher attendance, and one Mid Term exam per class with a
tie, a failed subject, an absent subject, and one incomplete (draft) student — Class 1's exam is
published, the others are left as drafts to demonstrate the workflow. Verified idempotent: ran twice
against a clean DB, second run produced identical row counts and reported "0 created, already
present" for everything.

### Known limitations / what's not in this delivery
- **Frontend (Part F) is not built.** Every Phase 3 screen (teacher attendance marking, admin
  attendance reports, the exams/marks-entry UI, result views, dashboard cards) still needs to be
  built against the API below.
- Expelling/withdrawing a student doesn't auto-revoke their login (same limitation noted in Phase 2).
- The bulk "download all cards" PDF re-fetches each result individually rather than batching; fine at
  seed-data scale, would want optimizing for a very large class.

### New endpoints (see `/docs` once running for the full schema)
```
GET/POST         /attendance, /attendance/bulk
GET               /students/{id}/attendance/summary, /students/{id}/attendance/calendar
GET/POST/DELETE   /holidays
GET/POST          /teacher-attendance, /teacher-attendance/bulk
GET               /teachers/{id}/attendance/summary
GET               /reports/attendance/class, /reports/attendance/overview, /reports/attendance/low
GET/POST/PUT/DELETE  /exams, /exams/{id}, /exams/{id}/subjects, /exams/{id}/subjects/reset
POST              /exams/{id}/publish, /exams/{id}/unpublish
GET/PUT           /exams/{id}/marks-sheet, /exams/{id}/marks
GET/PUT           /exams/{id}/students/{student_id}/entry
GET               /exams/{id}/results, /exams/{id}/results/export, /exams/{id}/results/pdf, /exams/{id}/analytics, /exams/{id}/marks-progress
GET               /students/{id}/results, /results/{id}, /results/{id}/pdf
GET               /student/dashboard, /ceo/dashboard
```

### Run it
```bash
cp .env.example .env      # set POSTGRES_PASSWORD and JWT_SECRET
docker compose up --build
# or, without Docker:
cd backend && alembic upgrade head && APP_ENV=demo python -m scripts.seed
TEST_DATABASE_URL=postgresql+asyncpg://sms:sms@localhost:5432/sms_test pytest -q
```
Demo logins, all with password `Demo@12345`: `ceo`, `admin`, `teacher`, `student`, `parent`.

### About your uploaded `sms.zip`
You sent a version with your own in-progress edits (modified models + new `attendance.py`/`exams.py`/
`grading.py`/`scoping.py` changes, on top of the Phase 2 git history). I did not merge that branch into
this delivery — it looked like a separate, partial, untested attempt at the same work, and reconciling
two independent implementations line-by-line would have cost more time than it saved and risked
reintroducing the exact kind of bug this phase already had history with. This zip is my own
implementation, built incrementally and verified at each step (real Postgres, real migrations, real
test runs, real rendered PDFs) rather than merged from two sources. If you specifically want something
preserved from your edits, tell me what it was and I'll fold it in.
