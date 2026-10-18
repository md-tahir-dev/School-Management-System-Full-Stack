from fastapi import APIRouter

from app.api.v1 import (
    academic,
    attendance,
    auth,
    content,
    dashboard,
    exams,
    fees,
    health,
    holidays,
    meta,
    notices,
    online_tests,
    parent,
    public,
    reports,
    results,
    salary,
    settings,
    students,
    teacher_attendance,
    teachers,
    timetable,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(public.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(settings.router)
api_router.include_router(academic.router)
api_router.include_router(students.router)
api_router.include_router(teachers.router)
api_router.include_router(parent.router)
api_router.include_router(meta.router)
# Phase 3: attendance, results
api_router.include_router(attendance.router)
api_router.include_router(teacher_attendance.router)
api_router.include_router(holidays.router)
api_router.include_router(reports.router)
api_router.include_router(exams.router)
api_router.include_router(results.router)
api_router.include_router(timetable.router)
api_router.include_router(content.router)
# Phase 4: fees and salary
api_router.include_router(fees.router)
api_router.include_router(salary.router)
# Phase 6: announcements, calendar, notifications
api_router.include_router(notices.router)
# Phase 5: online tests
api_router.include_router(online_tests.router)
api_router.include_router(dashboard.router)
# Phase 4: fees/payments/salary. Phase 5: tests, materials. Phase 6: announcements.
