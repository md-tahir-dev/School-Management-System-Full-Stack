"""Daily diary / homework and study material, shared with a class or one section of it.

Who reads a row (class_id, section_id | null = whole class): school-wide roles; teachers who teach or
are class teacher anywhere in that class/section; students of that class/section and their parents.
Who writes: managers anywhere; a teacher for a subject they teach there; the class teacher for a
general (no-subject) diary note. Only the author or a manager edits/deletes. Out of scope is 404."""

import uuid
from datetime import UTC, date, datetime, time

from fastapi import UploadFile
from sqlalchemy import ColumnElement, and_, exists, false, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, conflict, forbidden, invalid, not_found
from app.core.permissions import MANAGERS, SCHOOL_WIDE
from app.models import (
    ClassSubject,
    ClassTeacher,
    DiaryEntry,
    DiarySubmission,
    Material,
    Role,
    SchoolClass,
    Section,
    Student,
    Subject,
    TeacherAssignment,
    User,
)
from app.models.enums import MaterialType, StudentStatus
from app.schemas.common import Page, PageParams
from app.schemas.content import DiaryIn, DiaryOut, MaterialOut, SubmissionCheckIn, SubmissionOut, SubmissionRow
from app.services.audit import log_action
from app.services.dbutil import flush_or_conflict
from app.services.notify import family_user_ids, notify
from app.services.scoping import (
    get_student_in_scope,
    student_scope_clause,
    teacher_assigned_to_subject,
    teacher_id_for,
)
from app.services.storage import StorageBackend
from app.utils.pagination import like_pattern, paginate

Row = type[DiaryEntry] | type[Material]


# --- scope ---------------------------------------------------------------------------------------


def _covers(table, teacher_id: uuid.UUID, model: Row) -> ColumnElement[bool]:
    """`table` (TeacherAssignment or ClassTeacher) row of this teacher overlapping the row's class/section."""
    return exists().where(
        table.teacher_id == teacher_id,
        table.class_id == model.class_id,
        or_(table.section_id.is_(None), model.section_id.is_(None), table.section_id == model.section_id),
    )


async def _audience_student(db: AsyncSession, user: User, student_id: uuid.UUID | None) -> Student:
    if user.role == Role.STUDENT:
        student = await db.scalar(select(Student).where(Student.user_id == user.id, Student.is_deleted.is_(False)))
        if student is None:
            raise not_found("Student profile")
        return student
    if student_id is None:
        raise invalid("Choose a child.", {"student_id": "Required"})
    return await get_student_in_scope(db, user, student_id)


async def _read_clause(db: AsyncSession, user: User, model: Row, student: Student | None) -> ColumnElement[bool]:
    if user.role in SCHOOL_WIDE:
        return true()
    if user.role == Role.TEACHER:
        teacher_id = await teacher_id_for(db, user)
        if teacher_id is None:
            return false()
        return or_(_covers(TeacherAssignment, teacher_id, model), _covers(ClassTeacher, teacher_id, model))
    if student is not None:
        return and_(
            model.class_id == student.class_id,
            or_(model.section_id.is_(None), model.section_id == student.section_id),
        )
    # no child chosen (file downloads): any of the caller's own students (parent: any linked child)
    return exists().where(
        Student.is_deleted.is_(False),
        await student_scope_clause(db, user),
        Student.class_id == model.class_id,
        or_(model.section_id.is_(None), model.section_id == Student.section_id),
    )


async def _assert_can_write(
    db: AsyncSession, user: User, class_id: uuid.UUID, section_id: uuid.UUID | None, subject_id: uuid.UUID | None
) -> None:
    if await db.get(SchoolClass, class_id) is None:
        raise invalid("Unknown class.", {"class_id": "Unknown class"})
    if section_id is not None:
        section = await db.get(Section, section_id)
        if section is None or section.class_id != class_id:
            raise invalid("That section isn't in this class.", {"section_id": "Not in this class"})
    if subject_id is not None:
        taught = await db.scalar(
            select(exists().where(ClassSubject.class_id == class_id, ClassSubject.subject_id == subject_id))
        )
        if not taught:
            raise invalid("This subject isn't taught in this class.", {"subject_id": "Not a subject of this class"})
    if user.role in MANAGERS:
        return
    if user.role != Role.TEACHER:
        raise forbidden()
    teacher_id = await teacher_id_for(db, user)
    if teacher_id is None:
        raise not_found("Class section")
    has_sections = await db.scalar(select(exists().where(Section.class_id == class_id)))
    if section_id is None and has_sections:
        # a teacher posts per section; "whole class" would reach sections they don't teach
        raise invalid("Choose a section.", {"section_id": "Required"})
    if subject_id is not None:
        allowed = await teacher_assigned_to_subject(db, teacher_id, class_id, section_id, subject_id)
    else:
        allowed = await db.scalar(
            select(
                exists().where(
                    ClassTeacher.teacher_id == teacher_id,
                    ClassTeacher.class_id == class_id,
                    or_(ClassTeacher.section_id.is_(None), ClassTeacher.section_id == section_id),
                )
            )
        )
        if not allowed:
            raise invalid("Only the class teacher can post a note without a subject.", {"subject_id": "Required"})
    if not allowed:
        raise not_found("Class section")


