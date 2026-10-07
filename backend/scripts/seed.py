"""Idempotent seed: school settings, current academic year, users, and (demo/sample mode) a small school.

  python -m scripts.seed

APP_ENV=demo          -> demo logins for every role + sample school data (password = SEED_DEMO_PASSWORD)
SEED_SAMPLE_DATA=true -> sample school data outside demo mode (random temporary passwords are printed once)
otherwise             -> only the first admin from FIRST_ADMIN_USERNAME / FIRST_ADMIN_PASSWORD

Safe to run repeatedly: existing rows are never modified. Students and teachers are created through the
same service functions the API uses, so seeding exercises the real registration transaction."""

import asyncio
import sys
from datetime import date, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.core.demo import DEMO_USERS
from app.core.errors import AppError
from app.core.security import hash_password, validate_password_strength
from app.db.session import SessionLocal, engine
from app.models import (
    AcademicYear,
    Attendance,
    ClassSubject,
    Exam,
    SchoolHoliday,
    TeacherAttendance,
    FeeStructure,
    Guardian,
    Role,
    SchoolClass,
    Section,
    Student,
    Subject,
    Teacher,
    User,
)
from app.models.enums import AttendanceStatus, ExamType, StudentStatus, TeacherAttendanceStatus
from app.schemas.attendance import (
    AttendanceRecordIn,
    BulkAttendanceIn,
    BulkTeacherAttendanceIn,
    HolidayIn,
    TeacherAttendanceRecordIn,
)
from app.schemas.results import ExamIn, MarkSaveIn, MarksBulkSaveIn
from app.schemas.students import StudentCreate
from app.schemas.teachers import TeacherCreate
from app.services import attendance as attendance_svc
from app.services import exams as exam_svc
from app.services import holidays as holiday_svc
from app.services import students as student_svc
from app.services import teacher_attendance as teacher_attendance_svc
from app.services import teachers as teacher_svc
from app.services.settings import get_school_settings

# ------------------------------------------------------------------ sample data
CLASSES = [("Class 1", 1, "2000"), ("Class 2", 2, "2500"), ("Class 3", 3, "3000")]
SECTIONS = ("A", "B")
SUBJECTS = ("English", "Urdu", "Mathematics", "Science", "Islamiat", "Social Studies")

# (full name, dob, gender, class, section, discount %, guardian (father, cnic, phone))
_KHAN = {"father_name": "Imran Khan", "father_cnic": "35202-1000001-1", "father_phone": "0300-1000001"}
STUDENTS = [
    ("Hamza Khan", "2018-04-12", "male", "Class 1", "A", "0", _KHAN),  # demo student login; sibling of Zara
    ("Zara Khan", "2015-09-02", "female", "Class 3", "B", "0", _KHAN),  # same guardian -> one parent, two children
    (
        "Ayesha Malik",
        "2018-01-20",
        "female",
        "Class 1",
        "A",
        "0",
        {"father_name": "Tariq Malik", "father_cnic": "35202-1000002-1", "father_phone": "0301-1000002"},
    ),
    (
        "Bilal Ahmed",
        "2018-06-30",
        "male",
        "Class 1",
        "B",
        "25",
        {"father_name": "Nadeem Ahmed", "father_cnic": "35202-1000003-1", "father_phone": "0302-1000003"},
    ),
    (
        "Daniyal Shah",
        "2017-11-05",
        "male",
        "Class 1",
        "B",
        "0",
        {"father_name": "Farhan Shah", "father_cnic": "35202-1000004-1", "father_phone": "0303-1000004"},
    ),
    (
        "Fatima Noor",
        "2017-02-14",
        "female",
        "Class 2",
        "A",
        "0",
        {"father_name": "Noor Muhammad", "father_cnic": "35202-1000005-1", "father_phone": "0304-1000005"},
    ),
    (
        "Usman Tariq",
        "2016-08-09",
        "male",
        "Class 2",
        "A",
        "50",
        {"father_name": "Tariq Mehmood", "father_cnic": "35202-1000006-1", "father_phone": "0305-1000006"},
    ),
    (
        "Maryam Siddiqui",
        "2016-12-25",
        "female",
        "Class 2",
        "B",
        "0",
        {"father_name": "Asif Siddiqui", "father_cnic": "35202-1000007-1", "father_phone": "0306-1000007"},
    ),
    (
        "Hassan Raza",
        "2015-03-18",
        "male",
        "Class 3",
        "A",
        "0",
        {"father_name": "Raza Hussain", "father_cnic": "35202-1000008-1", "father_phone": "0307-1000008"},
    ),
    (
        "Sana Iqbal",
        "2015-07-07",
        "female",
        "Class 3",
        "B",
        "0",
        {"father_name": "Iqbal Ahmad", "father_cnic": "35202-1000009-1", "father_phone": "0308-1000009"},
    ),
]

