import uuid
from datetime import date
from decimal import Decimal  # noqa: F401

from sqlalchemy import Date, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin, enum_col
from app.models.enums import EmploymentType, Gender, StudentStatus


class Guardian(IdMixin, TimestampMixin, Base):
    __tablename__ = "guardians"

    father_name: Mapped[str | None] = mapped_column(String(150))
    father_cnic: Mapped[str | None] = mapped_column(String(15), unique=True, index=True)  # sibling lookup key
    father_phone: Mapped[str | None] = mapped_column(String(32))
    father_occupation: Mapped[str | None] = mapped_column(String(100))
    mother_name: Mapped[str | None] = mapped_column(String(150))
    mother_cnic: Mapped[str | None] = mapped_column(String(15))
    mother_phone: Mapped[str | None] = mapped_column(String(32))
    guardian_name: Mapped[str | None] = mapped_column(String(150))
    guardian_phone: Mapped[str | None] = mapped_column(String(32))
    guardian_relation: Mapped[str | None] = mapped_column(String(64))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), unique=True)


class Student(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "students"

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    roll_no: Mapped[str] = mapped_column(String(32), unique=True)
    full_name: Mapped[str] = mapped_column(String(150), index=True)
    dob: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[Gender | None] = mapped_column(enum_col(Gender))
    religion: Mapped[str | None] = mapped_column(String(64))
    nationality: Mapped[str | None] = mapped_column(String(64))
    blood_group: Mapped[str | None] = mapped_column(String(8))
    photo_url: Mapped[str | None] = mapped_column(String(500))
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id"))
    section_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sections.id"))
    admission_date: Mapped[date | None] = mapped_column(Date)
    previous_school: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    emergency_name: Mapped[str | None] = mapped_column(String(150))
    emergency_phone: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[StudentStatus] = mapped_column(
        enum_col(StudentStatus), default=StudentStatus.ACTIVE, server_default=StudentStatus.ACTIVE.value
    )
    status_reason: Mapped[str | None] = mapped_column(Text)  # required when expelled

    __table_args__ = (Index("ix_students_class_id_section_id", "class_id", "section_id"),)


class StudentGuardian(IdMixin, Base):
    """One parent, many children."""

    __tablename__ = "student_guardians"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    guardian_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guardians.id", ondelete="CASCADE"), index=True)

    __table_args__ = (UniqueConstraint("student_id", "guardian_id"),)


class Teacher(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "teachers"

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    employee_id: Mapped[str] = mapped_column(String(32), unique=True)
    full_name: Mapped[str] = mapped_column(String(150), index=True)
    father_name: Mapped[str | None] = mapped_column(String(150))
    dob: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[Gender | None] = mapped_column(enum_col(Gender))
    cnic: Mapped[str | None] = mapped_column(String(15), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    emergency_contact: Mapped[str | None] = mapped_column(String(64))
    photo_url: Mapped[str | None] = mapped_column(String(500))
    blood_group: Mapped[str | None] = mapped_column(String(8))
    religion: Mapped[str | None] = mapped_column(String(64))
    designation: Mapped[str | None] = mapped_column(String(100))
    qualification: Mapped[str | None] = mapped_column(String(200))
    joining_date: Mapped[date | None] = mapped_column(Date)
    employment_type: Mapped[EmploymentType | None] = mapped_column(enum_col(EmploymentType))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))


class TeacherAssignment(IdMixin, TimestampMixin, Base):
    __tablename__ = "teacher_assignments"

    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), index=True)
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    section_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"))
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))

    __table_args__ = (
        Index("ix_teacher_assignments_class_section", "class_id", "section_id"),
        UniqueConstraint(
            "teacher_id",
            "class_id",
            "section_id",
            "subject_id",
            name="uq_teacher_assignments_scope",
            postgresql_nulls_not_distinct=True,
        ),
    )