def _can_edit(user: User, author_id: uuid.UUID | None) -> bool:
    return user.role in MANAGERS or (author_id is not None and author_id == user.id)


async def _get_readable(
    db: AsyncSession, user: User, model: Row, row_id: uuid.UUID, student_id: uuid.UUID | None = None
):
    student = None if user.role in (*SCHOOL_WIDE, Role.TEACHER) else await _audience_student(db, user, student_id)
    row = await db.scalar(select(model).where(model.id == row_id, await _read_clause(db, user, model, student)))
    if row is None:
        raise not_found("Diary entry" if model is DiaryEntry else "Material")
    return row, student


def _names_stmt(model: Row):
    return (
        select(model, SchoolClass.name, Section.name, Subject.name, User.full_name)
        .join(SchoolClass, SchoolClass.id == model.class_id)
        .outerjoin(Section, Section.id == model.section_id)
        .outerjoin(Subject, Subject.id == model.subject_id)
        .outerjoin(User, User.id == (model.created_by if model is DiaryEntry else model.uploaded_by))
    )


# --- diary ---------------------------------------------------------------------------------------


def _submission_out(s: DiarySubmission, due: date | None) -> SubmissionOut:
    late = due is not None and s.submitted_at > datetime.combine(due, time.max, tzinfo=UTC)
    return SubmissionOut(
        id=s.id,
        student_id=s.student_id,
        file_url=s.file_url,
        note=s.note,
        submitted_at=s.submitted_at,
        checked=s.checked,
        remarks=s.remarks,
        late=late,
    )


def _diary_out(user: User, row, *, count: int | None = None, mine: DiarySubmission | None = None) -> DiaryOut:
    e, class_name, section_name, subject_name, author = row
    return DiaryOut(
        id=e.id,
        class_id=e.class_id,
        class_name=class_name,
        section_id=e.section_id,
        section_name=section_name,
        subject_id=e.subject_id,
        subject_name=subject_name,
        date=e.date,
        title=e.title,
        body=e.body,
        attachment_url=e.attachment_url,
        submission_required=e.submission_required,
        due_date=e.due_date,
        author_name=author,
        created_at=e.created_at,
        can_edit=_can_edit(user, e.created_by),
        submission_count=count,
        my_submission=_submission_out(mine, e.due_date) if mine else None,
    )


async def list_diary(
    db: AsyncSession,
    user: User,
    *,
    day: date,
    class_id: uuid.UUID | None,
    section_id: uuid.UUID | None,
    student_id: uuid.UUID | None,
) -> list[DiaryOut]:
    staff = user.role in (*SCHOOL_WIDE, Role.TEACHER)
    student = None if staff else await _audience_student(db, user, student_id)
    stmt = (
        _names_stmt(DiaryEntry)
        .where(DiaryEntry.date == day, await _read_clause(db, user, DiaryEntry, student))
        .order_by(Subject.name.nulls_first(), DiaryEntry.created_at)
    )
    if staff and class_id:
        stmt = stmt.where(DiaryEntry.class_id == class_id)
    if staff and section_id:
        stmt = stmt.where(or_(DiaryEntry.section_id.is_(None), DiaryEntry.section_id == section_id))
    rows = (await db.execute(stmt)).all()
    ids = [r[0].id for r in rows]
    if staff:
        counts = (
            dict(
                (
                    await db.execute(
                        select(DiarySubmission.entry_id, func.count())
                        .where(DiarySubmission.entry_id.in_(ids))
                        .group_by(DiarySubmission.entry_id)
                    )
                ).all()
            )
            if ids
            else {}
        )
        return [_diary_out(user, r, count=counts.get(r[0].id, 0)) for r in rows]
    mine = (
        {
            s.entry_id: s
            for s in await db.scalars(
                select(DiarySubmission).where(
                    DiarySubmission.entry_id.in_(ids), DiarySubmission.student_id == student.id
                )
            )
        }
        if ids
        else {}
    )
    return [_diary_out(user, r, mine=mine.get(r[0].id)) for r in rows]


