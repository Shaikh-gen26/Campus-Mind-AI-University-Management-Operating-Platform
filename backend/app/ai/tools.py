"""
Campus Mind AI data tools.

These functions retrieve and calculate academic information from the
database. They do not generate natural-language answers.

Important architecture rule:

    Database = source of truth
    Python = calculations
    AI = explanation/recommendation
"""
from sqlalchemy import case, cast, Float, func, select
from sqlalchemy.orm import Session

from .. import models


ATTENDANCE_THRESHOLD = 75.0


def get_authorized_subject_ids(
    db: Session,
    user: models.User,
) -> list[int]:
    """
    Return the subject IDs the user is allowed to access.
    """

    if user.role == "super_admin":
        return [
            subject.id
            for subject in db.scalars(
                select(models.Subject)
            ).all()
        ]

    if user.role == "course_admin":
        return [
            subject_id
            for subject_id in db.scalars(
                select(models.TeacherSubject.subject_id)
                .where(
                    models.TeacherSubject.teacher_id == user.id
                )
            ).all()
        ]

    if user.role == "student":
        if not user.student_id:
            return []

        student = db.get(models.Student, user.student_id)

        if not student:
            return []

        return [
            subject.id
            for subject in db.scalars(
                select(models.Subject)
                .where(
                    models.Subject.course_id == student.course_id
                )
            ).all()
        ]

    return []


def get_authorized_students(
    db: Session,
    user: models.User,
) -> list[models.Student]:
    """
    Return only students the current user is authorized to access.
    """

    if user.role == "super_admin":
        return db.scalars(
            select(models.Student)
            .order_by(models.Student.id)
        ).all()

    if user.role == "course_admin":
        if not user.course_id:
            return []

        return db.scalars(
            select(models.Student)
            .where(
                models.Student.course_id == user.course_id
            )
            .order_by(models.Student.id)
        ).all()

    if user.role == "student":
        if not user.student_id:
            return []

        student = db.get(
            models.Student,
            user.student_id,
        )

        return [student] if student else []

    return []


def get_authorized_subject_performance(
    db: Session,
    user: models.User,
) -> dict:
    """
    Return academic performance analytics only for subjects
    the current user is authorized to access.
    """

    subject_ids = get_authorized_subject_ids(db, user)

    if not subject_ids:
        return {
            "user_id": user.id,
            "role": user.role,
            "subjects": [],
            "message": "No authorized subjects found.",
        }

    query = (
        select(
            models.Subject.id,
            models.Subject.code,
            models.Subject.name,
            func.avg(
                (
                    models.Grade.score
                    / models.Grade.max_score
                ) * 100
            ).label("average_percentage"),
            func.count(models.Grade.id).label("grade_count"),
        )
        .join(
            models.Grade,
            models.Grade.subject_id == models.Subject.id,
        )
        .where(
            models.Subject.id.in_(subject_ids),
            models.Grade.published.is_(True),
        )
        .group_by(
            models.Subject.id,
            models.Subject.code,
            models.Subject.name,
        )
        .order_by(models.Subject.code)
    )

    rows = db.execute(query).all()

    subjects = []

    for row in rows:
        subjects.append(
            {
                "subject_id": row.id,
                "code": row.code,
                "subject": row.name,
                "average_percentage": round(
                    float(row.average_percentage or 0),
                    1,
                ),
                "grade_count": int(row.grade_count or 0),
            }
        )

    overall_average = (
        round(
            sum(
                item["average_percentage"]
                for item in subjects
            ) / len(subjects),
            1,
        )
        if subjects
        else 0.0
    )

    return {
        "user_id": user.id,
        "role": user.role,
        "authorized_subject_ids": subject_ids,
        "overall_average": overall_average,
        "subjects": subjects,
    }



