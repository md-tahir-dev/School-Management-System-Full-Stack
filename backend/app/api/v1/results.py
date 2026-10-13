import uuid

from fastapi import APIRouter, Response

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.permissions import MANAGERS
from app.models import Role
from app.schemas.results import ResultOut
from app.services import exams as svc
from app.services import pdf as pdf_svc
from app.services.settings import get_school_settings

router = APIRouter(prefix="/results", tags=["results"])


@router.get("/{result_id}", response_model=ResultOut)
async def get_result(result_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return await svc.get_result(db, user, result_id)


@router.get("/{result_id}/pdf")
async def result_pdf(result_id: uuid.UUID, user: CurrentUser, db: DbSession):
    result = await svc.get_result(db, user, result_id)
    if not result.is_published and user.role not in (*MANAGERS, Role.TEACHER):
        from app.core.errors import not_found

        raise not_found("Result")
    school = await get_school_settings(db)
    html = pdf_svc.render_result_card_html(
        result, school_name=school.name, slogan=school.slogan, address=school.address, phone=school.phone,
        logo_url=school.logo_url, photo_url=None, upload_dir=settings.upload_dir, show_rank=True,
    )
    pdf_bytes = pdf_svc.html_to_pdf(html)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{result.roll_no}-{result.exam_name}.pdf"'},
    )
