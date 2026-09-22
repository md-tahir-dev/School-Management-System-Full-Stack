"""Row-level access rules, enforced in the service layer (not only in routes).

A student that exists but is outside the caller's scope is reported as *not found*, so a caller
can't learn which IDs exist."""

import uuid

from sqlalchemy import ColumnElement, exists, false, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden, not_found
from app.models import Guardian, Role, Student, StudentGuardian, Teacher, TeacherAssignment, User


async def teacher_id_for(db: AsyncSession, user: User) -> uuid.UUID | None:
    return await db.scalar(select(Teacher.id).where(Teacher.user_id == user.id, Teacher.is_deleted.is_(False)))


async def student_scope_clause(db: AsyncSession, user: User) -> ColumnElement[bool]:
    """SQL condition restricting `Student` rows to what `user` may see."""
    match user.role:
        case Role.ADMIN | Role.CEO:
            return true()
        case Role.TEACHER:
            teacher_id = await teacher_id_for(db, user)
            if teacher_id is None:
                return false()
            return exists(
                select(TeacherAssignment.id).where(
                    TeacherAssignment.teacher_id == teacher_id,
                    TeacherAssignment.class_id == Student.class_id,
                    # an assignment without a section covers the whole class
                    or_(TeacherAssignment.section_id.is_(None), TeacherAssignment.section_id == Student.section_id),
                )
            )
        case Role.STUDENT:
            return Student.user_id == user.id
        case Role.PARENT:
            return Student.id.in_(
                select(StudentGuardian.student_id)
                .join(Guardian, Guardian.id == StudentGuardian.guardian_id)
                .where(Guardian.user_id == user.id)
            )
    raise forbidden()


async def get_student_in_scope(db: AsyncSession, user: User, student_id: uuid.UUID) -> Student:
    clause = await student_scope_clause(db, user)
    student = await db.scalar(select(Student).where(Student.id == student_id, Student.is_deleted.is_(False), clause))
    if student is None:
        raise not_found("Student")
    return student
