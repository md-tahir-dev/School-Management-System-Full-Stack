"""Exams and results: exam CRUD, the publish workflow, marks entry (grid and per-student), ranking,
class/student result reading, analytics, and CSV export.

Every conflict path below goes through `app.services.dbutil.flush_or_conflict`, the same helper
`academic.py` uses for its duplicate-name checks - see that module's docstring for why this matters:
an earlier attempt at this exact file had a hand-rolled version of this pattern that left the session's
connection in a bad state after a duplicate-name error (a `MissingGreenlet` on the *next* query in the
same session). Reusing one audited helper instead of re-deriving the rollback dance is the fix.
"""

import csv
import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, delete, func, select, text, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, forbidden, invalid, not_found
from app.core.permissions import MANAGERS, SCHOOL_WIDE
from app.models import (
    AcademicYear,
    ClassSubject,
    Exam,
    ExamSubject,
    Guardian,
    Notification,
    Result,
    ResultItem,
    Role,
    SchoolClass,
    Section,
    Student,
    StudentGuardian,
    Subject,
    User,
)
from app.models.enums import ResultStatus, StudentStatus
from app.schemas.common import Page, PageParams
from app.schemas.results import (
    ClassResultRow,
    ExamAnalyticsOut,
    ExamIn,
    ExamOut,
    ExamSubjectIn,
    ExamSubjectOut,
    LeaderboardRow,
    MarkEntryRow,
    MarksBulkSaveIn,
    MarksSheetOut,
    ResultOut,
    ResultSubjectRow,
    StudentEntryOut,
    StudentEntrySaveIn,
    StudentEntrySubject,
    StudentResultsOut,
    SubjectAnalytics,
    TrendPoint,
)
from app.services.audit import log_action
from app.services.dbutil import flush_or_conflict
from app.services.grading import SubjectMark, grade_for, is_overall_pass, percentage, round2, subject_status
from app.services.scoping import (
    get_student_in_scope,
    student_scope_clause,
    teacher_assigned_to_section,
    teacher_assigned_to_subject,
    teacher_id_for,
)
from app.services.settings import get_school_settings
from app.utils.money import money
from app.utils.pagination import like_pattern, paginate


# ------------------------------------------------------------------------- exams
async def _class_or_404(db: AsyncSession, class_id: uuid.UUID) -> SchoolClass:
    klass = await db.get(SchoolClass, class_id)
    if klass is None:
        raise not_found("Class")
    return klass


async def _exam_or_404(db: AsyncSession, exam_id: uuid.UUID) -> Exam:
    exam = await db.get(Exam, exam_id)
    if exam is None:
        raise not_found("Exam")
    return exam


async def _exam_out(db: AsyncSession, exam: Exam) -> ExamOut:
    klass = await db.get(SchoolClass, exam.class_id)
    return ExamOut(
        id=exam.id,
        name=exam.name,
        type=exam.type,
        academic_year_id=exam.academic_year_id,
        class_id=exam.class_id,
        class_name=klass.name if klass else "",
        start_date=exam.start_date,
        end_date=exam.end_date,
        is_published=exam.is_published,
        published_at=exam.published_at,
        created_at=exam.created_at,
    )


async def latest_grade_for_student(db: AsyncSession, student_id: uuid.UUID) -> str | None:
    """Most recent COMPLETE result's grade, for the student profile header card."""
    result = await db.scalar(
        select(Result)
        .join(Exam, Exam.id == Result.exam_id)
        .where(Result.student_id == student_id, Result.status == ResultStatus.COMPLETE)
        .order_by(Exam.created_at.desc())
        .limit(1)
    )
    return result.grade if result else None


async def get_exam(db: AsyncSession, exam_id: uuid.UUID) -> ExamOut:
    return await _exam_out(db, await _exam_or_404(db, exam_id))