# (name, cnic, phone, designation, qualification, employment, [(class, section|None, subject)], demo login)
TEACHERS = [
    (
        "Sadia Hussain",
        "35202-2000001-1",
        "0311-2000001",
        "Senior Teacher",
        "Master's",
        "full_time",
        [("Class 1", "A", "English"), ("Class 1", "B", "English"), ("Class 2", "A", "English")],
        True,
    ),
    (
        "Kamran Ali",
        "35202-2000002-1",
        "0312-2000002",
        "Teacher",
        "Bachelor's",
        "full_time",
        [("Class 1", None, "Mathematics"), ("Class 2", None, "Mathematics")],
        False,
    ),
    (
        "Nadia Farooq",
        "35202-2000003-1",
        "0313-2000003",
        "Coordinator",
        "M.Phil",
        "full_time",
        [("Class 3", None, "Science"), ("Class 3", None, "Urdu")],
        False,
    ),
]


def _academic_year_bounds(today: date) -> tuple[str, date, date]:
    start_year = today.year if today.month >= 4 else today.year - 1
    return f"{start_year}-{start_year + 1}", date(start_year, 4, 1), date(start_year + 1, 3, 31)


async def _seed_structure() -> dict:
    """Classes, sections, subjects, class-subject marks and monthly fees. Returns name -> id lookups."""
    ids: dict = {"class": {}, "section": {}, "subject": {}}
    async with SessionLocal() as db:
        for name, order, fee in CLASSES:
            klass = await db.scalar(select(SchoolClass).where(SchoolClass.name == name))
            if klass is None:
                klass = SchoolClass(name=name, sort_order=order)
                db.add(klass)
                await db.flush()
            ids["class"][name] = klass.id
            for sec in SECTIONS:
                section = await db.scalar(select(Section).where(Section.class_id == klass.id, Section.name == sec))
                if section is None:
                    section = Section(class_id=klass.id, name=sec)
                    db.add(section)
                    await db.flush()
                ids["section"][(name, sec)] = section.id
            if await db.scalar(select(FeeStructure.id).where(FeeStructure.class_id == klass.id)) is None:
                db.add(FeeStructure(class_id=klass.id, monthly_fee=fee))
        for name in SUBJECTS:
            subject = await db.scalar(select(Subject).where(Subject.name == name))
            if subject is None:
                subject = Subject(name=name)
                db.add(subject)
                await db.flush()
            ids["subject"][name] = subject.id
        for class_id in ids["class"].values():
            for subject_id in ids["subject"].values():
                exists = await db.scalar(
                    select(ClassSubject.id).where(
                        ClassSubject.class_id == class_id, ClassSubject.subject_id == subject_id
                    )
                )
                if exists is None:
                    db.add(ClassSubject(class_id=class_id, subject_id=subject_id, total_marks=100, passing_marks=40))
        await db.commit()
    return ids


async def _remove_unlinked_demo_user(username: str) -> None:
    """Phase 1 seeded bare teacher/student/parent demo users with no profile. Those names now belong to real
    profiles created below, so drop an old unlinked account (it has no data of its own) before re-creating it."""
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == username))
        if user is None:
            return
        linked = (
            await db.scalar(select(Teacher.id).where(Teacher.user_id == user.id))
            or await db.scalar(select(Student.id).where(Student.user_id == user.id))
            or await db.scalar(select(Guardian.id).where(Guardian.user_id == user.id))
        )
        if not linked:
            await db.delete(user)
            await db.commit()