def get_student_attendance(
    db: Session,
    student_id: int,
    subject_ids: list[int] | None = None,
) -> dict:
    """
    Get overall and subject-wise attendance for one student.
    """

    query = (
        select(
            models.Subject.id,
            models.Subject.code,
            models.Subject.name,
            func.count(models.Attendance.id).label("total_classes"),
            func.sum(
                case(
                    (models.Attendance.present.is_(True), 1),
                    else_=0,
                )
            ).label("attended_classes"),
        )
        .join(
            models.Attendance,
            models.Attendance.subject_id == models.Subject.id,
        )
        .where(models.Attendance.student_id == student_id)
        .group_by(
            models.Subject.id,
            models.Subject.code,
            models.Subject.name,
        )
    )

    if subject_ids:
        query = query.where(models.Subject.id.in_(subject_ids))

    rows = db.execute(query).all()

    subjects = []

    total_classes = 0
    total_attended = 0

    for row in rows:
        classes = int(row.total_classes or 0)
        attended = int(row.attended_classes or 0)

        percentage = (
            round((attended / classes) * 100, 1)
            if classes
            else 0.0
        )

        total_classes += classes
        total_attended += attended

        subjects.append(
            {
                "subject_id": row.id,
                "code": row.code,
                "subject": row.name,
                "classes": classes,
                "attended": attended,
                "percentage": percentage,
            }
        )

    overall_percentage = (
        round((total_attended / total_classes) * 100, 1)
        if total_classes
        else 0.0
    )

    return {
        "student_id": student_id,
        "total_classes": total_classes,
        "total_attended": total_attended,
        "overall_percentage": overall_percentage,
        "below_threshold": overall_percentage < ATTENDANCE_THRESHOLD,
        "subjects": subjects,
    }


def get_authorized_subject_attendance(
    db: Session,
    user: models.User,
) -> dict:
    """
    Return attendance analytics only for subjects
    the current user is authorized to access.
    """

    subject_ids = get_authorized_subject_ids(db, user)

    if not subject_ids:
        return {
            "user_id": user.id,
            "role": user.role,
            "subjects": [],
            "message": "No authorized subjects found.",
        }

    query = (
        select(
            models.Subject.id,
            models.Subject.code,
            models.Subject.name,
            func.count(models.Attendance.id).label("total_classes"),
            func.sum(
                case(
                    (models.Attendance.present.is_(True), 1),
                    else_=0,
                )
            ).label("attended_classes"),
        )
        .join(
            models.Attendance,
            models.Attendance.subject_id == models.Subject.id,
        )
        .where(
            models.Subject.id.in_(subject_ids)
        )
        .group_by(
            models.Subject.id,
            models.Subject.code,
            models.Subject.name,
        )
        .order_by(models.Subject.code)
    )

    rows = db.execute(query).all()

    subjects = []

    for row in rows:
        total = int(row.total_classes or 0)
        attended = int(row.attended_classes or 0)

        percentage = (
            round((attended / total) * 100, 1)
            if total
            else 0.0
        )

        subjects.append(
            {
                "subject_id": row.id,
                "code": row.code,
                "subject": row.name,
                "classes": total,
                "attended": attended,
                "percentage": percentage,
            }
        )

    return {
        "user_id": user.id,
        "role": user.role,
        "authorized_subject_ids": subject_ids,
        "subjects": subjects,
    }



def get_student_performance(
    db: Session,
    student_id: int,
    subject_ids: list[int] | None = None,
) -> dict:
    """
    Get overall and subject-wise published academic performance
    for one student.
    """

    query = (
        select(
            models.Subject.id,
            models.Subject.code,
            models.Subject.name,
            func.sum(models.Grade.score).label("score"),
            func.sum(models.Grade.max_score).label("max_score"),
        )
        .join(
            models.Grade,
            models.Grade.subject_id == models.Subject.id,
        )
        .where(
            models.Grade.student_id == student_id,
            models.Grade.published.is_(True),
        )
        .group_by(
            models.Subject.id,
            models.Subject.code,
            models.Subject.name,
        )
    )

    if subject_ids:
        query = query.where(models.Subject.id.in_(subject_ids))

    rows = db.execute(query).all()

    subjects = []

    total_score = 0.0
    total_max_score = 0.0

    for row in rows:
        score = float(row.score or 0)
        max_score = float(row.max_score or 0)

        percentage = (
            round((score / max_score) * 100, 1)
            if max_score
            else 0.0
        )

        total_score += score
        total_max_score += max_score

        subjects.append(
            {
                "subject_id": row.id,
                "code": row.code,
                "subject": row.name,
                "score": score,
                "max_score": max_score,
                "percentage": percentage,
            }
        )

    overall_percentage = (
        round((total_score / total_max_score) * 100, 1)
        if total_max_score
        else 0.0
    )

    return {
        "student_id": student_id,
        "overall_percentage": overall_percentage,
        "subjects": subjects,
    }