async def list_exams(
    db: AsyncSession,
    params: PageParams,
    *,
    class_id: uuid.UUID | None,
    academic_year_id: uuid.UUID | None,
    type_: str | None,
    published: bool | None,
) -> Page:
    stmt = select(Exam, SchoolClass.name).join(SchoolClass, SchoolClass.id == Exam.class_id).order_by(Exam.created_at.desc())
    if params.q:
        stmt = stmt.where(Exam.name.ilike(like_pattern(params.q)))
    if class_id:
        stmt = stmt.where(Exam.class_id == class_id)
    if academic_year_id:
        stmt = stmt.where(Exam.academic_year_id == academic_year_id)
    if type_:
        stmt = stmt.where(Exam.type == type_)
    if published is not None:
        stmt = stmt.where(Exam.is_published.is_(published))

    def _row(row) -> dict:
        exam, class_name = row
        return {
            "id": exam.id,
            "name": exam.name,
            "type": exam.type,
            "academic_year_id": exam.academic_year_id,
            "class_id": exam.class_id,
            "class_name": class_name,
            "start_date": exam.start_date,
            "end_date": exam.end_date,
            "is_published": exam.is_published,
            "published_at": exam.published_at,
            "created_at": exam.created_at,
        }

    return await paginate(db, stmt, params, ExamOut, row_mapper=_row)


async def create_exam(db: AsyncSession, actor: User, body: ExamIn, ip: str | None) -> ExamOut:
    await _class_or_404(db, body.class_id)
    if await db.get(AcademicYear, body.academic_year_id) is None:
        raise invalid("Academic year not found.", {"academic_year_id": "Academic year not found"})

    exam = Exam(
        name=body.name,
        type=body.type,
        academic_year_id=body.academic_year_id,
        class_id=body.class_id,
        start_date=body.start_date,
        end_date=body.end_date,
    )
    db.add(exam)
    await flush_or_conflict(
        db, f"An exam named {body.name} already exists for this class and year.", code="EXAM_EXISTS", field="name"
    )

    # Copy the class's current subjects in as the exam's starting subject list (Part C1).
    class_subjects = (
        await db.scalars(select(ClassSubject).where(ClassSubject.class_id == body.class_id))
    ).all()
    for cs in class_subjects:
        db.add(
            ExamSubject(
                exam_id=exam.id, subject_id=cs.subject_id, total_marks=cs.total_marks, passing_marks=cs.passing_marks
            )
        )
    log_action(actor, "create", "exam", exam.id, {"name": body.name, "class_id": str(body.class_id)}, db=db, ip=ip)
    await db.commit()
    return await _exam_out(db, exam)


async def update_exam(db: AsyncSession, actor: User, exam_id: uuid.UUID, body: ExamIn, ip: str | None) -> ExamOut:
    exam = await _exam_or_404(db, exam_id)
    if exam.is_published:
        raise AppError(409, "EXAM_PUBLISHED", "Unpublish the exam before editing it.")
    await _class_or_404(db, body.class_id)
    diff = {}
    for field in ("name", "type", "academic_year_id", "class_id", "start_date", "end_date"):
        new = getattr(body, field)
        old = getattr(exam, field)
        if old != new:
            diff[field] = {"old": str(old), "new": str(new)}
            setattr(exam, field, new)
    await flush_or_conflict(
        db, f"An exam named {body.name} already exists for this class and year.", code="EXAM_EXISTS", field="name"
    )
    if diff:
        log_action(actor, "update", "exam", exam.id, diff, db=db, ip=ip)
    await db.commit()
    return await _exam_out(db, exam)


async def delete_exam(db: AsyncSession, actor: User, exam_id: uuid.UUID, ip: str | None) -> None:
    exam = await _exam_or_404(db, exam_id)
    has_results = await db.scalar(select(func.count()).select_from(Result).where(Result.exam_id == exam_id))
    if has_results:
        raise AppError(
            409,
            "EXAM_HAS_RESULTS",
            f"{exam.name} has {has_results} result(s) recorded. Unpublish it instead of deleting it, "
            "or remove the results first.",
            details={"result_count": has_results},
        )
    name = exam.name
    await db.execute(delete(ExamSubject).where(ExamSubject.exam_id == exam_id))
    await db.delete(exam)
    log_action(actor, "delete", "exam", exam_id, {"name": name}, db=db, ip=ip)
    await db.commit()


async def get_exam_subjects(db: AsyncSession, exam_id: uuid.UUID) -> list[ExamSubjectOut]:
    await _exam_or_404(db, exam_id)
    rows = await db.execute(
        select(ExamSubject, Subject.name).join(Subject, Subject.id == ExamSubject.subject_id).where(ExamSubject.exam_id == exam_id).order_by(Subject.name)
    )
    return [
        ExamSubjectOut(subject_id=es.subject_id, subject_name=name, total_marks=money(es.total_marks), passing_marks=money(es.passing_marks))
        for es, name in rows.all()
    ]