async def _diary_row(db: AsyncSession, user: User, entry_id: uuid.UUID) -> DiaryOut:
    row = (await db.execute(_names_stmt(DiaryEntry).where(DiaryEntry.id == entry_id))).one()
    return _diary_out(user, row)


async def create_diary(db: AsyncSession, actor: User, body: DiaryIn, ip: str | None) -> DiaryOut:
    await _assert_can_write(db, actor, body.class_id, body.section_id, body.subject_id)
    entry = DiaryEntry(**body.model_dump(), created_by=actor.id)
    db.add(entry)
    await db.flush()
    log_action(actor, "create", "diary_entry", entry.id, {"date": str(body.date), "title": body.title}, db=db, ip=ip)
    section = Student.section_id == body.section_id if body.section_id else true()
    await notify(
        db,
        await family_user_ids(db, and_(Student.class_id == body.class_id, section)),
        f"New diary entry: {body.title}" + (" (work to submit)" if body.submission_required else ""),
        f"diary?date={body.date}",
    )
    await db.commit()
    return await _diary_row(db, actor, entry.id)


async def _editable_entry(db: AsyncSession, actor: User, entry_id: uuid.UUID) -> DiaryEntry:
    entry, _ = await _get_readable(db, actor, DiaryEntry, entry_id)
    if not _can_edit(actor, entry.created_by):
        raise forbidden("Only the author or a manager can change this entry.")
    return entry


async def update_diary(db: AsyncSession, actor: User, entry_id: uuid.UUID, body: DiaryIn, ip: str | None) -> DiaryOut:
    entry = await _editable_entry(db, actor, entry_id)
    await _assert_can_write(db, actor, body.class_id, body.section_id, body.subject_id)
    for k, v in body.model_dump().items():
        setattr(entry, k, v)
    log_action(actor, "update", "diary_entry", entry.id, {"title": body.title}, db=db, ip=ip)
    await db.commit()
    return await _diary_row(db, actor, entry.id)


async def delete_diary(
    db: AsyncSession, actor: User, entry_id: uuid.UUID, storage: StorageBackend, ip: str | None
) -> None:
    entry = await _editable_entry(db, actor, entry_id)
    files = [
        entry.attachment_url,
        *(await db.scalars(select(DiarySubmission.file_url).where(DiarySubmission.entry_id == entry.id))),
    ]
    await db.delete(entry)
    log_action(actor, "delete", "diary_entry", entry_id, {"title": entry.title}, db=db, ip=ip)
    await db.commit()
    for url in files:
        await storage.delete(url)


async def set_diary_attachment(
    db: AsyncSession, actor: User, entry_id: uuid.UUID, file: UploadFile | None, storage: StorageBackend
) -> DiaryOut:
    entry = await _editable_entry(db, actor, entry_id)
    old = entry.attachment_url
    entry.attachment_url = await storage.save_document(file, "diary") if file else None
    await db.commit()
    await storage.delete(old)
    return await _diary_row(db, actor, entry.id)


async def submit_work(
    db: AsyncSession,
    actor: User,
    entry_id: uuid.UUID,
    note: str | None,
    file: UploadFile | None,
    storage: StorageBackend,
) -> SubmissionOut:
    if actor.role != Role.STUDENT:
        raise forbidden("Only the student can submit their work.")
    entry, student = await _get_readable(db, actor, DiaryEntry, entry_id)
    if not entry.submission_required:
        raise conflict("This entry doesn't take submissions.", code="submission_not_required")
    note = (note or "").strip() or None
    if note is None and file is None:
        raise invalid("Attach a file or write a note.", {"file": "Required"})
    if note is not None and len(note) > 5000:
        raise invalid("The note is too long.", {"note": "At most 5000 characters"})
    sub = await db.scalar(
        select(DiarySubmission).where(DiarySubmission.entry_id == entry.id, DiarySubmission.student_id == student.id)
    )
    if sub is not None and sub.checked:
        raise conflict("Your teacher has already checked this work.", code="already_checked")
    url = await storage.save_document(file, "homework") if file else None
    old = None
    if sub is None:
        sub = DiarySubmission(entry_id=entry.id, student_id=student.id, file_url=url, note=note)
        db.add(sub)
    else:
        old = sub.file_url if url else None
        sub.file_url, sub.note, sub.submitted_at = url or sub.file_url, note, func.now()
    try:
        await flush_or_conflict(db, "Already submitted.", code="already_submitted")
    except AppError:
        await storage.delete(url)  # don't leave the losing duplicate's upload behind
        raise
    await db.commit()
    await db.refresh(sub)
    await storage.delete(old)
    return _submission_out(sub, entry.due_date)