def get_student_assignments(
    db: Session,
    student_id: int,
    subject_ids: list[int] | None = None,
) -> dict:
    """
    Get assignment totals and submission information for one student.
    """

    query = (
        select(models.Assignment)
        .where(
            models.Assignment.published.is_(True),
            models.Assignment.archived.is_(False),
        )
    )

    if subject_ids:
        query = query.where(
            models.Assignment.subject_id.in_(subject_ids)
        )

    assignments = db.scalars(query).all()

    assignment_data = []

    submitted = 0

    for assignment in assignments:
        submission = db.scalar(
            select(models.Submission)
            .where(
                models.Submission.assignment_id == assignment.id,
                models.Submission.student_id == student_id,
            )
        )

        is_submitted = submission is not None

        if is_submitted:
            submitted += 1

        assignment_data.append(
            {
                "assignment_id": assignment.id,
                "title": assignment.title,
                "subject_id": assignment.subject_id,
                "due_at": assignment.due_at,
                "submitted": is_submitted,
            }
        )

    total = len(assignment_data)

    completion_rate = (
        round((submitted / total) * 100, 1)
        if total
        else 0.0
    )

    return {
        "student_id": student_id,
        "total": total,
        "submitted": submitted,
        "pending": total - submitted,
        "completion_rate": completion_rate,
        "assignments": assignment_data,
    }
    

def get_pending_assignments(
    db: Session,
    student_id: int,
    subject_ids: list[int] | None = None,
) -> dict:
    """
    Return assignments that the student has not submitted.

    If subject_ids are supplied, only those subjects are included.
    Otherwise, the student's own course subjects are used.
    """

    student = db.get(models.Student, student_id)

    if not student:
        return {
            "student_id": student_id,
            "pending_count": 0,
            "assignments": [],
            "message": "Student not found.",
        }

    if subject_ids is None:
        subject_ids = [
            subject.id
            for subject in db.scalars(
                select(models.Subject)
                .where(
                    models.Subject.course_id == student.course_id
                )
            ).all()
        ]

    query = (
        select(models.Assignment)
        .where(
            models.Assignment.published.is_(True),
            models.Assignment.archived.is_(False),
            models.Assignment.subject_id.in_(subject_ids),
        )
        .order_by(models.Assignment.due_at)
    )

    assignments = db.scalars(query).all()

    pending = []

    for assignment in assignments:
        submission = db.scalar(
            select(models.Submission)
            .where(
                models.Submission.assignment_id == assignment.id,
                models.Submission.student_id == student_id,
            )
        )

        if submission is None:
            pending.append(
                {
                    "assignment_id": assignment.id,
                    "title": assignment.title,
                    "subject_id": assignment.subject_id,
                    "due_at": assignment.due_at,
                }
            )

    return {
        "student_id": student_id,
        "course_id": student.course_id,
        "pending_count": len(pending),
        "assignments": pending,
    }



def get_students_needing_attention(
    db: Session,
    students: list[models.Student],
    subject_ids: list[int] | None = None,
    attendance_threshold: float = 75.0,
    performance_threshold: float = 60.0,
    assignment_threshold: float = 50.0,
) -> dict:
    """
    Find authorized students who need academic support.

    A student is flagged if at least one condition is met:
    - Attendance below the attendance threshold.
    - Academic performance below the performance threshold.
    - Assignment submission rate below the assignment threshold.
    """

    results = []

    for student in students:
        attendance = get_student_attendance(
            db=db,
            student_id=student.id,
            subject_ids=subject_ids,
        )

        performance = get_student_performance(
            db=db,
            student_id=student.id,
            subject_ids=subject_ids,
        )

        assignments = get_student_assignments(
            db=db,
            student_id=student.id,
            subject_ids=subject_ids,
        )

        attendance_percentage = float(
            attendance.get("overall_percentage") or 0
        )

        performance_percentage = float(
            performance.get("overall_percentage") or 0
        )

        assignment_rate = float(
            assignments.get("completion_rate") or 0
        )

        low_attendance = (
            attendance_percentage < attendance_threshold
        )

        low_performance = (
            performance_percentage < performance_threshold
        )

        low_assignment_completion = (
            assignment_rate < assignment_threshold
        )

        reasons = []

        if low_attendance:
            reasons.append("Attendance below threshold")

        if low_performance:
            reasons.append("Academic performance below threshold")

        if low_assignment_completion:
            reasons.append("Assignment completion below threshold")

        if reasons:
            results.append(
                {
                    "student_id": student.id,
                    "student_number": student.student_number,
                    "name": student.full_name,
                    "attendance": attendance_percentage,
                    "performance": performance_percentage,
                    "assignment_completion": assignment_rate,
                    "reasons": reasons,
                }
            )

    results.sort(
        key=lambda item: (
            len(item["reasons"]),
            -item["attendance"],
            -item["performance"],
        ),
        reverse=True,
    )

    return {
        "count": len(results),
        "students": results,
        "criteria": {
            "attendance_below": attendance_threshold,
            "performance_below": performance_threshold,
            "assignment_completion_below": assignment_threshold,
        },
    }