async def replace_exam_subjects(
    db: AsyncSession, actor: User, exam_id: uuid.UUID, items: list[ExamSubjectIn], ip: str | None
) -> list[ExamSubjectOut]:
    exam = await _exam_or_404(db, exam_id)
    if exam.is_published:
        raise AppError(409, "EXAM_PUBLISHED", "Subjects can't be changed after the exam is published.")
    ids = [i.subject_id for i in items]
    if len(set(ids)) != len(ids):
        raise invalid("The same subject is listed twice.", {"items": "Duplicate subjects"})
    known = set((await db.scalars(select(Subject.id).where(Subject.id.in_(ids)))).all()) if ids else set()
    if missing := set(ids) - known:
        raise invalid("Unknown subject.", {"items": f"{len(missing)} subject(s) do not exist"})

    await db.execute(delete(ExamSubject).where(ExamSubject.exam_id == exam_id))
    for item in items:
        db.add(ExamSubject(exam_id=exam_id, subject_id=item.subject_id, total_marks=item.total_marks, passing_marks=item.passing_marks))
    log_action(actor, "update", "exam_subjects", exam_id, {"count": len(items)}, db=db, ip=ip)
    await db.commit()
    return await get_exam_subjects(db, exam_id)


async def reset_exam_subjects_from_class(db: AsyncSession, actor: User, exam_id: uuid.UUID, ip: str | None) -> list[ExamSubjectOut]:
    exam = await _exam_or_404(db, exam_id)
    class_subjects = (await db.scalars(select(ClassSubject).where(ClassSubject.class_id == exam.class_id))).all()
    items = [ExamSubjectIn(subject_id=cs.subject_id, total_marks=cs.total_marks, passing_marks=cs.passing_marks) for cs in class_subjects]
    return await replace_exam_subjects(db, actor, exam_id, items, ip)


# ---------------------------------------------------------------------- roster
async def _class_roster(
    db: AsyncSession, class_id: uuid.UUID, *, section_id: uuid.UUID | None = None, scope: ColumnElement[bool] = true()
) -> list[Student]:
    stmt = select(Student).where(
        Student.class_id == class_id, Student.is_deleted.is_(False), Student.status == StudentStatus.ACTIVE, scope
    )
    if section_id:
        stmt = stmt.where(Student.section_id == section_id)
    return list((await db.scalars(stmt.order_by(Student.roll_no))).all())


async def _assert_teacher_subject_scope(db: AsyncSession, actor: User, exam: Exam, section_id: uuid.UUID | None, subject_id: uuid.UUID) -> None:
    if actor.role != Role.TEACHER:
        return
    teacher_id = await teacher_id_for(db, actor)
    if teacher_id is None or not await teacher_assigned_to_subject(db, teacher_id, exam.class_id, section_id, subject_id):
        raise not_found("Class section")  # out of scope is 404, never 403


async def _assert_teacher_class_scope(db: AsyncSession, actor: User, exam: Exam, section_id: uuid.UUID | None) -> None:
    """Result reads: a teacher must teach (any subject in) the exam's class, and the section if one is given."""
    if actor.role != Role.TEACHER:
        return
    teacher_id = await teacher_id_for(db, actor)
    if teacher_id is None or not await teacher_assigned_to_section(db, teacher_id, exam.class_id, section_id):
        raise not_found("Exam")


# ------------------------------------------------------------------- ranking
_RANK_SQL = text(
    """
    UPDATE results r
    SET rank = sub.new_rank
    FROM (
        SELECT id, RANK() OVER (ORDER BY percentage DESC) AS new_rank
        FROM results
        WHERE exam_id = :exam_id AND status = 'complete'
    ) sub
    WHERE r.id = sub.id
    """
)
_CLEAR_RANK_SQL = text("UPDATE results SET rank = NULL WHERE exam_id = :exam_id AND status != 'complete'")


async def recompute_ranks(db: AsyncSession, exam_id: uuid.UUID) -> None:
    """Ties share the same rank (SQL RANK(), not DENSE_RANK): [95, 90, 90, 80] -> [1, 2, 2, 4].
    Only 'complete' results are ranked; draft results always have a null rank."""
    await db.execute(_RANK_SQL, {"exam_id": exam_id})
    await db.execute(_CLEAR_RANK_SQL, {"exam_id": exam_id})


