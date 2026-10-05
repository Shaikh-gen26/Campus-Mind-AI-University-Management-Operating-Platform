"""CSV-driven development dataset seeder."""

import csv
import os
import re
from datetime import datetime, time
from pathlib import Path

from sqlalchemy import select

from .database import SessionLocal
from .models import (
    Announcement,
    Assignment,
    Attendance,
    Course,
    Event,
    Exam,
    FAQ,
    FAQCategory,
    Grade,
    Notification,
    Student,
    Submission,
    Subject,
    TeacherSubject,
    Timetable,
    User,
)
from .security import hash_password
from .settings import settings


SEED_DATA_DIR = Path(__file__).resolve().parent.parent / "seed_data"


def read_csv(filename: str, required_columns: set[str]):
    path = SEED_DATA_DIR / filename

    if not path.exists():
        raise RuntimeError(f"Missing seed file: {path}")

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        rows = list(csv.DictReader(file))

    if not rows:
        raise RuntimeError(f"{filename} contains no data rows.")

    actual_columns = set(rows[0].keys())
    missing = required_columns - actual_columns

    if missing:
        raise RuntimeError(
            f"{filename} is missing required columns: "
            f"{', '.join(sorted(missing))}"
        )

    return rows


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def parse_datetime(value: str | None):
    if not value:
        return None

    value = value.strip()

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    raise ValueError(f"Invalid datetime: {value}")


def parse_time(value: str):
    return datetime.strptime(value.strip(), "%H:%M:%S").time()


def get_or_create_course(db, row):
    course = db.scalar(
        select(Course).where(Course.code == row["code"])
    )

    if not course:
        course = Course(
            code=row["code"],
            name=row["name"],
        )
        db.add(course)
        db.flush()

    return course


