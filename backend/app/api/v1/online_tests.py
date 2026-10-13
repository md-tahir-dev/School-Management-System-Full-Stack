import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, Request, status

from app.core.deps import DbSession, require_roles
from app.core.permissions import MANAGERS, SCHOOL_WIDE
from app.core.ratelimit import client_ip
from app.models import Role, User
from app.models.enums import TestStatus
from app.schemas.common import Page, PageParams, page_params
from app.schemas.online_tests import (
    AnswersIn,
    AttemptResult,
    AttemptRow,
    AttemptView,
    GradeIn,
    MyTestOut,
    QuestionsIn,
    TestDetailOut,
    TestIn,
    TestOut,
)
from app.services import online_tests as svc

router = APIRouter(prefix="/tests", tags=["online tests"])
Writer = Annotated[User, Depends(require_roles(*MANAGERS, Role.TEACHER))]
Staff = Annotated[User, Depends(require_roles(*SCHOOL_WIDE, Role.TEACHER))]
StudentUser = Annotated[User, Depends(require_roles(Role.STUDENT))]
Family = Annotated[User, Depends(require_roles(Role.STUDENT, Role.PARENT))]
Anyone = Annotated[User, Depends(require_roles(*SCHOOL_WIDE, Role.TEACHER, Role.STUDENT, Role.PARENT))]


@router.get("", response_model=Page[TestOut])
async def list_tests(
    user: Staff,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    class_id: uuid.UUID | None = Query(None),
    status_: TestStatus | None = Query(None, alias="status"),
):
    return await svc.list_tests(db, user, params, class_id=class_id, status=status_)


@router.get("/me", response_model=list[MyTestOut])
async def my_tests(user: Family, db: DbSession, student_id: uuid.UUID | None = Query(None)):
    return await svc.my_tests(db, user, student_id)


@router.post("", response_model=TestDetailOut, status_code=status.HTTP_201_CREATED)
async def create_test(body: TestIn, request: Request, db: DbSession, actor: Writer):
    return await svc.create_test(db, actor, body, client_ip(request))


@router.get("/attempts/{attempt_id}", response_model=AttemptView)
async def get_attempt(attempt_id: uuid.UUID, user: StudentUser, db: DbSession):
    return await svc.get_attempt(db, user, attempt_id)


@router.put("/attempts/{attempt_id}/answers", response_model=AttemptView)
async def save_answers(attempt_id: uuid.UUID, body: AnswersIn, user: StudentUser, db: DbSession):
    return await svc.save_answers(db, user, attempt_id, body)


@router.post("/attempts/{attempt_id}/submit", response_model=AttemptResult)
async def submit(attempt_id: uuid.UUID, user: StudentUser, db: DbSession, body: AnswersIn | None = Body(None)):
    return await svc.submit_attempt(db, user, attempt_id, body)


@router.get("/attempts/{attempt_id}/result", response_model=AttemptResult)
async def attempt_result(attempt_id: uuid.UUID, user: Anyone, db: DbSession):
    return await svc.attempt_result(db, user, attempt_id)


@router.put("/attempts/{attempt_id}/grade", response_model=AttemptResult)
async def grade(attempt_id: uuid.UUID, body: GradeIn, db: DbSession, actor: Writer):
    return await svc.grade_attempt(db, actor, attempt_id, body)


@router.get("/{test_id}", response_model=TestDetailOut)
async def get_test(test_id: uuid.UUID, user: Staff, db: DbSession):
    return await svc.get_test(db, user, test_id)


@router.put("/{test_id}", response_model=TestDetailOut)
async def update_test(test_id: uuid.UUID, body: TestIn, request: Request, db: DbSession, actor: Writer):
    return await svc.update_test(db, actor, test_id, body, client_ip(request))


@router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_test(test_id: uuid.UUID, request: Request, db: DbSession, actor: Writer):
    await svc.delete_test(db, actor, test_id, client_ip(request))


@router.put("/{test_id}/questions", response_model=TestDetailOut)
async def replace_questions(test_id: uuid.UUID, body: QuestionsIn, db: DbSession, actor: Writer):
    return await svc.replace_questions(db, actor, test_id, body)


@router.post("/{test_id}/publish", response_model=TestDetailOut)
async def publish(test_id: uuid.UUID, request: Request, db: DbSession, actor: Writer):
    return await svc.publish_test(db, actor, test_id, client_ip(request))


@router.post("/{test_id}/close", response_model=TestDetailOut)
async def close(test_id: uuid.UUID, request: Request, db: DbSession, actor: Writer):
    return await svc.close_test(db, actor, test_id, client_ip(request))


@router.post("/{test_id}/release", response_model=TestDetailOut)
async def release(test_id: uuid.UUID, request: Request, db: DbSession, actor: Writer):
    return await svc.release_results(db, actor, test_id, client_ip(request))


@router.post("/{test_id}/start", response_model=AttemptView)
async def start(test_id: uuid.UUID, user: StudentUser, db: DbSession):
    return await svc.start_attempt(db, user, test_id)


@router.get("/{test_id}/attempts", response_model=list[AttemptRow])
async def list_attempts(test_id: uuid.UUID, user: Staff, db: DbSession):
    return await svc.list_attempts(db, user, test_id)