def get_student_improvement_priority(
    db: Session,
    student_id: int,
    subject_ids: list[int] | None = None,
) -> dict:
    """
    Identify subjects that should receive the student's attention first.

    Priority rules:
    - Attendance below 75%: high-priority indicator.
    - Attendance from 75% to below 80%: improvement indicator.
    - Performance below 60%: high-priority indicator.
    - Performance from 60% to below 70%: improvement indicator.

    Every scored subject receives an explanation.
    """

    comparison = compare_student_subjects(
        db=db,
        student_id=student_id,
        subject_ids=subject_ids,
    )

    subjects = comparison["subjects"]
    priorities = []

    for subject in subjects:
        attendance = subject["attendance"]
        performance = subject["performance"]

        score = 0
        reasons = []

        # Attendance priority
        if attendance is not None:
            if attendance < 75:
                score += 3
                reasons.append(
                    "Attendance is below the 75% threshold."
                )
            elif attendance < 80:
                score += 1
                reasons.append(
                    "Attendance is below 80%; improvement is recommended."
                )

        # Academic performance priority
        if performance is not None:
            if performance < 60:
                score += 3
                reasons.append(
                    "Academic performance is below 60%."
                )
            elif performance < 70:
                score += 1
                reasons.append(
                    "Academic performance is below 70%; review this subject."
                )

        if score > 0:
            priorities.append(
                {
                    "subject_id": subject["subject_id"],
                    "code": subject["code"],
                    "subject": subject["subject"],
                    "attendance": attendance,
                    "performance": performance,
                    "priority_score": score,
                    "reasons": reasons,
                }
            )

    # Highest score first; break ties using lower performance,
    # then lower attendance, then subject code.
    priorities.sort(
        key=lambda item: (
            -item["priority_score"],
            (
                item["performance"]
                if item["performance"] is not None
                else float("inf")
            ),
            (
                item["attendance"]
                if item["attendance"] is not None
                else float("inf")
            ),
            item["code"],
        )
    )

    return {
        "student_id": student_id,
        "priorities": priorities,
        "top_priority": priorities[0] if priorities else None,
    }




def compare_student_subjects(
    db: Session,
    student_id: int,
    subject_ids: list[int] | None = None,
) -> dict:
    """
    Combine attendance and academic performance by subject.

    This gives My Campus-Intelligent a single structured dataset
    for subject-level analysis.
    """

    attendance = get_student_attendance(
        db=db,
        student_id=student_id,
        subject_ids=subject_ids,
    )

    performance = get_student_performance(
        db=db,
        student_id=student_id,
        subject_ids=subject_ids,
    )

    attendance_map = {
        item["subject_id"]: item
        for item in attendance["subjects"]
    }

    performance_map = {
        item["subject_id"]: item
        for item in performance["subjects"]
    }

    subject_ids_found = set(attendance_map) | set(performance_map)

    subjects = []

    for subject_id in subject_ids_found:
        attendance_item = attendance_map.get(subject_id)
        performance_item = performance_map.get(subject_id)

        subjects.append(
            {
                "subject_id": subject_id,
                "code": (
                    attendance_item["code"]
                    if attendance_item
                    else performance_item["code"]
                ),
                "subject": (
                    attendance_item["subject"]
                    if attendance_item
                    else performance_item["subject"]
                ),
                "attendance": (
                    attendance_item["percentage"]
                    if attendance_item
                    else None
                ),
                "performance": (
                    performance_item["percentage"]
                    if performance_item
                    else None
                ),
            }
        )

    lowest_attendance = min(
        (
            item
            for item in subjects
            if item["attendance"] is not None
        ),
        key=lambda item: item["attendance"],
        default=None,
    )

    lowest_performance = min(
        (
            item
            for item in subjects
            if item["performance"] is not None
        ),
        key=lambda item: item["performance"],
        default=None,
    )

    highest_attendance = max(
        (
            item
            for item in subjects
            if item["attendance"] is not None
        ),
        key=lambda item: item["attendance"],
        default=None,
    )

    highest_performance = max(
        (
            item
            for item in subjects
            if item["performance"] is not None
        ),
        key=lambda item: item["performance"],
        default=None,
    )

    return {
        "student_id": student_id,
        "subjects": subjects,
        "lowest_attendance": lowest_attendance,
        "highest_attendance": highest_attendance,
        "lowest_performance": lowest_performance,
        "highest_performance": highest_performance,
    }
    
