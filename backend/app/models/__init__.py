"""Import every model so Alembic autogenerate and Base.metadata see all tables."""

from app.models.attendance import Attendance, SchoolHoliday, TeacherAttendance
from app.models.content import Announcement, DiaryEntry, DiarySubmission, Event, Material, Notification
from app.models.core import (
    AcademicYear,
    AuditLog,
    ClassSubject,
    Counter,
    RefreshToken,
    SchoolClass,
    SchoolSettings,
    Section,
    Subject,
    User,
)
from app.models.enums import Role
from app.models.fees import FeeLedger, FeeStructure, Payment, PaymentAllocation, StudentFeeSetting
from app.models.online_tests import Attempt, AttemptAnswer, OnlineTest, Question
from app.models.people import Guardian, Student, StudentGuardian, Teacher, TeacherAssignment
from app.models.results import Exam, ExamSubject, Result, ResultItem
from app.models.salary import SalaryAdvance, SalaryRecord, SalaryStructure
from app.models.timetable import ClassTeacher, Period, TimetableEntry

__all__ = [
    "AcademicYear",
    "Announcement",
    "Attempt",
    "AttemptAnswer",
    "Attendance",
    "AuditLog",
    "ClassSubject",
    "ClassTeacher",
    "Counter",
    "DiaryEntry",
    "DiarySubmission",
    "Event",
    "Exam",
    "ExamSubject",
    "FeeLedger",
    "FeeStructure",
    "Guardian",
    "Material",
    "Notification",
    "OnlineTest",
    "Payment",
    "Period",
    "PaymentAllocation",
    "Question",
    "RefreshToken",
    "Result",
    "ResultItem",
    "Role",
    "SalaryAdvance",
    "SalaryRecord",
    "SalaryStructure",
    "SchoolClass",
    "SchoolHoliday",
    "SchoolSettings",
    "Section",
    "Student",
    "StudentFeeSetting",
    "StudentGuardian",
    "Subject",
    "Teacher",
    "TeacherAssignment",
    "TeacherAttendance",
    "TimetableEntry",
    "User",
]