# -------------------------------------------------------------- save one result row
async def _recompute_result(db: AsyncSession, exam: Exam, student_id: uuid.UUID) -> Result:
    """Rebuilds one student's `results` row from their current `result_items`, against the exam's full
    subject list (so a result is only 'complete' once every exam_subjects row has a matching item)."""
    school = await get_school_settings(db)
    exam_subject_ids = set((await db.scalars(select(ExamSubject.subject_id).where(ExamSubject.exam_id == exam.id))).all())
    result = await db.scalar(select(Result).where(Result.exam_id == exam.id, Result.student_id == student_id))
    if result is None:
        result = Result(
            student_id=student_id, exam_id=exam.id, total_obtained=0, total_possible=0, percentage=0, grade="F", is_pass=False
        )
        db.add(result)
        await db.flush()

    items = (await db.scalars(select(ResultItem).where(ResultItem.result_id == result.id))).all()
    entered_ids = {i.subject_id for i in items}
    marks = [SubjectMark(i.subject_id, i.total_marks, i.passing_marks, i.obtained_marks, i.is_absent) for i in items]

    if exam_subject_ids and exam_subject_ids.issubset(entered_ids):
        pct = percentage(marks)
        result.total_obtained = round2(sum((m.obtained_marks for m in marks), Decimal(0)))
        result.total_possible = round2(sum((m.total_marks for m in marks), Decimal(0)))
        result.percentage = pct
        result.grade = grade_for(pct)
        result.is_pass = is_overall_pass(marks, pct, fail_if_any_subject_failed=school.fail_if_any_subject_failed)
        result.status = ResultStatus.COMPLETE
    else:
        result.status = ResultStatus.DRAFT
        result.rank = None
    return result


async def _marks_sheet_row(db: AsyncSession, exam: Exam, subject_id: uuid.UUID, student: Student) -> MarkEntryRow:
    item = await db.scalar(
        select(ResultItem)
        .join(Result, Result.id == ResultItem.result_id)
        .where(Result.exam_id == exam.id, Result.student_id == student.id, ResultItem.subject_id == subject_id)
    )
    return MarkEntryRow(
        student_id=student.id,
        roll_no=student.roll_no,
        full_name=student.full_name,
        total_marks=0,
        passing_marks=0,
        obtained_marks=item.obtained_marks if item else None,
        is_absent=item.is_absent if item else False,
    )


async def get_marks_sheet(db: AsyncSession, actor: User, exam_id: uuid.UUID, section_id: uuid.UUID | None, subject_id: uuid.UUID) -> MarksSheetOut:
    exam = await _exam_or_404(db, exam_id)
    exam_subject = await db.scalar(select(ExamSubject).where(ExamSubject.exam_id == exam_id, ExamSubject.subject_id == subject_id))
    if exam_subject is None:
        raise not_found("This subject is not part of this exam")
    await _assert_teacher_subject_scope(db, actor, exam, section_id, subject_id)
    subject = await db.get(Subject, subject_id)
    # a teacher only sees students whose section they teach this subject in (matters when section_id is omitted)
    scope = await student_scope_clause(db, actor, subject_id=subject_id)
    roster = await _class_roster(db, exam.class_id, section_id=section_id, scope=scope)
    rows = []
    for s in roster:
        row = await _marks_sheet_row(db, exam, subject_id, s)
        row.total_marks = money(exam_subject.total_marks)
        row.passing_marks = money(exam_subject.passing_marks)
        rows.append(row)
    is_locked = exam.is_published and actor.role == Role.TEACHER
    return MarksSheetOut(exam_id=exam_id, subject_id=subject_id, subject_name=subject.name if subject else "", section_id=section_id, is_locked=is_locked, rows=rows)


