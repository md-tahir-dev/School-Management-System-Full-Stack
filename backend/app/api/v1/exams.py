import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import PlainTextResponse, Response

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.permissions import MANAGERS
from app.core.ratelimit import client_ip
from app.models import Role, User
from app.models.enums import ExamType, ResultStatus
from app.schemas.common import Page, PageParams, page_params
from app.schemas.results import (
    ClassResultRow,
    ExamAnalyticsOut,
    ExamIn,
    ExamOut,
    ExamSubjectIn,
    ExamSubjectOut,
    MarksBulkSaveIn,
    MarksSheetOut,
    StudentEntryOut,
    StudentEntrySaveIn,
    UnpublishIn,
)
from app.services import exams as svc
from app.services import pdf as pdf_svc
from app.services.settings import get_school_settings

router = APIRouter(prefix="/exams", tags=["exams"])
Manager = Annotated[User, Depends(require_roles(*MANAGERS))]
Staff = Annotated[User, Depends(require_roles(*MANAGERS, Role.TEACHER))]
Params = Annotated[PageParams, Depends(page_params)]


@router.get("", response_model=Page[ExamOut])
async def list_exams(
    user: CurrentUser,
    db: DbSession,
    params: Params,
    class_id: uuid.UUID | None = Query(None),
    academic_year_id: uuid.UUID | None = Query(None),
    type: ExamType | None = Query(None),
    published: bool | None = Query(None),
):
    if user.role not in (*MANAGERS, Role.TEACHER):
        published = True  # CEO, students and parents never see drafts
    return await svc.list_exams(db, params, class_id=class_id, academic_year_id=academic_year_id, type_=type, published=published)


@router.post("", response_model=ExamOut, status_code=status.HTTP_201_CREATED)
async def create_exam(body: ExamIn, request: Request, db: DbSession, admin: Manager):
    return await svc.create_exam(db, admin, body, ip=client_ip(request))


@router.get("/{exam_id}", response_model=ExamOut)
async def get_exam(exam_id: uuid.UUID, _: CurrentUser, db: DbSession):
    return await svc.get_exam(db, exam_id)


@router.put("/{exam_id}", response_model=ExamOut)
async def update_exam(exam_id: uuid.UUID, body: ExamIn, request: Request, db: DbSession, admin: Manager):
    return await svc.update_exam(db, admin, exam_id, body, ip=client_ip(request))


@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam(exam_id: uuid.UUID, request: Request, db: DbSession, admin: Manager):
    await svc.delete_exam(db, admin, exam_id, ip=client_ip(request))


@router.get("/{exam_id}/subjects", response_model=list[ExamSubjectOut])
async def get_exam_subjects(exam_id: uuid.UUID, _: CurrentUser, db: DbSession):
    return await svc.get_exam_subjects(db, exam_id)


@router.put("/{exam_id}/subjects", response_model=list[ExamSubjectOut])
async def replace_exam_subjects(
    exam_id: uuid.UUID, body: list[ExamSubjectIn], request: Request, db: DbSession, admin: Manager
):
    return await svc.replace_exam_subjects(db, admin, exam_id, body, ip=client_ip(request))


@router.post("/{exam_id}/subjects/reset", response_model=list[ExamSubjectOut])
async def reset_exam_subjects(exam_id: uuid.UUID, request: Request, db: DbSession, admin: Manager):
    return await svc.reset_exam_subjects_from_class(db, admin, exam_id, ip=client_ip(request))


@router.post("/{exam_id}/publish", response_model=ExamOut)
async def publish_exam(exam_id: uuid.UUID, request: Request, db: DbSession, admin: Manager):
    return await svc.publish_exam(db, admin, exam_id, ip=client_ip(request))


@router.post("/{exam_id}/unpublish", response_model=ExamOut)
async def unpublish_exam(exam_id: uuid.UUID, body: UnpublishIn, request: Request, db: DbSession, admin: Manager):
    return await svc.unpublish_exam(db, admin, exam_id, body.reason, ip=client_ip(request))


