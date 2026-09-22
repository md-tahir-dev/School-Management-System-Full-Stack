from fastapi import APIRouter

from app.api.v1 import academic, auth, health, meta, parent, public, settings, students, teachers, users

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
# Phase 3+: attendance, results. Phase 4: fees/payments/salary. Phase 5: tests, materials. Phase 6: announcements.