async def save_marks_bulk(db: AsyncSession, actor: User, exam_id: uuid.UUID, subject_id: uuid.UUID, section_id: uuid.UUID | None, body: MarksBulkSaveIn, ip: str | None) -> MarksSheetOut:
    exam = await _exam_or_404(db, exam_id)
    exam_subject = await db.scalar(select(ExamSubject).where(ExamSubject.exam_id == exam_id, ExamSubject.subject_id == subject_id))
    if exam_subject is None:
        raise not_found("This subject is not part of this exam")

    if exam.is_published:
        if actor.role == Role.TEACHER:
            raise forbidden("This exam is published; marks can no longer be edited.")
        if actor.role in MANAGERS and not body.reason:
            raise invalid("A reason is required to edit marks after publishing.", {"reason": "Reason is required"})
    await _assert_teacher_subject_scope(db, actor, exam, section_id, subject_id)

    # Per-student scope, not just per-request: without a section_id the request-level check above only
    # proves the teacher teaches this subject in *some* section of the class.
    scope = await student_scope_clause(db, actor, subject_id=subject_id)
    roster_ids = {s.id for s in await _class_roster(db, exam.class_id, section_id=section_id, scope=scope)}
    changed_students: set[uuid.UUID] = set()
    for entry in body.entries:
        if entry.student_id not in roster_ids:
            if actor.role == Role.TEACHER:
                raise not_found("Student")
            raise invalid("Some students are not on this class/section's roster.", {"entries": "Unknown student"})
        if entry.obtained_marks > exam_subject.total_marks:
            raise invalid(
                f"Obtained marks can't exceed the total ({exam_subject.total_marks}).",
                {"entries": f"{entry.student_id}: obtained marks exceed total"},
            )
        result = await _recompute_result(db, exam, entry.student_id)  # ensures a Result row exists
        item = await db.scalar(select(ResultItem).where(ResultItem.result_id == result.id, ResultItem.subject_id == subject_id))
        obtained = Decimal(0) if entry.is_absent else entry.obtained_marks
        old_values = None
        if item is None:
            item = ResultItem(
                result_id=result.id, subject_id=subject_id, total_marks=exam_subject.total_marks,
                passing_marks=exam_subject.passing_marks, obtained_marks=obtained, is_absent=entry.is_absent,
                is_pass=(not entry.is_absent) and obtained >= exam_subject.passing_marks,
            )
            db.add(item)
        else:
            if exam.is_published and actor.role in MANAGERS:
                old_values = {"obtained_marks": str(item.obtained_marks), "is_absent": item.is_absent}
            item.total_marks = exam_subject.total_marks  # re-snapshot at this save
            item.passing_marks = exam_subject.passing_marks
            item.obtained_marks = obtained
            item.is_absent = entry.is_absent
            item.is_pass = (not entry.is_absent) and obtained >= exam_subject.passing_marks
        await db.flush()
        if old_values and (old_values["obtained_marks"] != str(obtained) or old_values["is_absent"] != entry.is_absent):
            log_action(
                actor, "update", "result_item", item.id,
                {"reason": body.reason, "old": old_values, "new": {"obtained_marks": str(obtained), "is_absent": entry.is_absent}},
                db=db, ip=ip,
            )
        changed_students.add(entry.student_id)

    for student_id in changed_students:
        await _recompute_result(db, exam, student_id)
    await db.flush()
    await recompute_ranks(db, exam_id)
    if not (exam.is_published and actor.role in MANAGERS):
        log_action(
            actor, "bulk_save", "marks", subject_id,
            {"exam_id": str(exam_id), "subject_id": str(subject_id), "section_id": str(section_id), "count": len(body.entries)},
            db=db, ip=ip,
        )
    await db.commit()
    return await get_marks_sheet(db, actor, exam_id, section_id, subject_id)


async def get_student_entry(db: AsyncSession, actor: User, exam_id: uuid.UUID, student_id: uuid.UUID) -> StudentEntryOut:
    exam = await _exam_or_404(db, exam_id)
    student = await get_student_in_scope(db, actor, student_id) if actor.role in (Role.TEACHER,) else await _student_or_404(db, student_id)
    exam_subjects = (
        await db.execute(select(ExamSubject, Subject.name).join(Subject, Subject.id == ExamSubject.subject_id).where(ExamSubject.exam_id == exam_id).order_by(Subject.name))
    ).all()
    result = await db.scalar(select(Result).where(Result.exam_id == exam_id, Result.student_id == student_id))
    items = {i.subject_id: i for i in (await db.scalars(select(ResultItem).where(ResultItem.result_id == result.id))).all()} if result else {}

    subjects = []
    for es, name in exam_subjects:
        item = items.get(es.subject_id)
        mark = SubjectMark(es.subject_id, es.total_marks, es.passing_marks, item.obtained_marks if item else Decimal(0), item.is_absent if item else False)
        subjects.append(
            StudentEntrySubject(
                subject_id=es.subject_id, subject_name=name, total_marks=money(es.total_marks), passing_marks=money(es.passing_marks),
                obtained_marks=item.obtained_marks if item else None, is_absent=item.is_absent if item else False,
                status=subject_status(mark) if item else None,
            )
        )
    return StudentEntryOut(
        exam_id=exam_id, student_id=student_id, full_name=student.full_name, roll_no=student.roll_no, subjects=subjects,
        total_obtained=result.total_obtained if result else Decimal(0),
        total_possible=result.total_possible if result else Decimal(0),
        percentage=result.percentage if result else Decimal(0),
        grade=result.grade if result and result.status == ResultStatus.COMPLETE else None,
        is_complete=bool(result and result.status == ResultStatus.COMPLETE),
    )


