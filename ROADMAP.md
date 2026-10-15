# Status & Roadmap

_Updated 2026-10-08. All six phases now have a backend and a UI; nothing below is committed yet._

## Built

| Module | Backend | Frontend |
|---|---|---|
| Auth (login, refresh, lockout, change password) | ✅ | ✅ |
| Users (create admin/CEO/headmaster, activate, reset password) | ✅ | ✅ |
| Settings: school profile + logo (branding) | ✅ | ✅ |
| Settings: years, classes, sections, subjects, fee structure, periods, class teachers | ✅ | ✅ |
| Settings: attendance/result rules, holidays | ✅ | ✅ |
| Students (register, profile, status, discount, ledger) | ✅ | ✅ |
| Teachers (register, assignments, salary structure) | ✅ | ✅ |
| Student/parent portal (dashboard, profile, fees, results, attendance) | ✅ | ✅ |
| Teacher "My classes" | ✅ | ✅ |
| Timetable (bell periods, weekly grid, no double-booking, class teachers) | ✅ | ✅ |
| Diary / homework (optional submission, teacher checking) | ✅ | ✅ |
| Study materials (files or links) | ✅ | ✅ |
| Attendance (students + teachers, holidays, reports, CSV) | ✅ | ✅ |
| Exams & results (marks entry, publish, ranking, PDF) | ✅ | ✅ |
| Online tests (MCQ / true-false / short, timed attempts, grading, release) | ✅ | ✅ |
| Fees (collection, receipts, void, late fines, defaulters, summary) | ✅ | ✅ |
| Salary (monthly payroll, absence deduction, advances, payslips) | ✅ | ✅ |
| Announcements, school calendar/events, in-app notifications | ✅ | ✅ |
| Dashboards (CEO/headmaster, student, parent, teacher) | ✅ | ✅ |

## How the newer modules work

- **Timetable is how teachers get assigned.** Saving a lecture creates the matching teaching assignment; removing a teacher's last lecture for that class/section/subject removes it. The DB forbids double-booking a teacher (`uq_timetable_teacher_slot`).
- **Class teacher** (per class or section, Settings > Classes) sees the whole section, marks its attendance and writes general (no-subject) diary notes. Marks entry stays with the subject teacher.
- **Diary**: a teacher posts per section and subject; ticking "students must submit work" lets students upload a file/note until it is checked. Late submissions are flagged, not blocked.
- **Fees**: payments are recorded by staff (cash/bank/cheque/online), allocated oldest month first under row locks, with receipt numbers `RCPT-YYYYMM-NNNNN`. Mistakes are voided with a reason (never deleted). The late fine is added once per overdue month, lazily (on ledger read, payment, reports), not by a scheduler.
- **Salary**: net = gross − gross/days-in-month × absent days − advances. Generating a month again recalculates unpaid records; paying recalculates once more.
- **Online tests**: the server owns the timer (`expires_at`); MCQ/true-false and exact short answers are auto-marked; students see answers only after the teacher releases results.
- **Notifications** are in-app only (bell, 60 s polling). Sent for announcements, new diary entries, published results/tests, absences, fee receipts and salary payments.

## Roles

White-label: one school per deployment, no multi-tenancy. Branding (name, tagline, logo) is edited in Settings > School profile.

| Role | Reads | Writes |
|---|---|---|
| `admin` | everything | everything, incl. creating admin/CEO/headmaster accounts |
| `headmaster` | everything | settings, academic structure, timetable, holidays, attendance, exams/results, fees, payroll, announcements, events, teacher/student/parent logins (activate, reset password) |
| `ceo` | everything (published results, non-draft tests) | nothing |
| `teacher` | assigned classes/sections (+ class-teacher sections) | attendance, marks, diary, materials, online tests, class announcements for what they teach |
| `student` | own records, own section's timetable/diary/materials/tests | homework submissions, test attempts |
| `parent` | linked children | nothing |

## Open decisions

- **Guest test links** (`/test/[token]`): the tables support guests (name + roll no) but there is no guest flow; the link asks the student to sign in.

## Suggested later

Leave requests, student ID cards, term report card combining exams, transport, library, admission enquiries, SMS/email notifications, brand colours.

## Production

Deploy with `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` on a VPS (Caddy gives HTTPS for `DOMAIN`). Fees are billed from the admission month; leaving school (expelled/inactive) disables the student's login, and the parent's once no child is active.

## Debt

- Pre-existing ruff findings (mostly E501 in Phase 3 files); CI's `ruff check` fails until cleaned.
- The demo seed adds periods, a timetable and class teachers; diary/materials/tests/fees start empty.
