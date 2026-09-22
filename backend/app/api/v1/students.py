import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
from pydantic import AfterValidator, BaseModel

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.ratelimit import client_ip
from app.models import Role, User
from app.models.enums import StudentStatus
from app.schemas.common import Page, PageParams, page_params
from app.schemas.fields import Credential
from app.schemas.students import (
    DiscountResult,
    DiscountUpdate,
    GuardianOut,
    LedgerOut,
    StatusUpdate,
    StudentCreate,
    StudentCreated,
    StudentCredentials,
    StudentDetail,
    StudentListItem,
    StudentUpdate,
)
from app.services import students as svc
from app.services.storage import StorageBackend, get_storage
from app.utils.pagination import paginate  # noqa: F401
from app.utils.validators import validate_cnic

router = APIRouter(prefix="/students", tags=["students"])

Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]
Params = Annotated[PageParams, Depends(page_params)]


class GuardianLookup(BaseModel):
    found: bool
    guardian: GuardianOut | None = None
    children: list[str] = []


# Reading is open to every role; the service narrows what each role can see (teacher: assigned classes,
# student: self, parent: own children). Writes are Admin only, so the CEO is read-only.
@router.get("", response_model=Page[StudentListItem])
async def list_students(
    user: CurrentUser,
    db: DbSession,
    params: Params,
    class_id: uuid.UUID | None = Query(None),
    section_id: uuid.UUID | None = Query(None),
    status_: StudentStatus | None = Query(None, alias="status"),
    sort: Literal["name", "roll_no", "class"] = Query("name"),
):
    return await svc.list_students(
        db, user, params, class_id=class_id, section_id=section_id, status=status_, sort=sort
    )


@router.post("", response_model=StudentCreated, status_code=status.HTTP_201_CREATED)
async def register_student(body: StudentCreate, request: Request, db: DbSession, admin: Admin):
    """Transactional registration. `credentials` is present on this response only."""
    result = await svc.register_student(db, body, admin, ip=client_ip(request))
    return StudentCreated(
        student=await svc.build_detail(db, result.student),
        credentials=StudentCredentials(parent=result.parent_credential, student=result.student_credential),
        warnings=result.warnings,
    )


@router.get("/guardian-lookup", response_model=GuardianLookup)
async def guardian_lookup(
    db: DbSession,
    _: Admin,
    father_cnic: Annotated[str, AfterValidator(validate_cnic), Query()],
):
    """Lets the registration form say 'Existing guardian found; siblings will be linked' before submitting."""
    guardian = await svc.find_by_guardian_cnic(db, father_cnic)
    if guardian is None:
        return GuardianLookup(found=False)
    from sqlalchemy import select

    from app.models import Student, StudentGuardian

    names = (
        await db.scalars(
            select(Student.full_name)
            .join(StudentGuardian, StudentGuardian.student_id == Student.id)
            .where(StudentGuardian.guardian_id == guardian.id, Student.is_deleted.is_(False))
            .order_by(Student.full_name)
        )
    ).all()
    return GuardianLookup(found=True, guardian=GuardianOut.model_validate(guardian), children=list(names))


@router.get("/{student_id}", response_model=StudentDetail)
async def get_student(student_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return await svc.get_detail(db, user, student_id)


@router.put("/{student_id}", response_model=StudentDetail)
async def update_student(student_id: uuid.UUID, body: StudentUpdate, request: Request, db: DbSession, admin: Admin):
    student = await svc.update_student(db, admin, student_id, body, ip=client_ip(request))
    return await svc.build_detail(db, student)


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student(student_id: uuid.UUID, request: Request, db: DbSession, admin: Admin):
    await svc.soft_delete(db, admin, student_id, ip=client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{student_id}/photo", response_model=StudentDetail)
async def upload_photo(
    student_id: uuid.UUID,
    request: Request,
    db: DbSession,
    admin: Admin,
    storage: Annotated[StorageBackend, Depends(get_storage)],
    file: UploadFile = File(...),
):
    student = await svc.set_photo(db, admin, student_id, file, storage, ip=client_ip(request))
    return await svc.build_detail(db, student)


@router.put("/{student_id}/status", response_model=StudentDetail)
async def change_status(student_id: uuid.UUID, body: StatusUpdate, request: Request, db: DbSession, admin: Admin):
    student = await svc.set_status(db, admin, student_id, body, ip=client_ip(request))
    return await svc.build_detail(db, student)


@router.put("/{student_id}/discount", response_model=DiscountResult)
async def change_discount(student_id: uuid.UUID, body: DiscountUpdate, request: Request, db: DbSession, admin: Admin):
    """Recalculates UNPAID ledger rows only."""
    percent, changed = await svc.set_discount(db, admin, student_id, body.discount_percent, ip=client_ip(request))
    return DiscountResult(discount_percent=percent, recalculated_rows=changed)


@router.get("/{student_id}/ledger", response_model=LedgerOut)
async def student_ledger(
    student_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(require_roles(Role.ADMIN, Role.CEO, Role.STUDENT, Role.PARENT))],
):
    return await svc.get_ledger(db, user, student_id)


_ = Credential  # re-exported for OpenAPI consumers