async def _student_or_404(db: AsyncSession, student_id: uuid.UUID) -> Student:
    student = await db.get(Student, student_id)
    if student is None or student.is_deleted:
        raise not_found("Student")
    return student


async def save_student_entry(db: AsyncSession, actor: User, exam_id: uuid.UUID, student_id: uuid.UUID, body: StudentEntrySaveIn, ip: str | None) -> StudentEntryOut:
    exam = await _exam_or_404(db, exam_id)
    for entry in body.subjects:
        exam_subject = await db.scalar(select(ExamSubject).where(ExamSubject.exam_id == exam_id, ExamSubject.subject_id == entry.subject_id))
        if exam_subject is None:
            raise not_found("This subject is not part of this exam")
        one = MarksBulkSaveIn(entries=[entry], reason=body.reason)
        await save_marks_bulk(db, actor, exam_id, entry.subject_id, None, one, ip)
    return await get_student_entry(db, actor, exam_id, student_id)


# --------------------------------------------------------------- publish workflow
async def publish_exam(db: AsyncSession, actor: User, exam_id: uuid.UUID, ip: str | None) -> ExamOut:
    exam = await _exam_or_404(db, exam_id)
    if exam.is_published:
        raise AppError(409, "ALREADY_PUBLISHED", "This exam is already published.")
    await recompute_ranks(db, exam_id)
    exam.is_published = True
    exam.published_at = datetime.now(UTC)
    exam.published_by = actor.id
    log_action(actor, "publish", "exam", exam.id, {"name": exam.name}, db=db, ip=ip)

    results = (await db.scalars(select(Result).where(Result.exam_id == exam_id))).all()
    for result in results:
        student = await db.get(Student, result.student_id)
        if student is None:
            continue
        recipients = []
        if student.user_id:
            recipients.append(student.user_id)
        guardian_users = await db.scalars(
            select(Guardian.user_id).join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
            .where(StudentGuardian.student_id == student.id, Guardian.user_id.is_not(None))
        )
        recipients.extend(guardian_users.all())
        message = f"{exam.name} result for {student.full_name} has been published."
        for user_id in recipients:
            already = await db.scalar(select(Notification.id).where(Notification.user_id == user_id, Notification.message == message))
            if already is None:
                db.add(Notification(user_id=user_id, message=message))
    await db.commit()
    return await _exam_out(db, exam)


async def unpublish_exam(db: AsyncSession, actor: User, exam_id: uuid.UUID, reason: str, ip: str | None) -> ExamOut:
    exam = await _exam_or_404(db, exam_id)
    if not exam.is_published:
        raise AppError(409, "NOT_PUBLISHED", "This exam isn't published.")
    exam.is_published = False
    exam.published_at = None
    exam.published_by = None
    log_action(actor, "unpublish", "exam", exam.id, {"name": exam.name, "reason": reason}, db=db, ip=ip)
    await db.commit()
    return await _exam_out(db, exam)


# ------------------------------------------------------------------------ reading
async def class_results(db: AsyncSession, actor: User, exam_id: uuid.UUID, params: PageParams, section_id: uuid.UUID | None, status_: str | None) -> Page:
    exam = await _exam_or_404(db, exam_id)
    if actor.role not in (*SCHOOL_WIDE, Role.TEACHER):
        raise forbidden()
    if not exam.is_published and actor.role == Role.CEO:
        raise not_found("Exam")
    await _assert_teacher_class_scope(db, actor, exam, section_id)

    stmt = (
        select(Result, Student.roll_no, Student.full_name, Section.name)
        .join(Student, Student.id == Result.student_id)
        .outerjoin(Section, Section.id == Student.section_id)
        .where(Result.exam_id == exam_id, await student_scope_clause(db, actor))
        .order_by(Result.rank.is_(None), Result.rank, Student.roll_no)
    )
    if section_id:
        stmt = stmt.where(Student.section_id == section_id)
    if status_:
        stmt = stmt.where(Result.status == status_)
    if params.q:
        stmt = stmt.where(Student.full_name.ilike(like_pattern(params.q)))

    def _row(row) -> dict:
        result, roll_no, full_name, section_name = row
        return {
            "result_id": result.id, "exam_id": exam.id, "exam_name": exam.name,
            "student_id": result.student_id, "roll_no": roll_no, "full_name": full_name, "section_name": section_name,
            "total_obtained": result.total_obtained, "total_possible": result.total_possible, "percentage": result.percentage,
            "grade": result.grade, "rank": result.rank, "is_pass": result.is_pass, "status": result.status,
        }

    return await paginate(db, stmt, params, ClassResultRow, row_mapper=_row)


