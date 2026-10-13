import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.config import settings
from app.core.deps import DbSession, require_roles
from app.core.permissions import MANAGERS, SCHOOL_WIDE
from app.core.ratelimit import client_ip
from app.models import Role, User
from app.schemas.salary import AdvanceIn, AdvanceOut, GenerateIn, GenerateOut, PayIn, SalaryRecordOut
from app.services import pdf as pdf_svc
from app.services import salary as svc
from app.services.settings import get_school_settings

router = APIRouter(prefix="/salary", tags=["salary"])
Manager = Annotated[User, Depends(require_roles(*MANAGERS))]
Reader = Annotated[User, Depends(require_roles(*SCHOOL_WIDE))]
Payee = Annotated[User, Depends(require_roles(*SCHOOL_WIDE, Role.TEACHER))]


@router.post("/generate", response_model=GenerateOut)
async def generate(body: GenerateIn, request: Request, db: DbSession, actor: Manager):
    return await svc.generate_month(db, actor, body.month, client_ip(request))


@router.get("", response_model=list[SalaryRecordOut])
async def list_month(_: Reader, db: DbSession, month: date = Query(..., description="Any day in the month")):
    return await svc.list_month(db, month)


@router.get("/me", response_model=list[SalaryRecordOut])
async def my_salary(user: Annotated[User, Depends(require_roles(Role.TEACHER))], db: DbSession):
    return await svc.my_records(db, user)


@router.get("/advances", response_model=list[AdvanceOut])
async def list_advances(_: Reader, db: DbSession, month: date = Query(...)):
    return await svc.list_advances(db, month)


@router.post("/advances", response_model=AdvanceOut, status_code=status.HTTP_201_CREATED)
async def add_advance(body: AdvanceIn, request: Request, db: DbSession, actor: Manager):
    return await svc.add_advance(db, actor, body, client_ip(request))


@router.delete("/advances/{advance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_advance(advance_id: uuid.UUID, request: Request, db: DbSession, actor: Manager):
    await svc.delete_advance(db, actor, advance_id, client_ip(request))


@router.get("/{record_id}", response_model=SalaryRecordOut)
async def get_record(record_id: uuid.UUID, user: Payee, db: DbSession):
    return await svc.get_record(db, user, record_id)


@router.post("/{record_id}/pay", response_model=SalaryRecordOut)
async def mark_paid(record_id: uuid.UUID, body: PayIn, request: Request, db: DbSession, actor: Manager):
    return await svc.mark_paid(db, actor, record_id, body.paid_date, client_ip(request))


@router.get("/{record_id}/pdf")
async def payslip_pdf(record_id: uuid.UUID, user: Payee, db: DbSession):
    record = await svc.get_record(db, user, record_id)
    school = await get_school_settings(db)
    pdf = pdf_svc.render_payslip_pdf(record, school=school, upload_dir=settings.upload_dir)
    filename = f"payslip-{record.employee_id}-{record.month:%Y-%m}.pdf"
    return Response(
        content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )
