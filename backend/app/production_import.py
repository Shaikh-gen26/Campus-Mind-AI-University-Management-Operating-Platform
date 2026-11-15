import argparse
import csv
import re
from datetime import datetime, date, time
from pathlib import Path

from sqlalchemy import select, func

from .database import SessionLocal, engine
from .models import (
    Announcement, Assignment, Attendance, Course, Event, Exam, FAQ,
    FAQCategory, Grade, Notification, Student, Submission, Subject,
    TeacherSubject, Timetable, User,
)
from .security import hash_password
from .settings import settings


DATA_DIR = Path(__file__).resolve().parent.parent / "seed_data"

EXPECTED_COUNTS = {
    "courses.csv": 6,
    "subjects.csv": 36,
    "teachers.csv": 18,
    "students.csv": 360,
    "attendance.csv": 43200,
    "grades.csv": 6480,
    "assignments.csv": 108,
    "submissions.csv": 1080,
    "exams.csv": 36,
    "timetable.csv": 36,
    "faqs.csv": 45,
    "announcements.csv": 20,
    "events.csv": 15,
    "notifications.csv": 30,
}


def read_csv(filename):
    path = DATA_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Required CSV file is missing: {filename}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError(f"{filename} has no header row.")
        rows = list(reader)

    if len(rows) != EXPECTED_COUNTS[filename]:
        raise ValueError(
            f"{filename}: expected {EXPECTED_COUNTS[filename]} rows, "
            f"found {len(rows)}."
        )

    for row_number, row in enumerate(rows, start=2):
        if any(value is None for value in row.values()):
            raise ValueError(
                f"{filename} contains a malformed row at line {row_number}."
            )

    return rows


def required(row, column, filename):
    value = (row.get(column) or "").strip()
    if not value:
        raise ValueError(f"{filename}: missing required value in column '{column}'.")
    return value


def parse_bool(value):
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def parse_datetime(value, filename, column):
    value = required({"value": value}, "value", filename)
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"{filename}: invalid datetime in '{column}'.")


def parse_date(value, filename, column):
    value = required({"value": value}, "value", filename)
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{filename}: invalid date in '{column}'.")


def parse_time(value, filename, column):
    value = required({"value": value}, "value", filename)
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            pass
    raise ValueError(f"{filename}: invalid time in '{column}'.")


def parse_int(value, filename, column):
    value = required({"value": value}, "value", filename)
    try:
        number = int(value)
    except ValueError:
        raise ValueError(f"{filename}: '{column}' must contain an integer.")
    return number


def ensure_production_database():
    if settings.app_env.lower() != "production":
        raise RuntimeError("Importer requires APP_ENV=production.")

    if engine.dialect.name != "postgresql":
        raise RuntimeError("Importer only permits a PostgreSQL database.")


def ensure_tables_empty(session):
    tables = [
        Course, Subject, User, Student, TeacherSubject, Attendance,
        Assignment, Submission, Grade, Timetable, Exam, Announcement,
        Event, Notification, FAQCategory, FAQ,
    ]

    occupied = []
    for model in tables:
        count = session.scalar(select(func.count()).select_from(model))
        if count:
            occupied.append(model.__tablename__)

    if occupied:
        raise RuntimeError(
            "Import stopped because these application tables are not empty: "
            + ", ".join(sorted(occupied))
        )


def unique_values(rows, key, filename):
    values = [required(row, key, filename) for row in rows]
    if len(values) != len(set(values)):
        raise ValueError(f"{filename}: duplicate values found in '{key}'.")
    return values


def load_all_csv():
    return {
        filename: read_csv(filename)
        for filename in EXPECTED_COUNTS
    }


