"""Idempotent seed: school settings, current academic year, users, and (demo/sample mode) a small school.

  python -m scripts.seed

APP_ENV=demo          -> demo logins for every role + sample school data (password = SEED_DEMO_PASSWORD)
SEED_SAMPLE_DATA=true -> sample school data outside demo mode (random temporary passwords are printed once)
otherwise             -> only the first admin from FIRST_ADMIN_USERNAME / FIRST_ADMIN_PASSWORD

Safe to run repeatedly: existing rows are never modified. Students and teachers are created through the
same service functions the API uses, so seeding exercises the real registration transaction."""

import asyncio
import sys
from datetime import date

from sqlalchemy import select

from app.core.config import settings
from app.core.demo import DEMO_USERS
from app.core.errors import AppError
from app.core.security import hash_password, validate_password_strength
from app.db.session import SessionLocal, engine
from app.models import (
    AcademicYear,
    ClassSubject,
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
from app.schemas.students import StudentCreate
from app.schemas.teachers import TeacherCreate
from app.services import students as student_svc
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
