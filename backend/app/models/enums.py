from enum import StrEnum


class Role(StrEnum):
    CEO = "ceo"
    ADMIN = "admin"
    HEADMASTER = "headmaster"
    TEACHER = "teacher"
    STUDENT = "student"
    PARENT = "parent"


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class StudentStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    GRADUATED = "graduated"
    EXPELLED = "expelled"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"


class AttendanceStatus(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    SICK = "sick"


class TeacherAttendanceStatus(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    LEAVE = "leave"


class ExamType(StrEnum):
    FIRST_TERM = "1st Term"
    MID_TERM = "Mid Term"
    FINAL_TERM = "Final Term"
    UNIT_TEST = "Unit Test"


class ResultStatus(StrEnum):
    DRAFT = "draft"
    COMPLETE = "complete"


class FeeStatus(StrEnum):
    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"


class PaymentMethod(StrEnum):
    CASH = "cash"
    BANK = "bank"
    ONLINE = "online"
    CHEQUE = "cheque"


class SalaryStatus(StrEnum):
    UNPAID = "unpaid"
    PAID = "paid"


class TestStatus(StrEnum):
    __test__ = False  # not a pytest class
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class QuestionType(StrEnum):
    MCQ = "mcq"
    SHORT = "short"
    TRUE_FALSE = "tf"


class AttemptStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"  # submitted, waiting for teacher grading
    GRADED = "graded"
    EXPIRED = "expired"  # closed by the server after the deadline


class MaterialType(StrEnum):
    NOTES = "notes"
    PAST_PAPER = "past_paper"
    ASSIGNMENT = "assignment"
    REFERENCE = "reference"


class Audience(StrEnum):
    ALL = "all"
    TEACHERS = "teachers"
    STUDENTS = "students"
    PARENTS = "parents"


class EventType(StrEnum):
    EVENT = "event"
    PTM = "ptm"
    EXAM = "exam"
    SPORTS = "sports"
    OTHER = "other"


class Priority(StrEnum):
    NORMAL = "normal"
    IMPORTANT = "important"


class Designation(StrEnum):
    HEAD_TEACHER = "Head Teacher"
    COORDINATOR = "Coordinator"
    SENIOR_TEACHER = "Senior Teacher"
    TEACHER = "Teacher"
    JUNIOR_TEACHER = "Junior Teacher"
    SUBSTITUTE = "Substitute Teacher"


class Qualification(StrEnum):
    MATRIC = "Matric"
    INTERMEDIATE = "Intermediate"
    BACHELORS = "Bachelor's"
    B_ED = "B.Ed"
    MASTERS = "Master's"
    M_ED = "M.Ed"
    M_PHIL = "M.Phil"
    PHD = "PhD"