async def _seed_people(ids: dict, demo: bool, shown: list[tuple[str, str, str]]) -> tuple[int, int]:
    pw = settings.seed_demo_password
    if demo:
        for username in ("teacher", "student", "parent"):
            await _remove_unlinked_demo_user(username)

    teachers = 0
    for name, cnic, phone, designation, qualification, employment, assignments, demo_login in TEACHERS:
        async with SessionLocal() as db:
            if await db.scalar(select(Teacher.id).where(Teacher.cnic == cnic)):
                continue
            payload = TeacherCreate(
                full_name=name,
                gender="female" if name.split()[0] in ("Sadia", "Nadia") else "male",
                cnic=cnic,
                phone=phone,
                designation=designation,
                qualification=qualification,
                joining_date="2023-08-01",
                employment_type=employment,
                city="Lahore",
                salary={"basic": "60000", "house": "12000", "transport": "6000", "medical": "3000"},
                assignments=[
                    {
                        "class_id": ids["class"][c],
                        "section_id": ids["section"][(c, s)] if s else None,
                        "subject_id": ids["subject"][subj],
                    }
                    for c, s, subj in assignments
                ],
            )
            login = ("teacher", pw) if (demo and demo_login) else None
            reg = await teacher_svc.register_teacher(db, payload, None, login=login)
            teachers += 1
            if not login:
                shown.append(("teacher", reg.credential.username, reg.credential.temp_password))

    students = 0
    for i, (name, dob, gender, klass, section, discount, guardian) in enumerate(STUDENTS):
        payload = StudentCreate(
            full_name=name,
            dob=dob,
            gender=gender,
            class_id=ids["class"][klass],
            section_id=ids["section"][(klass, section)],
            religion="Islam",
            nationality="Pakistani",
            city="Lahore",
            discount_percent=discount,
            guardian=guardian,
            create_student_login=(i == 0),
        )
        logins = None
        if demo:
            logins = student_svc.LoginOverrides(
                parent=("parent", pw) if i == 0 else None, student=("student", pw) if i == 0 else None
            )
        async with SessionLocal() as db:
            try:
                reg = await student_svc.register_student(db, payload, None, logins=logins)
            except AppError as exc:
                if exc.code == "DUPLICATE_STUDENT":
                    continue  # already seeded
                raise
        students += 1
        if reg.parent_credential and not (demo and i == 0):
            shown.append(("parent", reg.parent_credential.username, reg.parent_credential.temp_password))
        if reg.student_credential and not demo:
            shown.append(("student", reg.student_credential.username, reg.student_credential.temp_password))
    return teachers, students



# ------------------------------------------------------------------ Phase 3 sample data
LOW_ATTENDANCE_STUDENT = "Ayesha Malik"  # deliberately below the 75% alert threshold


def _school_days(today: date, count: int, skip: set[date]) -> list[date]:
    """The most recent `count` school days (no Sundays, no holidays), oldest first."""
    days: list[date] = []
    d = today
    while len(days) < count:
        if d.isoweekday() != 7 and d not in skip:
            days.append(d)
        d -= timedelta(days=1)
    return list(reversed(days))


def _mark_plan(position: int, subject_names: list[str]) -> dict[str, tuple[int, bool] | None]:
    """subject name -> (obtained, is_absent), or None when that subject is not entered yet.
    Position in the class roster decides the story each student tells (documented in the README):
      0 and 1  tie for first place (92 in everything)
      2        fails Mathematics (30) but does well elsewhere -> overall FAIL under the fail rule
      3        absent in Science and Social Studies not entered -> incomplete (draft), no grade/rank
      others   ordinary passing marks that differ per student so the ranks spread out
    """
    plan: dict[str, tuple[int, bool] | None] = {}
    for name in subject_names:
        if position in (0, 1):
            plan[name] = (92, False)
        elif position == 2:
            plan[name] = (30, False) if name == "Mathematics" else (78, False)
        elif position == 3:
            if name == "Science":
                plan[name] = (0, True)
            elif name == "Social Studies":
                plan[name] = None
            else:
                plan[name] = (65, False)
        else:
            plan[name] = (60 + (position * 7) % 30, False)
    return plan