def get_assignment_submission_status(
    db: Session,
    assignment_id: int,
    student_ids: list[int] | None = None,
) -> dict:
    """
    Return submission status for a specific assignment.
    """

    assignment = db.get(models.Assignment, assignment_id)

    if not assignment:
        return {
            "assignment_id": assignment_id,
            "found": False,
            "message": "Assignment not found.",
        }

    query = select(models.Student)

    if student_ids:
        query = query.where(
            models.Student.id.in_(student_ids)
        )

    students = db.scalars(query).all()

    submitted = []
    not_submitted = []

    for student in students:
        submission = db.scalar(
            select(models.Submission)
            .where(
                models.Submission.assignment_id == assignment_id,
                models.Submission.student_id == student.id,
            )
        )

        student_data = {
            "student_id": student.id,
            "student_number": student.student_number,
            "name": student.full_name,
        }

        if submission:
            submitted.append(student_data)
        else:
            not_submitted.append(student_data)

    return {
        "assignment_id": assignment.id,
        "title": assignment.title,
        "subject_id": assignment.subject_id,
        "submitted_count": len(submitted),
        "not_submitted_count": len(not_submitted),
        "submitted": submitted,
        "not_submitted": not_submitted,
    }   
    
    
def get_top_students(
    db: Session,
    students: list[models.Student],
    subject_ids: list[int] | None = None,
    limit: int = 10,
) -> dict:
    """
    Rank authorized students by their average published grade percentage.

    The caller must pass an authorized student list.
    When subject_ids is provided, only those subjects are included.

    Students with no eligible published grade records are excluded.
    Higher average performance ranks first.
    Ties are resolved deterministically using student ID.
    """

    limit = max(1, min(int(limit), 50))

    if not students:
        return {
            "count": 0,
            "limit": limit,
            "students": [],
            "message": "No authorized students were found.",
        }

    student_by_id = {
        student.id: student
        for student in students
    }

    student_ids = list(student_by_id.keys())

    # If no subject scope is supplied, limit the query to subjects
    # belonging to the courses represented by the supplied students.
    if subject_ids is None:
        course_ids = list(
            {
                student.course_id
                for student in students
                if student.course_id is not None
            }
        )

        if not course_ids:
            return {
                "count": 0,
                "limit": limit,
                "students": [],
                "message": "No authorized courses were found.",
            }

        subject_ids = list(
            db.scalars(
                select(models.Subject.id).where(
                    models.Subject.course_id.in_(course_ids)
                )
            ).all()
        )

    if not subject_ids:
        return {
            "count": 0,
            "limit": limit,
            "students": [],
            "message": "No authorized subjects were found.",
        }

    # Cast to floating point to ensure grades are converted to
    # percentages without integer division.
    grade_percentage = (
        cast(models.Grade.score, Float)
        / cast(models.Grade.max_score, Float)
        * 100.0
    )

    average_percentage = func.avg(
        grade_percentage
    ).label("average_performance")

    grade_count = func.count(
        models.Grade.id
    ).label("grade_count")

    statement = (
        select(
            models.Grade.student_id,
            average_percentage,
            grade_count,
        )
        .where(
            models.Grade.student_id.in_(student_ids),
            models.Grade.subject_id.in_(subject_ids),
            models.Grade.published.is_(True),
            models.Grade.max_score > 0,
        )
        .group_by(models.Grade.student_id)
        .order_by(
            average_percentage.desc(),
            models.Grade.student_id.asc(),
        )
        .limit(limit)
    )

    rows = db.execute(statement).all()

    ranked_students = []

    for rank, row in enumerate(rows, start=1):
        student = student_by_id.get(row.student_id)

        # Defense in depth: only return students from the supplied
        # authorized list.
        if student is None:
            continue

        ranked_students.append(
            {
                "rank": rank,
                "student_id": student.id,
                "student_number": student.student_number,
                "name": student.full_name,
                "course_id": student.course_id,
                "average_performance": round(
                    float(row.average_performance or 0),
                    1,
                ),
                "grade_count": int(row.grade_count or 0),
            }
        )

    return {
        "count": len(ranked_students),
        "limit": limit,
        "ranking_metric": "average published grade percentage",
        "authorized_subject_ids": subject_ids,
        "students": ranked_students,
    }