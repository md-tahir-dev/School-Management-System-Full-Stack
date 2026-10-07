import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.errors import not_found
from app.core.ratelimit import client_ip
from app.models import Role, User
from app.models.enums import Designation, EmploymentType
from app.schemas.attendance import TeacherAttendanceSummary
from app.schemas.common import Page, PageParams, page_params
from app.schemas.teachers import (
    AssignmentIn,
    SalaryIn,
    SalaryOut,
    TeacherCreate,
    TeacherCreated,
    TeacherCredentials,
    TeacherDetail,
    TeacherListItem,
    TeacherUpdate,
)
from app.services import teachers as svc
from app.services.storage import StorageBackend, get_storage

router = APIRouter(prefix="/teachers", tags=["teachers"])

Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]
AdminOrCeo = Annotated[User, Depends(require_roles(Role.ADMIN, Role.CEO))]
Params = Annotated[PageParams, Depends(page_params)]


@router.get("", response_model=Page[TeacherListItem])
async def list_teachers(
    _: AdminOrCeo,
    db: DbSession,
    params: Params,
    subject_id: uuid.UUID | None = Query(None),
    designation: Designation | None = Query(None),
    employment_type: EmploymentType | None = Query(None),
):
    return await svc.list_teachers(
        db, params, subject_id=subject_id, designation=designation, employment_type=employment_type
    )


@router.post("", response_model=TeacherCreated, status_code=status.HTTP_201_CREATED)
async def register_teacher(body: TeacherCreate, request: Request, db: DbSession, admin: Admin):
    """Transactional registration. `credentials` is present on this response only."""
    result = await svc.register_teacher(db, body, admin, ip=client_ip(request))
    return TeacherCreated(
        teacher=await svc.build_detail(db, result.teacher),
        credentials=TeacherCredentials(teacher=result.credential),
    )


@router.get("/me", response_model=TeacherDetail)
async def my_profile(db: DbSession, user: Annotated[User, Depends(require_roles(Role.TEACHER))]):
    teacher = await svc.current_teacher(db, user)
    if teacher is None:
        raise not_found("Teacher profile")
    return await svc.build_detail(db, teacher)


@router.get("/{teacher_id}", response_model=TeacherDetail)
async def get_teacher(
    teacher_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(require_roles(Role.ADMIN, Role.CEO, Role.TEACHER))],
):
    return await svc.build_detail(db, await svc.get_teacher_in_scope(db, user, teacher_id))


@router.put("/{teacher_id}", response_model=TeacherDetail)
async def update_teacher(teacher_id: uuid.UUID, body: TeacherUpdate, request: Request, db: DbSession, admin: Admin):
    teacher = await svc.update_teacher(db, admin, teacher_id, body, ip=client_ip(request))
    return await svc.build_detail(db, teacher)


@router.delete("/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_teacher(
    teacher_id: uuid.UUID,
    request: Request,
    db: DbSession,
    admin: Admin,
    force: bool = Query(False, description="Delete even if this is the only teacher for a class-subject"),
):
    await svc.soft_delete(db, admin, teacher_id, force=force, ip=client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{teacher_id}/photo", response_model=TeacherDetail)
async def upload_photo(
    teacher_id: uuid.UUID,
    request: Request,
    db: DbSession,
    admin: Admin,
    storage: Annotated[StorageBackend, Depends(get_storage)],
    file: UploadFile = File(...),
):
    teacher = await svc.set_photo(db, admin, teacher_id, file, storage, ip=client_ip(request))
    return await svc.build_detail(db, teacher)


@router.put("/{teacher_id}/assignments", response_model=TeacherDetail)
async def replace_assignments(
    teacher_id: uuid.UUID, body: list[AssignmentIn], request: Request, db: DbSession, admin: Admin
):
    teacher = await svc.replace_assignments(db, admin, teacher_id, body, ip=client_ip(request))
    return await svc.build_detail(db, teacher)


@router.put("/{teacher_id}/salary-structure", response_model=SalaryOut)
async def set_salary_structure(teacher_id: uuid.UUID, body: SalaryIn, request: Request, db: DbSession, admin: Admin):
    return await svc.set_salary_structure(db, admin, teacher_id, body, ip=client_ip(request))


@router.get("/{teacher_id}/attendance/summary", response_model=TeacherAttendanceSummary)
async def attendance_summary(
    teacher_id: uuid.UUID, user: CurrentUser, db: DbSession, month: str = Query(..., pattern=r"^\d{4}-\d{2}$")
):
    from app.services import teacher_attendance as ta_svc

    return await ta_svc.teacher_summary(db, user, teacher_id, month)