async def _seed_phase3(ids: dict) -> None:
    """Holidays, 30 school days of attendance, 10 days of teacher attendance and one Mid Term exam per
    class. Uses the same service functions as the API and skips anything already present, so it is safe
    to run repeatedly."""
    import random

    from app.models import Student as StudentModel
    from app.services.attendance import _today

    async with SessionLocal() as db:
        admin = await db.scalar(select(User).where(User.role == Role.ADMIN, User.is_active.is_(True)).limit(1))
        if admin is None:
            print("No admin user found; skipping Phase 3 sample data.", file=sys.stderr)
            return
        school = await get_school_settings(db)
        school.weekly_off_days = school.weekly_off_days or [7]  # Sunday
        today = _today(school)

        # Seed students are registered "today", so backdate their admission to cover the attendance window.
        cutoff = today - timedelta(days=60)
        for st in (await db.scalars(select(StudentModel).where(StudentModel.admission_date > cutoff))).all():
            st.admission_date = cutoff
        await db.commit()

        # ---- holidays: 3 sample dates inside the window
        if await db.scalar(select(SchoolHoliday.id).limit(1)) is None:
            candidates = _school_days(today, 30, set())
            for offset, name in ((5, "Sample Holiday: Iqbal Day"), (12, "Sample Holiday: Teachers' Day"), (20, "Sample Holiday: Sports Day")):
                await holiday_svc.create_holiday(db, admin, HolidayIn(date=candidates[-offset], name=name), ip=None)
        holidays = {h.date for h in (await db.scalars(select(SchoolHoliday))).all()}
        days = _school_days(today, 30, holidays)

        # ---- student attendance for the last 30 school days
        if await db.scalar(select(Attendance.id).limit(1)) is None:
            rng = random.Random(2026)  # fixed seed -> the same data on every fresh database
            for (class_name, sec_name), section_id in ids["section"].items():
                class_id = ids["class"][class_name]
                roster = (
                    await db.scalars(
                        select(StudentModel)
                        .where(
                            StudentModel.section_id == section_id,
                            StudentModel.is_deleted.is_(False),
                            StudentModel.status == StudentStatus.ACTIVE,
                        )
                        .order_by(StudentModel.roll_no)
                    )
                ).all()
                if not roster:
                    continue
                roster = [(st.id, st.full_name) for st in roster]
                for i, day in enumerate(days):
                    records = []
                    for student_id, full_name in roster:
                        if full_name == LOW_ATTENDANCE_STUDENT:
                            status = AttendanceStatus.ABSENT if i % 3 == 0 else AttendanceStatus.PRESENT  # 66.7%
                        else:
                            status = rng.choices(
                                [AttendanceStatus.PRESENT, AttendanceStatus.LATE, AttendanceStatus.SICK, AttendanceStatus.ABSENT],
                                weights=[90, 5, 3, 2],
                            )[0]
                        records.append(AttendanceRecordIn(student_id=student_id, status=status))
                    await attendance_svc.bulk_save_attendance(
                        db, admin, BulkAttendanceIn(class_id=class_id, section_id=section_id, date=day, records=records), ip=None
                    )

        # ---- teacher attendance: last 10 school days
        if await db.scalar(select(TeacherAttendance.id).limit(1)) is None:
            teacher_ids = [t.id for t in (await db.scalars(select(Teacher).where(Teacher.is_deleted.is_(False)).order_by(Teacher.employee_id))).all()]
            for i, day in enumerate(days[-10:]):
                records = []
                for j, tid in enumerate(teacher_ids):
                    status = TeacherAttendanceStatus.PRESENT
                    if (i, j) == (2, 1):
                        status = TeacherAttendanceStatus.LATE
                    elif (i, j) == (6, 2):
                        status = TeacherAttendanceStatus.LEAVE
                    elif (i, j) == (8, 0):
                        status = TeacherAttendanceStatus.ABSENT
                    records.append(TeacherAttendanceRecordIn(teacher_id=tid, status=status))
                if records:
                    await teacher_attendance_svc.bulk_save(db, admin, BulkTeacherAttendanceIn(date=day, records=records), ip=None)

        # ---- one Mid Term exam per class; Class 1 published, the others left as unpublished drafts
        year = await db.scalar(select(AcademicYear).where(AcademicYear.is_current.is_(True)))
        for class_name, class_id in ids["class"].items():
            if await db.scalar(select(Exam.id).where(Exam.class_id == class_id, Exam.name == "Mid Term")):
                continue
            exam = await exam_svc.create_exam(
                db, admin, ExamIn(name="Mid Term", type=ExamType.MID_TERM, academic_year_id=year.id, class_id=class_id), ip=None
            )
            subjects = await exam_svc.get_exam_subjects(db, exam.id)
            names = [s.subject_name for s in subjects]
            roster = (
                await db.scalars(
                    select(StudentModel)
                    .where(StudentModel.class_id == class_id, StudentModel.is_deleted.is_(False), StudentModel.status == StudentStatus.ACTIVE)
                    .order_by(StudentModel.roll_no)
                )
            ).all()
            roster_ids = [st.id for st in roster]
            for subject in subjects:
                entries = []
                for position, student_id in enumerate(roster_ids):
                    cell = _mark_plan(position, names)[subject.subject_name]
                    if cell is not None:
                        entries.append(
                            MarkSaveIn(student_id=student_id, subject_id=subject.subject_id, obtained_marks=cell[0], is_absent=cell[1])
                        )
                if entries:
                    await exam_svc.save_marks_bulk(
                        db, admin, exam.id, subject.subject_id, None, MarksBulkSaveIn(entries=entries), ip=None
                    )
            if class_name == "Class 1":
                await exam_svc.publish_exam(db, admin, exam.id, ip=None)


