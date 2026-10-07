"""Read-only parent views. Every call re-checks the student_guardians link (via the shared scoping rule)."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FeeLedger, SchoolClass, Section, Student, User
from app.schemas.common import Page, PageParams
from app.schemas.parent import ChildDashboard, ChildSummary, FeeMonthSummary
from app.services.dashboard import attendance_card, latest_result_card
from app.services.scoping import get_student_in_scope, student_scope_clause
from app.utils.pagination import paginate


def _summary_dict(row) -> dict:
    student, class_name, section_name = row
    return {
        "id": student.id,
        "full_name": student.full_name,
        "roll_no": student.roll_no,
        "class_name": class_name,
        "section_name": section_name,
        "photo_url": student.photo_url,
    }


async def list_children(db: AsyncSession, user: User, params: PageParams) -> Page:
    stmt = (
        select(Student, SchoolClass.name, Section.name)
        .join(SchoolClass, SchoolClass.id == Student.class_id)
        .outerjoin(Section, Section.id == Student.section_id)
        .where(Student.is_deleted.is_(False), await student_scope_clause(db, user))
        .order_by(Student.dob, Student.full_name, Student.id)  # eldest first
    )
    return await paginate(db, stmt, params, ChildSummary, row_mapper=_summary_dict)


async def child_dashboard(
    db: AsyncSession, user: User, student_id: uuid.UUID, *, today: date | None = None
) -> ChildDashboard:
    student = await get_student_in_scope(db, user, student_id)
    klass = await db.get(SchoolClass, student.class_id)
    section = await db.get(Section, student.section_id) if student.section_id else None
    month_start = (today or date.today()).replace(day=1)
    fee = await db.scalar(select(FeeLedger).where(FeeLedger.student_id == student.id, FeeLedger.month == month_start))
    result_card = await latest_result_card(db, student.id)
    att_card = await attendance_card(db, student)
    return ChildDashboard(
        child=ChildSummary(
            id=student.id,
            full_name=student.full_name,
            roll_no=student.roll_no,
            class_name=klass.name if klass else "",
            section_name=section.name if section else None,
            photo_url=student.photo_url,
        ),
        status=student.status,
        fee_current_month=FeeMonthSummary(
            month=fee.month,
            status=fee.status,
            total_payable=fee.total_payable,
            paid_amount=fee.paid_amount,
            due_date=fee.due_date,
        )
        if fee
        else None,
        latest_result=result_card,
        attendance_percentage=att_card["month_percentage"] if att_card else None,
        attendance=att_card,
    )
