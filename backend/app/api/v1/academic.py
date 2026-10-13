"""Settings module routes: academic years, classes, sections, subjects, class-subjects, fee structures.

Read access: Manager/CEO for years and fees; every signed-in user for classes, sections and subjects
(dropdowns). Writes: Manager only."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.permissions import MANAGERS, SCHOOL_WIDE
from app.core.ratelimit import client_ip
from app.models import User
from app.schemas.academic import (
    AcademicYearIn,
    AcademicYearOut,
    ClassIn,
    ClassOut,
    ClassSubjectIn,
    ClassSubjectOut,
    FeeStructureIn,
    FeeStructureOut,
    SectionIn,
    SectionOut,
    SubjectIn,
    SubjectOut,
)
from app.schemas.common import Page, PageParams, page_params
from app.services import academic as svc

router = APIRouter(tags=["settings"])

Manager = Annotated[User, Depends(require_roles(*MANAGERS))]
SchoolWide = Depends(require_roles(*SCHOOL_WIDE))
Params = Annotated[PageParams, Depends(page_params)]


# ---------------------------------------------------------- academic years
@router.get("/academic-years", response_model=Page[AcademicYearOut], dependencies=[SchoolWide])
async def list_years(db: DbSession, params: Params):
    return await svc.list_years(db, params)


@router.post("/academic-years", response_model=AcademicYearOut, status_code=status.HTTP_201_CREATED)
async def create_year(body: AcademicYearIn, request: Request, db: DbSession, admin: Manager):
    return await svc.create_year(db, admin, body, client_ip(request))


@router.put("/academic-years/{year_id}", response_model=AcademicYearOut)
async def update_year(year_id: uuid.UUID, body: AcademicYearIn, request: Request, db: DbSession, admin: Manager):
    return await svc.update_year(db, admin, year_id, body, client_ip(request))


@router.post("/academic-years/{year_id}/set-current", response_model=AcademicYearOut)
async def set_current_year(year_id: uuid.UUID, request: Request, db: DbSession, admin: Manager):
    return await svc.set_current_year(db, admin, year_id, client_ip(request))


# ----------------------------------------------------------------- classes
@router.get("/classes", response_model=Page[ClassOut])
async def list_classes(_: CurrentUser, db: DbSession, params: Params):
    return await svc.list_classes(db, params)


@router.post("/classes", response_model=ClassOut, status_code=status.HTTP_201_CREATED)
async def create_class(body: ClassIn, request: Request, db: DbSession, admin: Manager):
    return await svc.create_class(db, admin, body, client_ip(request))


@router.put("/classes/{class_id}", response_model=ClassOut)
async def update_class(class_id: uuid.UUID, body: ClassIn, request: Request, db: DbSession, admin: Manager):
    return await svc.update_class(db, admin, class_id, body, client_ip(request))


@router.delete("/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_class(class_id: uuid.UUID, request: Request, db: DbSession, admin: Manager):
    await svc.delete_class(db, admin, class_id, client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- sections
@router.get("/classes/{class_id}/sections", response_model=Page[SectionOut])
async def list_sections(class_id: uuid.UUID, _: CurrentUser, db: DbSession, params: Params):
    return await svc.list_sections(db, class_id, params)


@router.post("/classes/{class_id}/sections", response_model=SectionOut, status_code=status.HTTP_201_CREATED)
async def create_section(class_id: uuid.UUID, body: SectionIn, request: Request, db: DbSession, admin: Manager):
    return await svc.create_section(db, admin, class_id, body, client_ip(request))


@router.put("/sections/{section_id}", response_model=SectionOut)
async def update_section(section_id: uuid.UUID, body: SectionIn, request: Request, db: DbSession, admin: Manager):
    return await svc.update_section(db, admin, section_id, body, client_ip(request))


@router.delete("/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_section(section_id: uuid.UUID, request: Request, db: DbSession, admin: Manager):
    await svc.delete_section(db, admin, section_id, client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- subjects
@router.get("/subjects", response_model=Page[SubjectOut])
async def list_subjects(_: CurrentUser, db: DbSession, params: Params):
    return await svc.list_subjects(db, params)


@router.post("/subjects", response_model=SubjectOut, status_code=status.HTTP_201_CREATED)
async def create_subject(body: SubjectIn, request: Request, db: DbSession, admin: Manager):
    return await svc.create_subject(db, admin, body, client_ip(request))


@router.put("/subjects/{subject_id}", response_model=SubjectOut)
async def update_subject(subject_id: uuid.UUID, body: SubjectIn, request: Request, db: DbSession, admin: Manager):
    return await svc.update_subject(db, admin, subject_id, body, client_ip(request))


@router.delete("/subjects/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject(subject_id: uuid.UUID, request: Request, db: DbSession, admin: Manager):
    await svc.delete_subject(db, admin, subject_id, client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------- class subjects
# These two resources are replaced as a whole, so they return a plain array, not a page.
@router.get("/classes/{class_id}/subjects", response_model=list[ClassSubjectOut])
async def get_class_subjects(class_id: uuid.UUID, _: CurrentUser, db: DbSession):
    return await svc.get_class_subjects(db, class_id)


@router.put("/classes/{class_id}/subjects", response_model=list[ClassSubjectOut])
async def replace_class_subjects(
    class_id: uuid.UUID, body: list[ClassSubjectIn], request: Request, db: DbSession, admin: Manager
):
    return await svc.replace_class_subjects(db, admin, class_id, body, client_ip(request))


# ---------------------------------------------------------- fee structures
@router.get("/fee-structures", response_model=list[FeeStructureOut], dependencies=[SchoolWide])
async def list_fee_structures(db: DbSession):
    return await svc.list_fee_structures(db)


@router.put("/fee-structures", response_model=list[FeeStructureOut])
async def replace_fee_structures(body: list[FeeStructureIn], request: Request, db: DbSession, admin: Manager):
    return await svc.replace_fee_structures(db, admin, body, client_ip(request))