async def seed() -> None:
    demo = settings.app_env == "demo"
    sample = demo or settings.seed_sample_data
    shown: list[tuple[str, str, str]] = []  # (role, username, password) to print

    async with SessionLocal() as db:
        # --- school settings (only fill in a brand-new placeholder row) ---
        school = await get_school_settings(db)
        if school.name == "My School":
            school.name = "Greenfield Public School"
            school.slogan = "Learning today, leading tomorrow"
            school.address = "12 Model Town Road, Lahore"
            school.phone = "+92 42 111 000 111"
            school.email = "office@greenfield.example.com"
            school.fee_due_day = 10
            school.late_fine_amount = 200

        # --- current academic year ---
        year = await db.scalar(select(AcademicYear).where(AcademicYear.is_current.is_(True)))
        if year is None:
            label, start, end = _academic_year_bounds(date.today())
            year = await db.scalar(select(AcademicYear).where(AcademicYear.label == label))
            if year is None:
                year = AcademicYear(label=label, start_date=start, end_date=end, is_current=True)
                db.add(year)
            else:
                year.is_current = True
            await db.flush()
        if school.current_academic_year_id is None:
            school.current_academic_year_id = year.id

        # --- users created directly: admin/CEO in demo mode, or the first admin otherwise.
        # Teacher, student and parent demo logins come from real profiles (created below).
        if demo:
            accounts = [
                (role, username, name, settings.seed_demo_password)
                for role, username, name in DEMO_USERS
                if role in (Role.CEO, Role.ADMIN)
            ]
        elif not settings.first_admin_password:
            print("FIRST_ADMIN_PASSWORD is not set; skipping user creation.", file=sys.stderr)
            accounts = []
        else:
            problems = validate_password_strength(settings.first_admin_password)
            if problems:
                print(f"FIRST_ADMIN_PASSWORD {', '.join(problems)}", file=sys.stderr)
                raise SystemExit(1)
            accounts = [
                (Role.ADMIN, settings.first_admin_username.lower(), "Administrator", settings.first_admin_password)
            ]

        created = []
        for role, username, full_name, password in accounts:
            if await db.scalar(select(User.id).where(User.username == username)):
                continue
            db.add(User(username=username, password_hash=hash_password(password), role=role, full_name=full_name))
            created.append(username)
        await db.commit()

    teachers = students = 0
    if sample:
        ids = await _seed_structure()
        teachers, students = await _seed_people(ids, demo, shown)
        await _seed_phase3(ids)

    print(f"Seeded settings + academic year. Users created directly: {', '.join(created) or 'none (already present)'}")
    if sample:
        print(
            f"Sample data: {teachers} teacher(s) and {students} student(s) created this run (already-present ones skipped)."
        )
    _print_credentials(demo, shown)
    await engine.dispose()


def _print_credentials(demo: bool, shown: list[tuple[str, str, str]]) -> None:
    rows: list[tuple[str, str, str]] = []
    if demo:
        rows = [(role.value, username, settings.seed_demo_password) for role, username, _ in DEMO_USERS]
        title = "Demo logins"
    elif shown:
        rows = shown
        title = "Temporary logins (shown once; users must change them at first sign-in)"
    else:
        return
    print(f"\n{title}")
    width = max(len(r[1]) for r in rows + [("", "username", "")])
    print(f"  {'role':<9} {'username':<{width}}  password")
    print(f"  {'-' * 9} {'-' * width}  {'-' * 12}")
    for role, username, password in rows:
        print(f"  {role:<9} {username:<{width}}  {password}")


if __name__ == "__main__":
    asyncio.run(seed())