async def list_submissions(db: AsyncSession, actor: User, entry_id: uuid.UUID) -> list[SubmissionRow]:
    if actor.role not in (*SCHOOL_WIDE, Role.TEACHER):
        raise forbidden()
    entry, _ = await _get_readable(db, actor, DiaryEntry, entry_id)
    roster = (
        select(Student, DiarySubmission)
        .outerjoin(
            DiarySubmission, and_(DiarySubmission.student_id == Student.id, DiarySubmission.entry_id == entry.id)
        )
        .where(
            Student.class_id == entry.class_id,
            Student.is_deleted.is_(False),
            or_(Student.status == StudentStatus.ACTIVE, DiarySubmission.id.is_not(None)),
            # a teacher sees only the students they teach this subject to (class teacher: general notes)
            await student_scope_clause(db, actor, subject_id=entry.subject_id),
        )
        .order_by(Student.roll_no)
    )
    if entry.section_id is not None:
        roster = roster.where(Student.section_id == entry.section_id)
    return [
        SubmissionRow(
            student_id=st.id,
            full_name=st.full_name,
            roll_no=st.roll_no,
            submission=_submission_out(sub, entry.due_date) if sub else None,
        )
        for st, sub in (await db.execute(roster)).all()
    ]


async def check_submission(
    db: AsyncSession, actor: User, submission_id: uuid.UUID, body: SubmissionCheckIn
) -> SubmissionOut:
    sub = await db.get(DiarySubmission, submission_id)
    if sub is None:
        raise not_found("Submission")
    entry, _ = await _get_readable(db, actor, DiaryEntry, sub.entry_id)
    if not _can_edit(actor, entry.created_by):
        # the student's own subject teacher (or class teacher, for a general note) may check it
        in_scope = await db.scalar(
            select(Student.id).where(
                Student.id == sub.student_id, await student_scope_clause(db, actor, subject_id=entry.subject_id)
            )
        )
        if in_scope is None or (entry.subject_id is None and not await _is_class_teacher_of(db, actor, sub.student_id)):
            raise not_found("Submission")
    sub.checked, sub.remarks = body.checked, body.remarks
    await db.commit()
    return _submission_out(sub, entry.due_date)


async def _is_class_teacher_of(db: AsyncSession, user: User, student_id: uuid.UUID) -> bool:
    teacher_id = await teacher_id_for(db, user)
    student = await db.get(Student, student_id)
    return bool(
        teacher_id
        and student
        and await db.scalar(
            select(
                exists().where(
                    ClassTeacher.teacher_id == teacher_id,
                    ClassTeacher.class_id == student.class_id,
                    or_(ClassTeacher.section_id.is_(None), ClassTeacher.section_id == student.section_id),
                )
            )
        )
    )


# --- materials -----------------------------------------------------------------------------------


def _material_out(user: User, row) -> MaterialOut:
    m, class_name, section_name, subject_name, author = row
    return MaterialOut(
        id=m.id,
        title=m.title,
        description=m.description,
        type=m.type,
        class_id=m.class_id,
        class_name=class_name,
        section_id=m.section_id,
        section_name=section_name,
        subject_id=m.subject_id,
        subject_name=subject_name,
        file_url=m.file_url,
        external_link=m.external_link,
        author_name=author,
        created_at=m.created_at,
        can_edit=_can_edit(user, m.uploaded_by),
    )