def main():
    parser = argparse.ArgumentParser(
        description="Safely import Campus Mind production CSV data."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    apply_changes = args.apply
    ensure_production_database()

    session = SessionLocal()

    try:
        ensure_tables_empty(session)
        data = load_all_csv()

        courses, subjects, students, teachers = import_core_records(
            session, data
        )

        assignments_by_title = import_academic_records(
            session, data, courses, subjects, students, teachers
        )

        import_submissions(
            session, data, subjects, students, assignments_by_title
        )

        import_schedules(session, data, courses, subjects)
        import_campus_content(session, data, students)

        session.flush()

        print("Production environment: PASSED")
        print("PostgreSQL connection: PASSED")
        print("Initially empty tables: PASSED")
        print("CSV validation: PASSED")
        print("Courses:", len(courses))
        print("Subjects:", len(subjects))
        print("Students:", len(students))
        print("Course administrators:", len(teachers))
        print("Assignments:", len(data["assignments.csv"]))
        print("Submissions:", len(data["submissions.csv"]))
        print("Attendance:", len(data["attendance.csv"]))
        print("Grades:", len(data["grades.csv"]))
        print("Exams:", len(data["exams.csv"]))
        print("Timetable entries:", len(data["timetable.csv"]))
        print("FAQs:", len(data["faqs.csv"]))
        print("Announcements:", len(data["announcements.csv"]))
        print("Events:", len(data["events.csv"]))
        print("Notifications:", len(data["notifications.csv"]))

        if apply_changes:
            session.commit()
            print("PRODUCTION IMPORT COMMITTED.")
        else:
            session.rollback()
            print("DRY RUN PASSED. All database changes rolled back.")
            print("No production records were committed.")

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def import_core_records(session, data):
    courses = {}
    subjects = {}
    students = {}
    teachers = {}

    # Insert courses in one batch.
    for row in data["courses.csv"]:
        code = required(row, "code", "courses.csv")
        courses[code] = Course(
            code=code,
            name=required(row, "name", "courses.csv"),
        )

    session.add_all(list(courses.values()))
    session.flush()

    # Insert subjects in one batch.
    for row in data["subjects.csv"]:
        course_code = required(row, "course_code", "subjects.csv")
        subject_code = required(row, "subject_code", "subjects.csv")

        if course_code not in courses:
            raise ValueError("A subject references an unknown course.")

        subjects[subject_code] = Subject(
            code=subject_code,
            name=required(row, "subject_name", "subjects.csv"),
            course_id=courses[course_code].id,
        )

    session.add_all(list(subjects.values()))
    session.flush()

    # Create all student records before creating their login accounts.
    student_rows = []

    for row in data["students.csv"]:
        course_code = required(row, "course_code", "students.csv")

        if course_code not in courses:
            raise ValueError("A student references an unknown course.")

        student = Student(
            student_number=required(row, "student_number", "students.csv"),
            full_name=required(row, "full_name", "students.csv"),
            email=required(row, "email", "students.csv"),
            year=parse_int(row["year"], "students.csv", "year"),
            course_id=courses[course_code].id,
        )

        student_rows.append((row, student))

    session.add_all([student for _, student in student_rows])
    session.flush()

    # Hash passwords and prepare student accounts.
    student_accounts = []

    for row, student in student_rows:
        login = required(row, "login", "students.csv")
        password = required(row, "password", "students.csv")

        account = User(
            login=login,
            email=student.email,
            full_name=student.full_name,
            password_hash=hash_password(password),
            role="student",
            active=True,
            token_version=0,
            course_id=student.course_id,
            student_id=student.id,
        )

        student_accounts.append(account)
        students[student.student_number] = {
            "student": student,
            "user": account,
        }

    session.add_all(student_accounts)

    # Prepare course administrator accounts.
    teacher_rows = []

    for row in data["teachers.csv"]:
        course_code = required(row, "course_code", "teachers.csv")

        if course_code not in courses:
            raise ValueError("A teacher references an unknown course.")

        teacher = User(
            login=required(row, "login", "teachers.csv"),
            email=required(row, "email", "teachers.csv"),
            full_name=required(row, "full_name", "teachers.csv"),
            password_hash=hash_password(
                required(row, "password", "teachers.csv")
            ),
            role="course_admin",
            active=True,
            token_version=0,
            course_id=courses[course_code].id,
            student_id=None,
        )

        teacher_rows.append((row, teacher))

    session.add_all([teacher for _, teacher in teacher_rows])
    session.flush()

    # Create teacher-subject relationships.
    teacher_subject_links = []

    for row, teacher in teacher_rows:
        teachers[teacher.login] = teacher

        for column in ("subject_1_code", "subject_2_code"):
            subject_code = required(row, column, "teachers.csv")
            subject = subjects.get(subject_code)

            if subject is None:
                raise ValueError("A teacher references an unknown subject.")

            if subject.course_id != teacher.course_id:
                raise ValueError(
                    "A teacher is assigned a subject from another course."
                )

            teacher_subject_links.append(
                TeacherSubject(
                    teacher_id=teacher.id,
                    subject_id=subject.id,
                )
            )

    session.add_all(teacher_subject_links)
    session.flush()

    return courses, subjects, students, teachers


def import_academic_records(session, data, courses, subjects, students, teachers):
    # Attendance
    for row in data["attendance.csv"]:
        student_number = required(row, "student_number", "attendance.csv")
        subject_code = required(row, "subject_code", "attendance.csv")

        if student_number not in students:
            raise ValueError("Attendance references an unknown student.")
        if subject_code not in subjects:
            raise ValueError("Attendance references an unknown subject.")

        student = students[student_number]["student"]
        subject = subjects[subject_code]

        if student.course_id != subject.course_id:
            raise ValueError("Attendance student and subject courses do not match.")

        session.add(
            Attendance(
                student_id=student.id,
                subject_id=subject.id,
                held_on=parse_date(row["held_on"], "attendance.csv", "held_on"),
                present=parse_bool(row["present"]),
            )
        )

    # Grades
    for row in data["grades.csv"]:
        student_number = required(row, "student_number", "grades.csv")
        subject_code = required(row, "subject_code", "grades.csv")

        if student_number not in students:
            raise ValueError("A grade references an unknown student.")
        if subject_code not in subjects:
            raise ValueError("A grade references an unknown subject.")

        student = students[student_number]["student"]
        subject = subjects[subject_code]

        if student.course_id != subject.course_id:
            raise ValueError("Grade student and subject courses do not match.")

        score = parse_int(row["score"], "grades.csv", "score")
        max_score = parse_int(row["max_score"], "grades.csv", "max_score")

        if max_score <= 0 or score < 0 or score > max_score:
            raise ValueError("A grade contains an invalid score.")

        session.add(
            Grade(
                student_id=student.id,
                subject_id=subject.id,
                assessment=required(row, "assessment", "grades.csv"),
                score=score,
                max_score=max_score,
                published=parse_bool(row["published"]),
            )
        )

    # Assignments
    assignments_by_title = {}

    for row in data["assignments.csv"]:
        course_code = required(row, "course_code", "assignments.csv")
        subject_code = required(row, "subject_code", "assignments.csv")
        creator_login = required(row, "created_by_login", "assignments.csv")

        if course_code not in courses:
            raise ValueError("An assignment references an unknown course.")
        if subject_code not in subjects:
            raise ValueError("An assignment references an unknown subject.")
        if creator_login not in teachers:
            raise ValueError("An assignment references an unknown teacher.")

        subject = subjects[subject_code]
        teacher = teachers[creator_login]

        if subject.course_id != courses[course_code].id:
            raise ValueError("Assignment subject does not belong to its course.")
        if teacher.course_id != courses[course_code].id:
            raise ValueError("Assignment creator does not belong to its course.")

        max_score = parse_int(row["max_score"], "assignments.csv", "max_score")
        if max_score <= 0:
            raise ValueError("An assignment has an invalid maximum score.")

        assignment = Assignment(
            title=required(row, "title", "assignments.csv"),
            description=(row.get("description") or "").strip(),
            due_at=parse_datetime(row["due_at"], "assignments.csv", "due_at"),
            max_score=max_score,
            published=parse_bool(row["published"]),
            archived=parse_bool(row["archived"]),
            subject_id=subject.id,
            created_by=teacher.id,
        )
        session.add(assignment)

        title = assignment.title
        assignments_by_title.setdefault(title, []).append(assignment)

    session.flush()
    return assignments_by_title


def import_submissions(session, data, subjects, students, assignments_by_title):
    submission_rows = data["submissions.csv"]

    # Precompute subject codes found in each student's submissions.
    student_subject_codes = {}

    for row in submission_rows:
        student_number = required(row, "student_number", "submissions.csv")
        content = required(row, "content", "submissions.csv")

        match = re.search(r"\b([A-Z]{2,10}\d{3})\b", content, re.IGNORECASE)

        if match:
            student_subject_codes.setdefault(student_number, set()).add(
                match.group(1).upper()
            )

    assignment_list = [
        assignment
        for assignments in assignments_by_title.values()
        for assignment in assignments
    ]

    for row in submission_rows:
        student_number = required(row, "student_number", "submissions.csv")
        submission_title = required(row, "assignment_title", "submissions.csv")
        content = required(row, "content", "submissions.csv")

        if student_number not in students:
            raise ValueError("A submission references an unknown student.")

        number_match = re.search(
            r"assignment\s+(\d+)",
            submission_title,
            re.IGNORECASE,
        )

        if not number_match:
            raise ValueError("A submission has an unrecognizable assignment number.")

        assignment_number = int(number_match.group(1))

        subject_match = re.search(
            r"\b([A-Z]{2,10}\d{3})\b",
            content,
            re.IGNORECASE,
        )

        if subject_match:
            subject_code = subject_match.group(1).upper()
        else:
            possible_codes = student_subject_codes.get(student_number, set())

            if len(possible_codes) != 1:
                raise ValueError(
                    "A submission's subject code cannot be determined uniquely."
                )

            subject_code = next(iter(possible_codes))

        subject = subjects.get(subject_code)
        student = students[student_number]["student"]

        if subject is None:
            raise ValueError("A submission references an unknown subject.")

        if subject.course_id != student.course_id:
            raise ValueError("A submission subject does not belong to its student.")

        matching = [
            assignment
            for assignment in assignment_list
            if assignment.subject_id == subject.id
            and re.search(
                rf"assignment\s+{assignment_number}\b",
                assignment.title,
                re.IGNORECASE,
            )
        ]

        if len(matching) != 1:
            raise ValueError(
                "A submission does not resolve to exactly one assignment."
            )

        session.add(
            Submission(
                assignment_id=matching[0].id,
                student_id=student.id,
                content=content,
                submitted_at=parse_datetime(
                    row["submitted_at"],
                    "submissions.csv",
                    "submitted_at",
                ),
            )
        )

    session.flush()


def import_schedules(session, data, courses, subjects):
    weekday_map = {
        "Monday": 0,
        "Tuesday": 1,
        "Wednesday": 2,
        "Thursday": 3,
        "Friday": 4,
        "Saturday": 5,
        "Sunday": 6,
    }

    # Exams
    for row in data["exams.csv"]:
        course_code = required(row, "course_code", "exams.csv")
        subject_code = required(row, "subject_code", "exams.csv")

        if course_code not in courses or subject_code not in subjects:
            raise ValueError("An exam references an unknown course or subject.")

        subject = subjects[subject_code]

        if subject.course_id != courses[course_code].id:
            raise ValueError("An exam subject does not belong to its course.")

        session.add(
            Exam(
                subject_id=subject.id,
                title=required(row, "title", "exams.csv"),
                starts_at=parse_datetime(
                    row["starts_at"], "exams.csv", "starts_at"
                ),
                room=required(row, "room", "exams.csv"),
                status=required(row, "status", "exams.csv"),
            )
        )

    # Timetable
    for row in data["timetable.csv"]:
        course_code = required(row, "course_code", "timetable.csv")
        subject_code = required(row, "subject_code", "timetable.csv")

        if course_code not in courses or subject_code not in subjects:
            raise ValueError("A timetable row references an unknown course or subject.")

        subject = subjects[subject_code]

        if subject.course_id != courses[course_code].id:
            raise ValueError("A timetable subject does not belong to its course.")

        weekday_text = required(row, "weekday", "timetable.csv")

        if weekday_text in weekday_map:
            weekday = weekday_map[weekday_text]
        else:
            try:
                weekday = int(weekday_text)
            except ValueError:
                raise ValueError("A timetable row has an invalid weekday.")

        if weekday < 0 or weekday > 6:
            raise ValueError("A timetable weekday must be between 0 and 6.")

        starts_at = parse_time(
            row["starts_at"], "timetable.csv", "starts_at"
        )
        ends_at = parse_time(
            row["ends_at"], "timetable.csv", "ends_at"
        )

        if ends_at <= starts_at:
            raise ValueError("A timetable end time must be after its start time.")

        session.add(
            Timetable(
                subject_id=subject.id,
                weekday=weekday,
                starts_at=starts_at,
                ends_at=ends_at,
                room=required(row, "room", "timetable.csv"),
                faculty=required(row, "faculty", "timetable.csv"),
            )
        )

    session.flush()


def import_campus_content(session, data, students):
    # FAQ categories and FAQs
    categories = {}

    for row in data["faqs.csv"]:
        category_name = required(row, "category", "faqs.csv")

        if category_name not in categories:
            category = FAQCategory(name=category_name)
            session.add(category)
            session.flush()
            categories[category_name] = category

        session.add(
            FAQ(
                category_id=categories[category_name].id,
                question=required(row, "question", "faqs.csv"),
                answer=required(row, "answer", "faqs.csv"),
                published=parse_bool(row["published"]),
                featured=False,
            )
        )

    # Announcements
    for row in data["announcements.csv"]:
        session.add(
            Announcement(
                title=required(row, "title", "announcements.csv"),
                body=required(row, "content", "announcements.csv"),
                published_at=parse_datetime(
                    row["published_at"],
                    "announcements.csv",
                    "published_at",
                ),
                published=parse_bool(row["published"]),
                course_id=None,
                author_id=None,
            )
        )

    # Events
    for row in data["events.csv"]:
        session.add(
            Event(
                title=required(row, "title", "events.csv"),
                description=(row.get("description") or "").strip(),
                starts_at=parse_datetime(
                    row["starts_at"], "events.csv", "starts_at"
                ),
                location=required(row, "venue", "events.csv"),
            )
        )

    # Notifications
    for row in data["notifications.csv"]:
        student_number = required(
            row, "student_number", "notifications.csv"
        )

        if student_number not in students:
            raise ValueError("A notification references an unknown student.")

        student_user = students[student_number]["user"]

        session.add(
            Notification(
                user_id=student_user.id,
                title=required(row, "title", "notifications.csv"),
                body=required(row, "message", "notifications.csv"),
                notification_type="general",
                course_id=student_user.course_id,
                read=parse_bool(row["read"]),
                created_at=parse_datetime(
                    row["created_at"],
                    "notifications.csv",
                    "created_at",
                ),
            )
        )

    session.flush()

if __name__ == "__main__":
    main()
