"""phase 3 attendance and results

Adds: school_holidays, exam_subjects (per-exam snapshot of class_subjects).
Extends: attendance (remarks, updated_by), teacher_attendance (remarks), exams (publish workflow,
start/end date, unique per class+year+name), results (status, remarks), result_items (is_absent),
school_settings (weekly_off_days, attendance_alert_threshold, backdate_limit_days, timezone, and
flips fail_if_any_subject_failed's default to true per the Phase 3 spec).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-22 18:05:56.536067
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "school_holidays",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_school_holidays_created_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_school_holidays")),
        sa.UniqueConstraint("date", name=op.f("uq_school_holidays_date")),
    )
    op.create_table(
        "exam_subjects",
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("total_marks", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("passing_marks", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["exam_id"], ["exams.id"], name=op.f("fk_exam_subjects_exam_id_exams"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"], name=op.f("fk_exam_subjects_subject_id_subjects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_subjects")),
        sa.UniqueConstraint("exam_id", "subject_id", name=op.f("uq_exam_subjects_exam_id")),
    )
    op.create_index(op.f("ix_exam_subjects_exam_id"), "exam_subjects", ["exam_id"], unique=False)

    op.add_column("attendance", sa.Column("remarks", sa.Text(), nullable=True))
    op.add_column("attendance", sa.Column("updated_by", sa.Uuid(), nullable=True))
    op.create_index("ix_attendance_date_student_id", "attendance", ["date", "student_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_attendance_updated_by_users"), "attendance", "users", ["updated_by"], ["id"], ondelete="SET NULL"
    )

    op.add_column("teacher_attendance", sa.Column("remarks", sa.Text(), nullable=True))

    op.add_column("exams", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("exams", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column("exams", sa.Column("is_published", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("exams", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("exams", sa.Column("published_by", sa.Uuid(), nullable=True))
    op.create_unique_constraint(op.f("uq_exams_class_id"), "exams", ["class_id", "academic_year_id", "name"])
    op.create_foreign_key(
        op.f("fk_exams_published_by_users"), "exams", "users", ["published_by"], ["id"], ondelete="SET NULL"
    )

    op.add_column("result_items", sa.Column("is_absent", sa.Boolean(), server_default="false", nullable=False))

    op.add_column(
        "results",
        sa.Column(
            "status",
            sa.Enum("draft", "complete", name="resultstatus", native_enum=False, length=24),
            server_default="draft",
            nullable=False,
        ),
    )
    op.add_column("results", sa.Column("remarks", sa.Text(), nullable=True))
    op.create_index("ix_results_exam_id_percentage", "results", ["exam_id", "percentage"], unique=False)

    op.add_column(
        "school_settings",
        sa.Column(
            "weekly_off_days", postgresql.ARRAY(sa.Integer()), server_default=sa.text("'{7}'"), nullable=False
        ),
    )
    op.add_column(
        "school_settings", sa.Column("attendance_alert_threshold", sa.Integer(), server_default="75", nullable=False)
    )
    op.add_column(
        "school_settings", sa.Column("backdate_limit_days", sa.Integer(), server_default="7", nullable=False)
    )
    op.add_column(
        "school_settings",
        sa.Column("timezone", sa.String(length=64), server_default="Asia/Karachi", nullable=False),
    )
    # Phase 3 spec: schools should fail a student on any failed subject by default (Phase 2 shipped `false`).
    # Existing rows are updated too, not just the column default, so demo/prod data behaves the same way.
    op.execute("UPDATE school_settings SET fail_if_any_subject_failed = true WHERE fail_if_any_subject_failed = false")
    op.alter_column("school_settings", "fail_if_any_subject_failed", server_default=sa.text("true"))


def downgrade() -> None:
    op.alter_column("school_settings", "fail_if_any_subject_failed", server_default=sa.text("false"))
    op.drop_column("school_settings", "timezone")
    op.drop_column("school_settings", "backdate_limit_days")
    op.drop_column("school_settings", "attendance_alert_threshold")
    op.drop_column("school_settings", "weekly_off_days")

    op.drop_index("ix_results_exam_id_percentage", table_name="results")
    op.drop_column("results", "remarks")
    op.drop_column("results", "status")

    op.drop_column("result_items", "is_absent")

    op.drop_constraint(op.f("fk_exams_published_by_users"), "exams", type_="foreignkey")
    op.drop_constraint(op.f("uq_exams_class_id"), "exams", type_="unique")
    op.drop_column("exams", "published_by")
    op.drop_column("exams", "published_at")
    op.drop_column("exams", "is_published")
    op.drop_column("exams", "end_date")
    op.drop_column("exams", "start_date")

    op.drop_column("teacher_attendance", "remarks")

    op.drop_constraint(op.f("fk_attendance_updated_by_users"), "attendance", type_="foreignkey")
    op.drop_index("ix_attendance_date_student_id", table_name="attendance")
    op.drop_column("attendance", "updated_by")
    op.drop_column("attendance", "remarks")

    op.drop_index(op.f("ix_exam_subjects_exam_id"), table_name="exam_subjects")
    op.drop_table("exam_subjects")
    op.drop_table("school_holidays")
