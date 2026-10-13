"""Online tests: teachers build and publish timed tests; students attempt them inside the open window.

The server owns the clock: an attempt's `expires_at` is min(start + time limit, test end), answers saved
after it are rejected, and an attempt found past its deadline is closed with whatever was saved.
Multiple-choice and true/false questions are marked on submit; short answers are marked by the teacher
(an exact, case-insensitive match with the answer key is marked automatically). The answer key never
leaves the server for students, and students see per-question results only once the teacher releases them.
Who manages a test follows the diary rule (managers anywhere; teachers for a subject they teach there)."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, delete, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import conflict, forbidden, invalid, not_found
from app.core.permissions import MANAGERS, SCHOOL_WIDE
from app.models import (
    Attempt,
    AttemptAnswer,
    OnlineTest,
    Question,
    Role,
    SchoolClass,
    Section,
    Student,
    Subject,
    User,
)
from app.models.enums import AttemptStatus, QuestionType, TestStatus
from app.schemas.common import Page, PageParams
from app.schemas.online_tests import (
    AnswerResult,
    AnswersIn,
    AttemptResult,
    AttemptRow,
    AttemptView,
    GradeIn,
    MyTestOut,
    QuestionOut,
    QuestionsIn,
    StudentQuestionOut,
    TestDetailOut,
    TestIn,
    TestOut,
)
from app.services.audit import log_action
from app.services.content import _assert_can_write, _audience_student, _read_clause
from app.services.dbutil import flush_or_conflict
from app.services.notify import family_user_ids, notify
from app.utils.money import money
from app.utils.pagination import paginate

GRACE = timedelta(seconds=30)  # network slack for the final autosave/submit
ZERO = Decimal(0)


def _now() -> datetime:
    return datetime.now(UTC)


# --- staff side ----------------------------------------------------------------------------------


def _tests_stmt():
    totals = (
        select(Question.test_id, func.count().label("n"), func.coalesce(func.sum(Question.marks), 0).label("marks"))
        .group_by(Question.test_id)
        .subquery()
    )
    return (
        select(
            OnlineTest,
            Subject.name,
            SchoolClass.name,
            Section.name,
            User.full_name,
            func.coalesce(totals.c.n, 0),
            func.coalesce(totals.c.marks, 0),
        )
        .join(Subject, Subject.id == OnlineTest.subject_id)
        .join(SchoolClass, SchoolClass.id == OnlineTest.class_id)
        .outerjoin(Section, Section.id == OnlineTest.section_id)
        .outerjoin(User, User.id == OnlineTest.created_by)
        .outerjoin(totals, totals.c.test_id == OnlineTest.id)
    )


def _test_fields(user: User, row) -> dict:
    t, subject, class_name, section, author, n, marks = row
    return dict(
        id=t.id,
        title=t.title,
        subject_id=t.subject_id,
        subject_name=subject,
        class_id=t.class_id,
        class_name=class_name,
        section_id=t.section_id,
        section_name=section,
        instructions=t.instructions,
        time_limit_min=t.time_limit_min,
        start_at=t.start_at,
        end_at=t.end_at,
        status=t.status,
        show_one_by_one=t.show_one_by_one,
        results_released=t.results_released,
        total_marks=money(marks),
        question_count=n,
        author_name=author,
        can_edit=user.role in MANAGERS or t.created_by == user.id,
    )


async def _readable_test(db: AsyncSession, user: User, test_id: uuid.UUID) -> OnlineTest:
    """Staff: tests in their scope (same rule as the diary). Out of scope is 404."""
    if user.role not in (*SCHOOL_WIDE, Role.TEACHER):
        raise forbidden()
    test = await db.scalar(
        select(OnlineTest).where(OnlineTest.id == test_id, await _read_clause(db, user, OnlineTest, None))
    )
    if test is None:
        raise not_found("Test")
    return test


async def _editable_test(db: AsyncSession, user: User, test_id: uuid.UUID) -> OnlineTest:
    test = await _readable_test(db, user, test_id)
    if user.role not in MANAGERS and test.created_by != user.id:
        raise forbidden("Only the author or a manager can change this test.")
    return test


async def list_tests(
    db: AsyncSession, user: User, params: PageParams, *, class_id: uuid.UUID | None, status: TestStatus | None
) -> Page:
    if user.role not in (*SCHOOL_WIDE, Role.TEACHER):
        raise forbidden()
    stmt = _tests_stmt().where(await _read_clause(db, user, OnlineTest, None))
    if user.role == Role.CEO:
        stmt = stmt.where(OnlineTest.status != TestStatus.DRAFT)
    if class_id:
        stmt = stmt.where(OnlineTest.class_id == class_id)
    if status:
        stmt = stmt.where(OnlineTest.status == status)
    stmt = stmt.order_by(OnlineTest.start_at.desc().nulls_last(), OnlineTest.created_at.desc())
    return await paginate(db, stmt, params, TestOut, row_mapper=lambda r: _test_fields(user, r))


async def get_test(db: AsyncSession, user: User, test_id: uuid.UUID) -> TestDetailOut:
    test = await _readable_test(db, user, test_id)
    row = (await db.execute(_tests_stmt().where(OnlineTest.id == test.id))).one()
    questions = await db.scalars(select(Question).where(Question.test_id == test.id).order_by(Question.sort_order))
    attempts = await db.scalar(select(func.count()).where(Attempt.test_id == test.id))
    return TestDetailOut(
        **_test_fields(user, row),
        questions=[QuestionOut.model_validate(q, from_attributes=True) for q in questions],
        attempt_count=attempts,
    )


async def create_test(db: AsyncSession, actor: User, body: TestIn, ip: str | None) -> TestDetailOut:
    await _assert_can_write(db, actor, body.class_id, body.section_id, body.subject_id)
    test = OnlineTest(
        **body.model_dump(), created_by=actor.id, status=TestStatus.DRAFT, share_token=secrets.token_urlsafe(24)
    )
    db.add(test)
    await db.flush()
    log_action(actor, "create", "online_test", test.id, {"title": test.title}, db=db, ip=ip)
    await db.commit()
    return await get_test(db, actor, test.id)


def _require_draft(test: OnlineTest) -> None:
    if test.status != TestStatus.DRAFT:
        raise conflict("Only a draft test can be changed.", code="not_draft")


async def update_test(db: AsyncSession, actor: User, test_id: uuid.UUID, body: TestIn, ip: str | None) -> TestDetailOut:
    test = await _editable_test(db, actor, test_id)
    _require_draft(test)
    await _assert_can_write(db, actor, body.class_id, body.section_id, body.subject_id)
    for k, v in body.model_dump().items():
        setattr(test, k, v)
    log_action(actor, "update", "online_test", test.id, {"title": test.title}, db=db, ip=ip)
    await db.commit()
    return await get_test(db, actor, test.id)


async def replace_questions(db: AsyncSession, actor: User, test_id: uuid.UUID, body: QuestionsIn) -> TestDetailOut:
    test = await _editable_test(db, actor, test_id)
    _require_draft(test)
    await db.execute(delete(Question).where(Question.test_id == test.id))
    db.add_all(Question(test_id=test.id, sort_order=i, **q.model_dump()) for i, q in enumerate(body.questions))
    await db.commit()
    return await get_test(db, actor, test.id)


async def delete_test(db: AsyncSession, actor: User, test_id: uuid.UUID, ip: str | None) -> None:
    test = await _editable_test(db, actor, test_id)
    if await db.scalar(select(func.count()).where(Attempt.test_id == test.id)):
        raise conflict("Students have attempted this test; close it instead.", code="has_attempts")
    await db.delete(test)
    log_action(actor, "delete", "online_test", test_id, {"title": test.title}, db=db, ip=ip)
    await db.commit()


async def publish_test(db: AsyncSession, actor: User, test_id: uuid.UUID, ip: str | None) -> TestDetailOut:
    test = await _editable_test(db, actor, test_id)
    _require_draft(test)
    if not await db.scalar(select(func.count()).where(Question.test_id == test.id)):
        raise invalid("Add at least one question before publishing.", {"questions": "Required"})
    if test.end_at is None or test.end_at <= _now():
        raise invalid("The test window has already ended; move the end time.", {"end_at": "In the past"})
    test.status = TestStatus.PUBLISHED
    section = Student.section_id == test.section_id if test.section_id else true()
    await notify(
        db,
        await family_user_ids(db, and_(Student.class_id == test.class_id, section), parents=False),
        f"New online test: {test.title} (opens {test.start_at:%d %b %H:%M} UTC)",
        "tests",
    )
    log_action(actor, "publish", "online_test", test.id, {"title": test.title}, db=db, ip=ip)
    await db.commit()
    return await get_test(db, actor, test.id)


async def close_test(db: AsyncSession, actor: User, test_id: uuid.UUID, ip: str | None) -> TestDetailOut:
    test = await _editable_test(db, actor, test_id)
    if test.status != TestStatus.PUBLISHED:
        raise conflict("Only a published test can be closed.", code="not_published")
    test.status = TestStatus.CLOSED
    for attempt in await db.scalars(
        select(Attempt).where(Attempt.test_id == test.id, Attempt.status == AttemptStatus.IN_PROGRESS)
    ):
        await _finish(db, attempt, AttemptStatus.EXPIRED)
    log_action(actor, "close", "online_test", test.id, {"title": test.title}, db=db, ip=ip)
    await db.commit()
    return await get_test(db, actor, test.id)


async def release_results(db: AsyncSession, actor: User, test_id: uuid.UUID, ip: str | None) -> TestDetailOut:
    test = await _editable_test(db, actor, test_id)
    if test.status == TestStatus.DRAFT:
        raise conflict("Publish the test first.", code="not_published")
    test.results_released = True
    section = Student.section_id == test.section_id if test.section_id else true()
    await notify(
        db,
        await family_user_ids(db, and_(Student.class_id == test.class_id, section)),
        f"Results released: {test.title}",
        "tests",
    )
    log_action(actor, "release", "online_test", test.id, {"title": test.title}, db=db, ip=ip)
    await db.commit()
    return await get_test(db, actor, test.id)


async def list_attempts(db: AsyncSession, actor: User, test_id: uuid.UUID) -> list[AttemptRow]:
    test = await _readable_test(db, actor, test_id)
    await _expire_overdue(db, test.id)
    ungraded = (
        select(AttemptAnswer.attempt_id, func.count().label("n"))
        .where(AttemptAnswer.is_graded.is_(False))
        .group_by(AttemptAnswer.attempt_id)
        .subquery()
    )
    rows = await db.execute(
        select(Attempt, Student.full_name, Student.roll_no, func.coalesce(ungraded.c.n, 0))
        .outerjoin(Student, Student.id == Attempt.student_id)
        .outerjoin(ungraded, ungraded.c.attempt_id == Attempt.id)
        .where(Attempt.test_id == test.id)
        .order_by(Student.roll_no)
    )
    return [
        AttemptRow(
            attempt_id=a.id,
            student_id=a.student_id,
            student_name=name or a.guest_name or "-",
            roll_no=roll or a.guest_roll_no,
            status=a.status,
            started_at=a.started_at,
            submitted_at=a.submitted_at,
            score=a.score,
            needs_grading=n if a.status != AttemptStatus.IN_PROGRESS else 0,
        )
        for a, name, roll, n in rows.all()
    ]


async def grade_attempt(db: AsyncSession, actor: User, attempt_id: uuid.UUID, body: GradeIn) -> AttemptResult:
    attempt = await db.scalar(select(Attempt).where(Attempt.id == attempt_id).with_for_update())
    if attempt is None:
        raise not_found("Attempt")
    await _editable_test(db, actor, attempt.test_id)
    if attempt.status == AttemptStatus.IN_PROGRESS:
        raise conflict("The student is still answering.", code="in_progress")
    questions = {q.id: q for q in await db.scalars(select(Question).where(Question.test_id == attempt.test_id))}
    answers = {
        a.question_id: a for a in await db.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id))
    }
    for qid, marks in body.marks.items():
        q = questions.get(qid)
        if q is None:
            raise invalid("Unknown question.", {str(qid): "Not in this test"})
        if not ZERO <= marks <= q.marks:
            raise invalid(f"Marks must be between 0 and {q.marks}.", {str(qid): f"0-{q.marks}"})
        ans = answers.get(qid)
        if ans is None:
            ans = AttemptAnswer(attempt_id=attempt.id, question_id=qid, answer=None)
            db.add(ans)
            answers[qid] = ans
        ans.marks_awarded, ans.is_graded = money(marks), True
    _rescore(attempt, answers.values(), len(questions))
    await db.commit()
    return await attempt_result(db, actor, attempt.id)


# --- student side --------------------------------------------------------------------------------


def _test_open(test: OnlineTest, now: datetime) -> bool:
    return test.status == TestStatus.PUBLISHED and test.start_at <= now <= test.end_at


async def my_tests(db: AsyncSession, user: User, student_id: uuid.UUID | None) -> list[MyTestOut]:
    student = await _audience_student(db, user, student_id)
    rows = (
        await db.execute(
            _tests_stmt()
            .where(
                OnlineTest.status != TestStatus.DRAFT,
                await _read_clause(db, user, OnlineTest, student),
            )
            .order_by(OnlineTest.start_at.desc())
        )
    ).all()
    attempts = {a.test_id: a for a in await db.scalars(select(Attempt).where(Attempt.student_id == student.id))}
    out = []
    for r in rows:
        a = attempts.get(r[0].id)
        out.append(
            MyTestOut(
                **_test_fields(user, r),
                attempt_id=a.id if a else None,
                attempt_status=a.status if a else None,
                score=a.score if a and r[0].results_released else None,
            )
        )
    return out


async def _student_attempt(db: AsyncSession, user: User, attempt_id: uuid.UUID, *, lock: bool = False) -> Attempt:
    student = await _audience_student(db, user, None)
    stmt = select(Attempt).where(Attempt.id == attempt_id, Attempt.student_id == student.id)
    attempt = await db.scalar(stmt.with_for_update() if lock else stmt)
    if attempt is None:
        raise not_found("Attempt")
    return attempt


async def start_attempt(db: AsyncSession, user: User, test_id: uuid.UUID) -> AttemptView:
    if user.role != Role.STUDENT:
        raise forbidden("Only students take tests.")
    student = await _audience_student(db, user, None)
    test = await db.scalar(
        select(OnlineTest).where(
            OnlineTest.id == test_id,
            OnlineTest.status != TestStatus.DRAFT,
            await _read_clause(db, user, OnlineTest, student),
        )
    )
    if test is None:
        raise not_found("Test")
    attempt = await db.scalar(select(Attempt).where(Attempt.test_id == test.id, Attempt.student_id == student.id))
    now = _now()
    if attempt is None:
        if not _test_open(test, now):
            raise conflict("This test isn't open right now.", code="not_open")
        attempt = Attempt(
            test_id=test.id,
            student_id=student.id,
            started_at=now,
            status=AttemptStatus.IN_PROGRESS,
            expires_at=min(now + timedelta(minutes=test.time_limit_min), test.end_at),
        )
        db.add(attempt)
        await flush_or_conflict(db, "You have already started this test.", code="already_started")
        await db.commit()
    return await _attempt_view(db, test, attempt)


async def _attempt_view(db: AsyncSession, test: OnlineTest, attempt: Attempt) -> AttemptView:
    if attempt.status == AttemptStatus.IN_PROGRESS and _now() > attempt.expires_at + GRACE:
        await _finish(db, attempt, AttemptStatus.EXPIRED)
        await db.commit()
    questions = await db.scalars(select(Question).where(Question.test_id == test.id).order_by(Question.sort_order))
    saved = await db.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id))
    return AttemptView(
        attempt_id=attempt.id,
        test_id=test.id,
        title=test.title,
        instructions=test.instructions,
        show_one_by_one=test.show_one_by_one,
        status=attempt.status,
        expires_at=attempt.expires_at,
        server_now=_now(),
        questions=[StudentQuestionOut.model_validate(q, from_attributes=True) for q in questions],
        answers={a.question_id: a.answer for a in saved},
    )


async def get_attempt(db: AsyncSession, user: User, attempt_id: uuid.UUID) -> AttemptView:
    attempt = await _student_attempt(db, user, attempt_id)
    return await _attempt_view(db, await db.get(OnlineTest, attempt.test_id), attempt)


async def _apply_answers(db: AsyncSession, attempt: Attempt, body: AnswersIn) -> None:
    valid = set(await db.scalars(select(Question.id).where(Question.test_id == attempt.test_id)))
    existing = {
        a.question_id: a for a in await db.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id))
    }
    for item in body.answers:
        if item.question_id not in valid:
            raise invalid("Unknown question.", {str(item.question_id): "Not in this test"})
        if item.question_id in existing:
            existing[item.question_id].answer = item.answer
        else:
            db.add(AttemptAnswer(attempt_id=attempt.id, question_id=item.question_id, answer=item.answer))
    await db.flush()


async def save_answers(db: AsyncSession, user: User, attempt_id: uuid.UUID, body: AnswersIn) -> AttemptView:
    attempt = await _student_attempt(db, user, attempt_id, lock=True)
    test = await db.get(OnlineTest, attempt.test_id)
    if attempt.status != AttemptStatus.IN_PROGRESS:
        raise conflict("This attempt is already submitted.", code="submitted")
    if _now() > attempt.expires_at + GRACE:
        await _finish(db, attempt, AttemptStatus.EXPIRED)
        await db.commit()
        raise conflict("Time is up; your saved answers were submitted.", code="time_up")
    await _apply_answers(db, attempt, body)
    await db.commit()
    return await _attempt_view(db, test, attempt)


async def submit_attempt(db: AsyncSession, user: User, attempt_id: uuid.UUID, body: AnswersIn | None) -> AttemptResult:
    """Final answers (if still in time) + close. Submitting twice just returns the result."""
    attempt = await _student_attempt(db, user, attempt_id, lock=True)
    if attempt.status == AttemptStatus.IN_PROGRESS:
        in_time = _now() <= attempt.expires_at + GRACE
        if in_time and body and body.answers:
            await _apply_answers(db, attempt, body)
        await _finish(db, attempt, AttemptStatus.SUBMITTED if in_time else AttemptStatus.EXPIRED)
        await db.commit()
    return await attempt_result(db, user, attempt.id)


async def _finish(db: AsyncSession, attempt: Attempt, status: AttemptStatus) -> None:
    """Close the attempt and auto-mark what can be marked. The caller commits."""
    questions = list(await db.scalars(select(Question).where(Question.test_id == attempt.test_id)))
    answers = {
        a.question_id: a for a in await db.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id))
    }
    for q in questions:
        ans = answers.get(q.id)
        if ans is None:
            ans = AttemptAnswer(attempt_id=attempt.id, question_id=q.id, answer=None)
            db.add(ans)
            answers[q.id] = ans
        given = (ans.answer or "").strip()
        if q.type in (QuestionType.MCQ, QuestionType.TRUE_FALSE):
            ans.marks_awarded, ans.is_graded = (q.marks if given == (q.correct_answer or "") else ZERO), True
        elif not given:
            ans.marks_awarded, ans.is_graded = ZERO, True
        elif q.correct_answer and given.casefold() == q.correct_answer.strip().casefold():
            ans.marks_awarded, ans.is_graded = q.marks, True
    attempt.submitted_at = min(_now(), attempt.expires_at + GRACE)
    attempt.status = status
    _rescore(attempt, answers.values(), len(questions))


def _rescore(attempt: Attempt, answers, question_count: int) -> None:
    answers = list(answers)
    attempt.score = money(sum((a.marks_awarded or ZERO for a in answers), ZERO))
    fully_marked = len(answers) >= question_count and all(a.is_graded for a in answers)
    if fully_marked and attempt.status == AttemptStatus.SUBMITTED:  # an expired attempt keeps that label
        attempt.status = AttemptStatus.GRADED


async def _expire_overdue(db: AsyncSession, test_id: uuid.UUID) -> None:
    overdue = await db.scalars(
        select(Attempt)
        .where(
            Attempt.test_id == test_id,
            Attempt.status == AttemptStatus.IN_PROGRESS,
            Attempt.expires_at < _now() - GRACE,
        )
        .with_for_update(skip_locked=True)
    )
    changed = False
    for attempt in overdue:
        await _finish(db, attempt, AttemptStatus.EXPIRED)
        changed = True
    if changed:
        await db.commit()


async def attempt_result(db: AsyncSession, user: User, attempt_id: uuid.UUID) -> AttemptResult:
    """Students see their own (answers only once released); parents their child's; staff in scope."""
    attempt = await db.get(Attempt, attempt_id)
    if attempt is None:
        raise not_found("Attempt")
    test = await db.get(OnlineTest, attempt.test_id)
    if user.role in (*SCHOOL_WIDE, Role.TEACHER):
        await _readable_test(db, user, test.id)
        show = True
    else:
        mine = await _audience_student(db, user, attempt.student_id if user.role == Role.PARENT else None)
        if attempt.student_id != mine.id:
            raise not_found("Attempt")
        show = test.results_released
    student = await db.get(Student, attempt.student_id) if attempt.student_id else None
    questions = list(
        await db.scalars(select(Question).where(Question.test_id == test.id).order_by(Question.sort_order))
    )
    answers = {
        a.question_id: a for a in await db.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id))
    }
    return AttemptResult(
        attempt_id=attempt.id,
        test_id=test.id,
        title=test.title,
        student_name=student.full_name if student else (attempt.guest_name or "-"),
        roll_no=student.roll_no if student else attempt.guest_roll_no,
        status=attempt.status,
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        score=attempt.score if show else None,
        total_marks=money(sum((q.marks for q in questions), ZERO)),
        released=test.results_released,
        answers=[
            AnswerResult(
                question_id=q.id,
                text=q.text,
                type=q.type,
                options=q.options,
                answer=answers[q.id].answer if q.id in answers else None,
                correct_answer=q.correct_answer,
                marks=q.marks,
                marks_awarded=answers[q.id].marks_awarded if q.id in answers else None,
                is_graded=answers[q.id].is_graded if q.id in answers else False,
            )
            for q in questions
        ]
        if show
        else [],
    )


async def upcoming_tests(db: AsyncSession, student: Student) -> list[dict]:
    """Dashboard card: published tests for the student's class/section that haven't ended."""
    rows = await db.execute(
        select(OnlineTest, Subject.name)
        .join(Subject, Subject.id == OnlineTest.subject_id)
        .where(
            OnlineTest.status == TestStatus.PUBLISHED,
            OnlineTest.end_at >= _now(),
            OnlineTest.class_id == student.class_id,
            or_(OnlineTest.section_id.is_(None), OnlineTest.section_id == student.section_id),
        )
        .order_by(OnlineTest.start_at)
        .limit(5)
    )
    return [
        {
            "id": str(t.id),
            "title": t.title,
            "subject": subject,
            "start_at": t.start_at.isoformat(),
            "end_at": t.end_at.isoformat(),
        }
        for t, subject in rows.all()
    ]