def run():
    if settings.app_env.lower() == "production":
        raise SystemExit(
            "CSV seed data cannot be loaded in production."
        )

    demo_password = (
        settings.demo_password
        or os.getenv("DEMO_PASSWORD")
    )

    if not demo_password or len(demo_password) < 10:
        raise SystemExit(
            "Set DEMO_PASSWORD to a development password "
            "of at least 10 characters."
        )

    # ------------------------------------------------------------------
    # 1. LOAD CSV FILES
    # ------------------------------------------------------------------

    courses_data = read_csv(
        "courses.csv",
        {"code", "name"},
    )

    subjects_data = read_csv(
        "subjects.csv",
        {"course_code", "subject_code", "subject_name"},
    )

    teachers_data = read_csv(
        "teachers.csv",
        {
            "course_code",
            "login",
            "full_name",
            "email",
            "password",
            "subject_1_code",
            "subject_2_code",
        },
    )

    students_data = read_csv(
        "students.csv",
        {
            "course_code",
            "login",
            "student_number",
            "full_name",
            "email",
            "password",
            "year",
        },
    )

    attendance_data = read_csv(
        "attendance.csv",
        {
            "student_number",
            "subject_code",
            "held_on",
            "present",
        },
    )

    grades_data = read_csv(
        "grades.csv",
        {
            "student_number",
            "subject_code",
            "assessment",
            "score",
            "max_score",
            "published",
        },
    )

    assignments_data = read_csv(
        "assignments.csv",
        {
            "course_code",
            "subject_code",
            "title",
            "description",
            "due_at",
            "max_score",
            "published",
            "archived",
            "created_by_login",
        },
    )

    submissions_data = read_csv(
        "submissions.csv",
        {
            "assignment_title",
            "student_number",
            "content",
            "submitted_at",
        },
    )

    exams_data = read_csv(
        "exams.csv",
        {
            "course_code",
            "subject_code",
            "title",
            "starts_at",
            "room",
            "status",
        },
    )

    timetable_data = read_csv(
        "timetable.csv",
        {
            "course_code",
            "subject_code",
            "weekday",
            "starts_at",
            "ends_at",
            "room",
            "faculty",
        },
    )

    announcements_data = read_csv(
        "announcements.csv",
        {
            "title",
            "content",
            "published_at",
            "published",
        },
    )

    events_data = read_csv(
        "events.csv",
        {
            "title",
            "description",
            "starts_at",
            "ends_at",
            "venue",
        },
    )

    faqs_data = read_csv(
        "faqs.csv",
        {
            "category",
            "question",
            "answer",
            "published",
        },
    )

    notifications_data = read_csv(
        "notifications.csv",
        {
            "student_number",
            "title",
            "message",
            "created_at",
            "read",
        },
    )

    print("CSV files loaded successfully.")

    # ------------------------------------------------------------------
    # 2. DATABASE
    # ------------------------------------------------------------------

    with SessionLocal() as db:

        # --------------------------------------------------------------
        # SUPER ADMIN
        # --------------------------------------------------------------

        admin = db.scalar(
            select(User).where(User.login == "admin")
        )

        if not admin:
            admin = User(
                login="admin",
                email="admin@campusmind.local",
                full_name="University Administrator",
                password_hash=hash_password(demo_password),
                role="super_admin",
                active=True,
            )
            db.add(admin)
            db.flush()

        # --------------------------------------------------------------
        # COURSES
        # --------------------------------------------------------------

        course_map = {}

        for row in courses_data:
            course = get_or_create_course(db, row)
            course_map[row["code"]] = course

        db.flush()

        print(f"Courses imported: {len(course_map)}")

        # --------------------------------------------------------------
        # SUBJECTS
        # --------------------------------------------------------------

        subject_map = {}

        for row in subjects_data:
            course_code = row["course_code"]
            subject_code = row["subject_code"]

            if course_code not in course_map:
                raise RuntimeError(
                    f"Subject {subject_code} references "
                    f"unknown course {course_code}."
                )

            subject = db.scalar(
                select(Subject).where(
                    Subject.code == subject_code
                )
            )

            if not subject:
                subject = Subject(
                    code=subject_code,
                    name=row["subject_name"],
                    course_id=course_map[course_code].id,
                )
                db.add(subject)
                db.flush()

            subject_map[subject_code] = subject

        print(f"Subjects imported: {len(subject_map)}")

        # --------------------------------------------------------------
        # TEACHERS / COURSE ADMINS
        # --------------------------------------------------------------

        teacher_map = {}

        for row in teachers_data:
            course_code = row["course_code"]

            if course_code not in course_map:
                raise RuntimeError(
                    f"Teacher {row['login']} references "
                    f"unknown course {course_code}."
                )

            user = db.scalar(
                select(User).where(
                    User.login == row["login"]
                )
            )

            if not user:
                user = User(
                    login=row["login"],
                    email=row["email"],
                    full_name=row["full_name"],
                    password_hash=hash_password(row["password"]),
                    role="course_admin",
                    active=True,
                    course_id=course_map[course_code].id,
                )
                db.add(user)
                db.flush()
            else:
                user.email = row["email"]
                user.full_name = row["full_name"]
                user.role = "course_admin"
                user.course_id = course_map[course_code].id

            teacher_map[row["login"]] = user

            subject_codes = [
                row["subject_1_code"],
                row["subject_2_code"],
            ]

            if subject_codes[0] == subject_codes[1]:
                raise RuntimeError(
                    f"Teacher {row['login']} has the same "
                    f"subject assigned twice."
                )

            for subject_code in subject_codes:
                subject = subject_map.get(subject_code)

                if not subject:
                    raise RuntimeError(
                        f"Teacher {row['login']} references "
                        f"unknown subject {subject_code}."
                    )

                if subject.course_id != course_map[course_code].id:
                    raise RuntimeError(
                        f"Teacher {row['login']} has subject "
                        f"{subject_code} outside course {course_code}."
                    )

                existing = db.scalar(
                    select(TeacherSubject).where(
                        TeacherSubject.teacher_id == user.id,
                        TeacherSubject.subject_id == subject.id,
                    )
                )

                if not existing:
                    db.add(
                        TeacherSubject(
                            teacher_id=user.id,
                            subject_id=subject.id,
                        )
                    )

        db.flush()

        print(f"Teachers imported: {len(teacher_map)}")

        # --------------------------------------------------------------
        # STUDENTS
        # --------------------------------------------------------------

        student_map = {}
        student_user_map = {}

        for row in students_data:
            course_code = row["course_code"]

            if course_code not in course_map:
                raise RuntimeError(
                    f"Student {row['student_number']} references "
                    f"unknown course {course_code}."
                )

            student = db.scalar(
                select(Student).where(
                    Student.student_number == row["student_number"]
                )
            )

            if not student:
                student = Student(
                    student_number=row["student_number"],
                    full_name=row["full_name"],
                    email=row["email"],
                    year=int(row["year"]),
                    course_id=course_map[course_code].id,
                )
                db.add(student)
                db.flush()
            else:
                student.full_name = row["full_name"]
                student.email = row["email"]
                student.year = int(row["year"])
                student.course_id = course_map[course_code].id

            student_map[row["student_number"]] = student

            user = db.scalar(
                select(User).where(
                    User.login == row["login"]
                )
            )

            if not user:
                user = User(
                    login=row["login"],
                    email=row["email"],
                    full_name=row["full_name"],
                    password_hash=hash_password(row["password"]),
                    role="student",
                    active=True,
                    student_id=student.id,
                )
                db.add(user)
                db.flush()
            else:
                user.email = row["email"]
                user.full_name = row["full_name"]
                user.role = "student"
                user.student_id = student.id

            student_user_map[row["student_number"]] = user

        print(f"Students imported: {len(student_map)}")

        # --------------------------------------------------------------
        # ATTENDANCE
        # --------------------------------------------------------------

        attendance_count = 0

        for row in attendance_data:
            student = student_map.get(row["student_number"])
            subject = subject_map.get(row["subject_code"])

            if not student:
                raise RuntimeError(
                    f"Attendance references unknown student "
                    f"{row['student_number']}."
                )

            if not subject:
                raise RuntimeError(
                    f"Attendance references unknown subject "
                    f"{row['subject_code']}."
                )

            db.add(
                Attendance(
                    student_id=student.id,
                    subject_id=subject.id,
                    held_on=datetime.strptime(
                        row["held_on"],
                        "%Y-%m-%d",
                    ).date(),
                    present=parse_bool(row["present"]),
                )
            )

            attendance_count += 1

        print(f"Attendance imported: {attendance_count}")

        # --------------------------------------------------------------
        # GRADES
        # --------------------------------------------------------------

        grade_count = 0

        for row in grades_data:
            student = student_map.get(row["student_number"])
            subject = subject_map.get(row["subject_code"])

            if not student:
                raise RuntimeError(
                    f"Grade references unknown student "
                    f"{row['student_number']}."
                )

            if not subject:
                raise RuntimeError(
                    f"Grade references unknown subject "
                    f"{row['subject_code']}."
                )

            db.add(
                Grade(
                    student_id=student.id,
                    subject_id=subject.id,
                    assessment=row["assessment"],
                    score=float(row["score"]),
                    max_score=float(row["max_score"]),
                    published=parse_bool(row["published"]),
                )
            )

            grade_count += 1

        print(f"Grades imported: {grade_count}")

        # --------------------------------------------------------------
        # ASSIGNMENTS
        # --------------------------------------------------------------

        assignment_map = {}

        for row in assignments_data:
            subject = subject_map.get(row["subject_code"])
            teacher = teacher_map.get(row["created_by_login"])

            if not subject:
                raise RuntimeError(
                    f"Assignment references unknown subject "
                    f"{row['subject_code']}."
                )

            if not teacher:
                raise RuntimeError(
                    f"Assignment references unknown teacher "
                    f"{row['created_by_login']}."
                )

            if teacher.course_id != subject.course_id:
                raise RuntimeError(
                    f"Assignment creator {teacher.login} is outside "
                    f"subject {subject.code}'s course."
                )

            assignment = db.scalar(
                select(Assignment).where(
                    Assignment.title == row["title"],
                    Assignment.subject_id == subject.id,
                )
            )

            if not assignment:
                assignment = Assignment(
                    title=row["title"],
                    description=row["description"],
                    due_at=parse_datetime(row["due_at"]),
                    max_score=float(row["max_score"]),
                    published=parse_bool(row["published"]),
                    archived=parse_bool(row["archived"]),
                    subject_id=subject.id,
                    created_by=teacher.id,
                )
                db.add(assignment)
                db.flush()

            assignment_key = (
                row["title"],
                row["subject_code"],
            )

            assignment_map[assignment_key] = assignment

        print(f"Assignments imported: {len(assignment_map)}")

        # --------------------------------------------------------------
        # SUBMISSIONS
        # --------------------------------------------------------------

        submission_count = 0

        
        
        
        for row in submissions_data:
            student = student_map.get(row["student_number"])

            if not student:
                raise RuntimeError(
                    f"Submission references unknown student "
                    f"{row['student_number']}."
                )

            # Submission titles and assignment titles use different naming
            # conventions in the CSV files. Resolve by:
            #   1. student's course
            #   2. assignment number
            #
            # Example:
            #   Submission: "Assignment 1 — Unit 1 and foundational concepts"
            #   Assignment: "Data Structures and Algorithms - Assignment 1"

            
            
            
            
            submission_title = row["assignment_title"].strip()
            submission_content = row["content"].strip()

            # Extract assignment number from the submission title.
            assignment_number_match = re.search(
                r"assignment\s+(\d+)",
                submission_title,
                re.IGNORECASE,
            )

            if not assignment_number_match:
                raise RuntimeError(
                    f"Could not determine assignment number from submission: "
                    f"{row['assignment_title']}"
                )

            assignment_number = int(assignment_number_match.group(1))

            # Extract the subject code from the submission content.
            # Example:
            # "...questions in CSE301."
            
            
            
            
            # Extract the subject code from the submission content.