async def list_materials(
    db: AsyncSession,
    user: User,
    params: PageParams,
    *,
    class_id: uuid.UUID | None,
    subject_id: uuid.UUID | None,
    type_: MaterialType | None,
    student_id: uuid.UUID | None,
) -> Page:
    staff = user.role in (*SCHOOL_WIDE, Role.TEACHER)
    student = None if staff else await _audience_student(db, user, student_id)
    stmt = _names_stmt(Material).where(await _read_clause(db, user, Material, student))
    if staff and class_id:
        stmt = stmt.where(Material.class_id == class_id)
    if subject_id:
        stmt = stmt.where(Material.subject_id == subject_id)
    if type_:
        stmt = stmt.where(Material.type == type_)
    if params.q:
        stmt = stmt.where(Material.title.ilike(like_pattern(params.q)))
    stmt = stmt.order_by(Material.created_at.desc())
    return await paginate(db, stmt, params, MaterialOut, row_mapper=lambda r: _material_out(user, r))


async def create_material(
    db: AsyncSession,
    actor: User,
    *,
    title: str,
    description: str | None,
    type_: MaterialType,
    class_id: uuid.UUID,
    section_id: uuid.UUID | None,
    subject_id: uuid.UUID | None,
    external_link: str | None,
    file: UploadFile | None,
    storage: StorageBackend,
    ip: str | None,
) -> MaterialOut:
    title, description = title.strip(), (description or "").strip() or None
    external_link = (external_link or "").strip() or None
    if not 1 <= len(title) <= 200:
        raise invalid("Give the material a title.", {"title": "1-200 characters"})
    if external_link and not external_link.startswith(("https://", "http://")):
        raise invalid("Links must start with http:// or https://.", {"external_link": "Not a web link"})
    if external_link and len(external_link) > 500:
        raise invalid("The link is too long.", {"external_link": "At most 500 characters"})
    if not external_link and file is None:
        raise invalid("Upload a file or add a link.", {"file": "Required"})
    if actor.role == Role.TEACHER and subject_id is None:
        raise invalid("Choose the subject.", {"subject_id": "Required"})
    await _assert_can_write(db, actor, class_id, section_id, subject_id)
    url = await storage.save_document(file, "materials") if file else None
    material = Material(
        title=title,
        description=description,
        type=type_,
        class_id=class_id,
        section_id=section_id,
        subject_id=subject_id,
        file_url=url,
        external_link=external_link,
        uploaded_by=actor.id,
    )
    db.add(material)
    await db.flush()
    log_action(actor, "create", "material", material.id, {"title": title}, db=db, ip=ip)
    await db.commit()
    row = (await db.execute(_names_stmt(Material).where(Material.id == material.id))).one()
    return _material_out(actor, row)


async def delete_material(
    db: AsyncSession, actor: User, material_id: uuid.UUID, storage: StorageBackend, ip: str | None
) -> None:
    material, _ = await _get_readable(db, actor, Material, material_id)
    if not _can_edit(actor, material.uploaded_by):
        raise forbidden("Only the uploader or a manager can remove this material.")
    await db.delete(material)
    log_action(actor, "delete", "material", material_id, {"title": material.title}, db=db, ip=ip)
    await db.commit()
    await storage.delete(material.file_url)


# --- file downloads ------------------------------------------------------------------------------


async def assert_can_download(db: AsyncSession, user: User, folder: str, url: str) -> None:
    """404 unless `url` is a diary attachment, homework submission or material file the caller may read.
    Submissions: the student, their parents, teachers who see that entry's submissions, school-wide."""
    if folder == "diary":
        found = await db.scalar(
            select(DiaryEntry.id).where(
                DiaryEntry.attachment_url == url, await _read_clause(db, user, DiaryEntry, None)
            )
        )
    elif folder == "materials":
        found = await db.scalar(
            select(Material.id).where(Material.file_url == url, await _read_clause(db, user, Material, None))
        )
    elif folder == "homework":
        row = (
            await db.execute(
                select(DiarySubmission.student_id, DiaryEntry)
                .join(DiaryEntry, DiaryEntry.id == DiarySubmission.entry_id)
                .where(DiarySubmission.file_url == url)
            )
        ).first()
        found = row and await db.scalar(
            select(DiaryEntry.id).where(
                DiaryEntry.id == row[1].id,
                await _read_clause(db, user, DiaryEntry, None),
                exists().where(
                    Student.id == row[0],
                    Student.is_deleted.is_(False),
                    # same roster rule as list_submissions (teacher: this subject's students)
                    await student_scope_clause(db, user, subject_id=row[1].subject_id),
                ),
            )
        )
    else:
        found = None
    if not found:
        raise not_found("File")