@router.get("/{exam_id}/marks-sheet", response_model=MarksSheetOut)
async def marks_sheet(exam_id: uuid.UUID, staff: Staff, db: DbSession, subject_id: uuid.UUID = Query(...), section_id: uuid.UUID | None = Query(None)):
    return await svc.get_marks_sheet(db, staff, exam_id, section_id, subject_id)


@router.put("/{exam_id}/marks", response_model=MarksSheetOut)
async def save_marks(
    exam_id: uuid.UUID, body: MarksBulkSaveIn, request: Request, db: DbSession, staff: Staff,
    subject_id: uuid.UUID = Query(...), section_id: uuid.UUID | None = Query(None),
):
    return await svc.save_marks_bulk(db, staff, exam_id, subject_id, section_id, body, ip=client_ip(request))


@router.get("/{exam_id}/students/{student_id}/entry", response_model=StudentEntryOut)
async def student_entry(exam_id: uuid.UUID, student_id: uuid.UUID, staff: Staff, db: DbSession):
    return await svc.get_student_entry(db, staff, exam_id, student_id)


@router.put("/{exam_id}/students/{student_id}/entry", response_model=StudentEntryOut)
async def save_student_entry(exam_id: uuid.UUID, student_id: uuid.UUID, body: StudentEntrySaveIn, request: Request, db: DbSession, staff: Staff):
    return await svc.save_student_entry(db, staff, exam_id, student_id, body, ip=client_ip(request))


@router.get("/{exam_id}/results", response_model=Page[ClassResultRow])
async def class_results(
    exam_id: uuid.UUID, user: CurrentUser, db: DbSession, params: Params,
    section_id: uuid.UUID | None = Query(None), status_: ResultStatus | None = Query(None, alias="status"),
):
    return await svc.class_results(db, user, exam_id, params, section_id, status_)


@router.get("/{exam_id}/results/export")
async def export_results(exam_id: uuid.UUID, user: CurrentUser, db: DbSession, section_id: uuid.UUID | None = Query(None), format: str = Query("csv")):
    page = await svc.class_results(db, user, exam_id, PageParams(page=1, page_size=10000, q=None), section_id, None)
    return PlainTextResponse(svc.class_results_csv(page.items), media_type="text/csv")


@router.get("/{exam_id}/results/pdf")
async def bulk_result_pdf(
    exam_id: uuid.UUID, admin: Manager, db: DbSession, section_id: uuid.UUID | None = Query(None)
):
    from sqlalchemy import select as _select

    from app.models import Result

    exam = await svc.get_exam(db, exam_id)
    school = await get_school_settings(db)
    page = await svc.class_results(db, admin, exam_id, PageParams(page=1, page_size=10000, q=None), section_id, None)
    pdfs = []
    for row in page.items:
        result = await db.scalar(_select(Result).where(Result.exam_id == exam_id, Result.student_id == row.student_id))
        if result is None:
            continue
        full = await svc.get_result(db, admin, result.id)
        html = pdf_svc.render_result_card_html(
            full, school_name=school.name, slogan=school.slogan, address=school.address, phone=school.phone,
            logo_url=school.logo_url, photo_url=None, upload_dir=settings.upload_dir, show_rank=True,
        )
        pdfs.append(pdf_svc.html_to_pdf(html))
    merged = pdf_svc.merge_pdfs(pdfs) if pdfs else b""
    return Response(content=merged, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{exam.name}-results.pdf"'})


@router.get("/{exam_id}/analytics", response_model=ExamAnalyticsOut)
async def analytics(exam_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return await svc.exam_analytics(db, user, exam_id)


@router.get("/{exam_id}/marks-progress")
async def marks_progress(exam_id: uuid.UUID, staff: Staff, db: DbSession):
    return await svc.marks_progress(db, exam_id)