async def _result_out(db: AsyncSession, result: Result, exam: Exam, student: Student) -> ResultOut:
    klass = await db.get(SchoolClass, student.class_id)
    section = await db.get(Section, student.section_id) if student.section_id else None
    year = await db.get(AcademicYear, exam.academic_year_id)
    father_name = await db.scalar(
        select(Guardian.father_name).join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id).where(StudentGuardian.student_id == student.id).limit(1)
    )
    items = (
        await db.execute(select(ResultItem, Subject.name).join(Subject, Subject.id == ResultItem.subject_id).where(ResultItem.result_id == result.id).order_by(Subject.name))
    ).all()
    total_ranked = await db.scalar(select(func.count()).select_from(Result).where(Result.exam_id == exam.id, Result.status == ResultStatus.COMPLETE))
    return ResultOut(
        id=result.id, exam_id=exam.id, exam_name=exam.name, exam_type=exam.type,
        academic_year_label=year.label if year else "", student_id=student.id, student_name=student.full_name,
        roll_no=student.roll_no, class_name=klass.name if klass else "", section_name=section.name if section else None,
        father_name=father_name,
        subjects=[
            ResultSubjectRow(
                subject_id=item.subject_id, subject_name=name, total_marks=money(item.total_marks), passing_marks=money(item.passing_marks),
                obtained_marks=money(item.obtained_marks), is_absent=item.is_absent,
                status=subject_status(SubjectMark(item.subject_id, item.total_marks, item.passing_marks, item.obtained_marks, item.is_absent)),
            )
            for item, name in items
        ],
        total_obtained=money(result.total_obtained), total_possible=money(result.total_possible), percentage=money(result.percentage),
        grade=result.grade, rank=result.rank, total_ranked=total_ranked if result.rank else None, is_pass=result.is_pass,
        status=result.status, remarks=result.remarks, is_published=exam.is_published,
    )


async def get_result(db: AsyncSession, actor: User, result_id: uuid.UUID) -> ResultOut:
    result = await db.get(Result, result_id)
    if result is None:
        raise not_found("Result")
    exam = await _exam_or_404(db, result.exam_id)
    if not exam.is_published and actor.role not in (*MANAGERS, Role.TEACHER):
        raise not_found("Result")
    student = await get_student_in_scope(db, actor, result.student_id)
    return await _result_out(db, result, exam, student)


async def student_results(db: AsyncSession, actor: User, student_id: uuid.UUID) -> StudentResultsOut:
    student = await get_student_in_scope(db, actor, student_id)
    stmt = (
        select(Result, Exam)
        .join(Exam, Exam.id == Result.exam_id)
        .where(Result.student_id == student.id, Result.status == ResultStatus.COMPLETE)
        .order_by(Exam.created_at)
    )
    if actor.role not in (*MANAGERS, Role.TEACHER):
        stmt = stmt.where(Exam.is_published.is_(True))
    rows = (await db.execute(stmt)).all()
    results = [
        ClassResultRow(
            result_id=r.id, exam_id=e.id, exam_name=e.name,
            student_id=student.id, roll_no=student.roll_no, full_name=student.full_name,
            section_name=None, total_obtained=money(r.total_obtained), total_possible=money(r.total_possible),
            percentage=money(r.percentage), grade=r.grade, rank=r.rank, is_pass=r.is_pass, status=r.status,
        )
        for r, e in rows
    ]
    trend = [TrendPoint(exam_id=e.id, exam_name=e.name, percentage=money(r.percentage), grade=r.grade) for r, e in rows]
    return StudentResultsOut(results=results, trend=trend)


