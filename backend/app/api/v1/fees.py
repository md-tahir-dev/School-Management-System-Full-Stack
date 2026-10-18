import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.config import settings
from app.core.deps import DbSession, require_roles
from app.core.permissions import MANAGERS, SCHOOL_WIDE
from app.core.ratelimit import client_ip
from app.models import Role, User
from app.schemas.common import Page, PageParams, page_params
from app.schemas.fees import DefaulterOut, FeeSummaryOut, PaymentIn, PaymentOut, VoidIn
from app.services import payments as svc
from app.services import pdf as pdf_svc
from app.services.settings import get_school_settings

router = APIRouter(prefix="/fees", tags=["fees"])
Manager = Annotated[User, Depends(require_roles(*MANAGERS))]
Reader = Annotated[User, Depends(require_roles(*SCHOOL_WIDE))]
Family = Annotated[User, Depends(require_roles(*SCHOOL_WIDE, Role.STUDENT, Role.PARENT))]  # no teachers
Params = Annotated[PageParams, Depends(page_params)]


@router.post("/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def collect_payment(body: PaymentIn, request: Request, db: DbSession, actor: Manager):
    return await svc.collect_payment(db, actor, body, client_ip(request))


@router.get("/payments", response_model=Page[PaymentOut])
async def list_payments(
    user: Family,
    db: DbSession,
    params: Params,
    student_id: uuid.UUID | None = Query(None),
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
):
    """School-wide roles see every payment; students and parents see their own (teachers: none)."""
    return await svc.list_payments(db, user, params, student_id=student_id, date_from=date_from, date_to=date_to)


@router.get("/payments/{payment_id}", response_model=PaymentOut)
async def get_payment(payment_id: uuid.UUID, user: Family, db: DbSession):
    return await svc.get_payment(db, user, payment_id)


@router.get("/payments/{payment_id}/pdf")
async def receipt_pdf(payment_id: uuid.UUID, user: Family, db: DbSession):
    payment = await svc.get_payment(db, user, payment_id)
    school = await get_school_settings(db)
    pdf = pdf_svc.render_receipt_pdf(payment, school=school, upload_dir=settings.upload_dir)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{payment.receipt_no}.pdf"'},
    )


@router.post("/payments/{payment_id}/void", response_model=PaymentOut)
async def void_payment(payment_id: uuid.UUID, body: VoidIn, request: Request, db: DbSession, actor: Manager):
    return await svc.void_payment(db, actor, payment_id, body.reason, client_ip(request))


@router.get("/defaulters", response_model=Page[DefaulterOut])
async def defaulters(_: Reader, db: DbSession, params: Params, class_id: uuid.UUID | None = Query(None)):
    return await svc.defaulters(db, params, class_id=class_id)


@router.get("/summary", response_model=FeeSummaryOut)
async def fee_summary(_: Reader, db: DbSession, month: date = Query(..., description="Any day in the month")):
    return await svc.fee_summary(db, month)
