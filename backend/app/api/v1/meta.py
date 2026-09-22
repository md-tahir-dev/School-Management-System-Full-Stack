from fastapi import APIRouter
from pydantic import BaseModel

from app.core.deps import CurrentUser
from app.models.enums import Designation, EmploymentType, Gender, Qualification, StudentStatus
from app.utils.validators import BLOOD_GROUPS

router = APIRouter(prefix="/meta", tags=["meta"])


class Options(BaseModel):
    designations: list[str]
    qualifications: list[str]
    employment_types: list[str]
    genders: list[str]
    blood_groups: list[str]
    student_statuses: list[str]


@router.get("/options", response_model=Options)
async def options(_: CurrentUser):
    """Allowed values for the dropdowns in the student and teacher forms."""
    return Options(
        designations=[d.value for d in Designation],
        qualifications=[q.value for q in Qualification],
        employment_types=[e.value for e in EmploymentType],
        genders=[g.value for g in Gender],
        blood_groups=list(BLOOD_GROUPS),
        student_statuses=[s.value for s in StudentStatus],
    )