# ------------------------------------------------------------------------ analytics
async def exam_analytics(db: AsyncSession, actor: User, exam_id: uuid.UUID) -> ExamAnalyticsOut:
    exam = await _exam_or_404(db, exam_id)
    if actor.role not in (*SCHOOL_WIDE, Role.TEACHER):
        raise forbidden()
    if not exam.is_published and actor.role == Role.CEO:
        raise not_found("Exam")  # same rule as class_results: CEO sees published exams only
    await _assert_teacher_class_scope(db, actor, exam, None)
    scope = await student_scope_clause(db, actor)  # true() for school-wide readers

    def scoped_results():
        return select(Result).join(Student, Student.id == Result.student_id).where(Result.exam_id == exam_id, scope)

    complete = (await db.scalars(scoped_results().where(Result.status == ResultStatus.COMPLETE))).all()
    roster_size = len(await _class_roster(db, exam.class_id, scope=scope))
    entered = await db.scalar(scoped_results().with_only_columns(func.count(func.distinct(Result.student_id))))

    if complete:
        percentages = [r.percentage for r in complete]
        class_average = round2(sum(percentages) / len(percentages))
        highest, lowest = max(percentages), min(percentages)
        pass_count = sum(1 for r in complete if r.is_pass)
        pass_percent = round2(Decimal(pass_count) / len(complete) * 100)
    else:
        class_average = highest = lowest = pass_percent = Decimal("0.00")

    grade_dist: dict[str, int] = {}
    for r in complete:
        grade_dist[r.grade] = grade_dist.get(r.grade, 0) + 1

    subject_rows = (
        await db.execute(
            select(ExamSubject.subject_id, Subject.name).join(Subject, Subject.id == ExamSubject.subject_id).where(ExamSubject.exam_id == exam_id)
        )
    ).all()
    subjects = []
    for subject_id, name in subject_rows:
        items = (
            await db.scalars(
                select(ResultItem)
                .join(Result, Result.id == ResultItem.result_id)
                .join(Student, Student.id == Result.student_id)
                .where(Result.exam_id == exam_id, ResultItem.subject_id == subject_id, scope)
            )
        ).all()
        if items:
            pcts = [round2(i.obtained_marks / i.total_marks * 100) if i.total_marks else Decimal(0) for i in items]
            avg = round2(sum(pcts) / len(pcts))
            passed = sum(1 for i in items if i.is_pass)
            rate = round2(Decimal(passed) / len(items) * 100)
        else:
            avg = rate = Decimal("0.00")
        subjects.append(SubjectAnalytics(subject_id=subject_id, subject_name=name, average_percentage=avg, pass_rate=rate))

    top = sorted(complete, key=lambda r: r.percentage, reverse=True)[:5]
    top_rows = []
    for r in top:
        student = await db.get(Student, r.student_id)
        top_rows.append(LeaderboardRow(student_id=r.student_id, full_name=student.full_name if student else "", roll_no=student.roll_no if student else "", percentage=money(r.percentage), rank=r.rank))

    return ExamAnalyticsOut(
        exam_id=exam_id, class_average=money(class_average), highest=money(highest), lowest=money(lowest),
        pass_percent=money(pass_percent), grade_distribution=grade_dist, subjects=subjects, top_students=top_rows,
        not_entered_count=max(roster_size - (entered or 0), 0), complete_count=len(complete), total_students=roster_size,
    )


def class_results_csv(rows: list[ClassResultRow]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Rank", "Roll No", "Name", "Total Obtained", "Total Possible", "Percentage", "Grade", "Status"])
    for r in rows:
        writer.writerow([r.rank or "", r.roll_no, r.full_name, str(r.total_obtained), str(r.total_possible), str(r.percentage), r.grade, r.status.value])
    return buf.getvalue()


async def marks_progress(db: AsyncSession, exam_id: uuid.UUID) -> list[dict]:
    """Per subject, per section: how many roster students have a recorded mark. Drives the admin
    'Marks Progress' tab so it's obvious who hasn't finished entering."""
    exam = await _exam_or_404(db, exam_id)
    subjects = (await db.execute(select(ExamSubject.subject_id, Subject.name).join(Subject, Subject.id == ExamSubject.subject_id).where(ExamSubject.exam_id == exam_id))).all()
    sections = (await db.execute(select(Section).where(Section.class_id == exam.class_id))).scalars().all()
    out = []
    for subject_id, subject_name in subjects:
        for section in sections:
            roster = await _class_roster(db, exam.class_id, section_id=section.id)
            entered = await db.scalar(
                select(func.count(func.distinct(ResultItem.id)))
                .select_from(ResultItem)
                .join(Result, Result.id == ResultItem.result_id)
                .join(Student, Student.id == Result.student_id)
                .where(Result.exam_id == exam_id, ResultItem.subject_id == subject_id, Student.section_id == section.id)
            )
            out.append({"subject_id": subject_id, "subject_name": subject_name, "section_id": section.id, "section_name": section.name, "entered": entered or 0, "total": len(roster)})
    return out