# If the current submission content does not contain one,
# infer it from the other submissions made by the same student.
            subject_code_match = re.search(
                r"\b([A-Z]{2,10}\d{3})\b",
                submission_content,
                re.IGNORECASE,
            )

            if subject_code_match:
                subject_code = subject_code_match.group(1).upper()
            else:
                student_subject_codes = set()

                for other_row in submissions_data:
                    if other_row["student_number"] != row["student_number"]:
                        continue

                    other_match = re.search(
                        r"\b([A-Z]{2,10}\d{3})\b",
                        other_row["content"],
                        re.IGNORECASE,
                    )

                    if other_match:
                        student_subject_codes.add(
                            other_match.group(1).upper()
                        )

                if len(student_subject_codes) == 1:
                    subject_code = next(iter(student_subject_codes))
                else:
                    raise RuntimeError(
                        f"Could not determine subject code from submission: "
                        f"{row['content']}"
                    )
                        
            
            
            
            student_course = db.get(Course, student.course_id)

            if not student_course:
                raise RuntimeError(
                    f"Could not determine course for student "
                    f"{row['student_number']}."
                )
            
            
            subject = db.scalar(
                select(Subject).where(Subject.code == subject_code)
            )

            if not subject:
                raise RuntimeError(
                    f"Submission references unknown subject: {subject_code}"
                )

            # Make sure the subject belongs to the student's course.
            if subject.course_id != student_course.id:
                raise RuntimeError(
                    f"Submission subject {subject_code} does not belong to "
                    f"student course {student_course.code}."
                )

            matching = [
                assignment
                for assignment in assignment_map.values()
                if assignment.subject_id == subject.id
                and re.search(
                    rf"assignment\s+{assignment_number}\b",
                    assignment.title,
                    re.IGNORECASE,
                )
            ]

            if not matching:
                raise RuntimeError(
                    f"Could not resolve submission assignment: "
                    f"{row['assignment_title']} "
                    f"for subject {subject_code}"
                )

            if len(matching) > 1:
                raise RuntimeError(
                    f"Multiple assignments matched submission: "
                    f"{row['assignment_title']} "
                    f"for subject {subject_code}"
                )

            assignment = matching[0]
        
        
            

            existing = db.scalar(
                select(Submission).where(
                    Submission.assignment_id == assignment.id,
                    Submission.student_id == student.id,
                )
            )

            if not existing:
                db.add(
                    Submission(
                        assignment_id=assignment.id,
                        student_id=student.id,
                        content=row["content"],
                        submitted_at=parse_datetime(
                            row["submitted_at"]
                        ),
                    )
                )
                submission_count += 1

        print(f"Submissions imported: {submission_count}")

        # --------------------------------------------------------------
        # EXAMS
        # --------------------------------------------------------------

        exam_count = 0

        for row in exams_data:
            subject = subject_map.get(row["subject_code"])

            if not subject:
                raise RuntimeError(
                    f"Exam references unknown subject "
                    f"{row['subject_code']}."
                )

            existing = db.scalar(
                select(Exam).where(
                    Exam.subject_id == subject.id,
                    Exam.title == row["title"],
                )
            )

            if not existing:
                db.add(
                    Exam(
                        subject_id=subject.id,
                        title=row["title"],
                        starts_at=parse_datetime(row["starts_at"]),
                        room=row["room"],
                        status=row["status"],
                    )
                )
                exam_count += 1

        print(f"Exams imported: {exam_count}")

        # --------------------------------------------------------------
        # TIMETABLE
        # --------------------------------------------------------------

        timetable_count = 0

        weekday_map = {
            "Monday": 0,
            "Tuesday": 1,
            "Wednesday": 2,
            "Thursday": 3,
            "Friday": 4,
            "Saturday": 5,
            "Sunday": 6,
        }

        for row in timetable_data:
            subject = subject_map.get(row["subject_code"])

            if not subject:
                raise RuntimeError(
                    f"Timetable references unknown subject "
                    f"{row['subject_code']}."
                )

            weekday_value = row["weekday"]

            if weekday_value in weekday_map:
                weekday_value = weekday_map[weekday_value]
            else:
                weekday_value = int(weekday_value)

            existing = db.scalar(
                select(Timetable).where(
                    Timetable.subject_id == subject.id,
                    Timetable.weekday == weekday_value,
                    Timetable.starts_at == parse_time(row["starts_at"]),
                )
            )

            if not existing:
                db.add(
                    Timetable(
                        subject_id=subject.id,
                        weekday=weekday_value,
                        starts_at=parse_time(row["starts_at"]),
                        ends_at=parse_time(row["ends_at"]),
                        room=row["room"],
                        faculty=row["faculty"],
                    )
                )
                timetable_count += 1

        print(f"Timetable records imported: {timetable_count}")

        # --------------------------------------------------------------
        # FAQS
        # --------------------------------------------------------------

        faq_category_map = {}

        for row in faqs_data:
            category_name = row["category"].strip()

            category = faq_category_map.get(category_name)

            if not category:
                category = db.scalar(
                    select(FAQCategory).where(
                        FAQCategory.name == category_name
                    )
                )

            if not category:
                category = FAQCategory(name=category_name)
                db.add(category)
                db.flush()

            faq_category_map[category_name] = category

            existing = db.scalar(
                select(FAQ).where(
                    FAQ.question == row["question"]
                )
            )

            if not existing:
                db.add(
                    FAQ(
                        category_id=category.id,
                        question=row["question"],
                        answer=row["answer"],
                        published=parse_bool(row["published"]),
                    )
                )

        print(f"FAQs imported: {len(faqs_data)}")

        # --------------------------------------------------------------
        # ANNOUNCEMENTS
        # --------------------------------------------------------------

        announcement_count = 0

        for row in announcements_data:
            existing = db.scalar(
                select(Announcement).where(
                    Announcement.title == row["title"]
                )
            )

            if not existing:
                db.add(
                    Announcement(
                        title=row["title"],
                        body=row["content"],
                        published_at=parse_datetime(
                            row["published_at"]
                        ),
                        published=parse_bool(row["published"]),
                        author_id=admin.id,
                    )
                )
                announcement_count += 1

        print(
            f"Announcements imported: {announcement_count}"
        )

        # --------------------------------------------------------------
        # EVENTS
        # --------------------------------------------------------------

        event_count = 0

        for row in events_data:
            existing = db.scalar(
                select(Event).where(
                    Event.title == row["title"]
                )
            )

            if not existing:
                db.add(
                    Event(
                        title=row["title"],
                        description=row["description"],
                        starts_at=parse_datetime(row["starts_at"]),
                        location=row["venue"],
                    )
                )
                event_count += 1

        print(f"Events imported: {event_count}")

        # --------------------------------------------------------------
        # NOTIFICATIONS
        # --------------------------------------------------------------

        notification_count = 0

        for row in notifications_data:
            user = student_user_map.get(
                row["student_number"]
            )

            if not user:
                raise RuntimeError(
                    f"Notification references unknown student "
                    f"{row['student_number']}."
                )

            existing = db.scalar(
                select(Notification).where(
                    Notification.user_id == user.id,
                    Notification.title == row["title"],
                    Notification.created_at
                    == parse_datetime(row["created_at"]),
                )
            )

            if not existing:
                db.add(
                    Notification(
                        user_id=user.id,
                        title=row["title"],
                        body=row["message"],
                        read=parse_bool(row["read"]),
                        created_at=parse_datetime(
                            row["created_at"]
                        ),
                    )
                )
                notification_count += 1

        print(
            f"Notifications imported: {notification_count}"
        )

        # --------------------------------------------------------------
        # FINAL COMMIT
        # --------------------------------------------------------------

        db.commit()

    print()
    print("========================================")
    print("CSV SEED COMPLETE")
    print("========================================")
    print(f"Courses:        {len(course_map)}")
    print(f"Subjects:       {len(subject_map)}")
    print(f"Teachers:       {len(teacher_map)}")
    print(f"Students:       {len(student_map)}")
    print(f"Attendance:     {attendance_count}")
    print(f"Grades:         {grade_count}")
    print(f"Assignments:    {len(assignment_map)}")
    print(f"Submissions:    {submission_count}")
    print(f"Exams:          {exam_count}")
    print(f"Timetable:      {timetable_count}")
    print(f"Announcements:  {announcement_count}")
    print(f"Events:         {event_count}")
    print(f"FAQs:           {len(faqs_data)}")
    print(f"Notifications:  {notification_count}")
    print("========================================")


if __name__ == "__main__":
    run()
    
