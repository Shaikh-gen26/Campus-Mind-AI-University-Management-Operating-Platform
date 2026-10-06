from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models


def get_course_intelligence(db: Session, user):
    """
    Course-level analytics for Course Admin.
    Uses only subjects assigned to the current user.
    """

    
    if user.role == "super_admin":
        assigned_subjects = (
            db.query(models.Subject)
            .all()
        )

    elif user.role == "course_admin":
        assigned_subjects = (
            db.query(models.Subject)
            .join(
                models.TeacherSubject,
                models.TeacherSubject.subject_id == models.Subject.id,
            )
            .filter(
                models.TeacherSubject.teacher_id == user.id,
                models.Subject.course_id == user.course_id,
            )
            .all()
        )

    else:
        assigned_subjects = []

    subject_ids = [s.id for s in assigned_subjects]

    

    if not subject_ids:
        return {
            "students": 0,
            "subjects": 0,
            "attendance": {
                "average": 0,
                "below_75": 0,
            },
            "performance": {
                "average": 0,
            },
            "assignments": {
                "total": 0,
                "submission_rate": 0,
            },
            "insights": [],
        }

    student_query = db.query(func.count(models.Student.id))

    if user.role != "super_admin":
        student_query = student_query.filter(
            models.Student.course_id == user.course_id
        )

    student_count = student_query.scalar() or 0
        

    attendance_rows = (
        db.query(models.Attendance)
        .filter(models.Attendance.subject_id.in_(subject_ids))
        .all()
    )

    attendance_average = 0

    if attendance_rows:
        attendance_average = (
            sum(1 for row in attendance_rows if row.present)
            / len(attendance_rows)
        ) * 100

    student_attendance = {}

    for row in attendance_rows:
        student_attendance.setdefault(row.student_id, []).append(row.present)

    below_75 = 0

    for records in student_attendance.values():
        percentage = (sum(records) / len(records)) * 100

        if percentage < 75:
            below_75 += 1

    grades = (
        db.query(models.Grade)
        .filter(
            models.Grade.subject_id.in_(subject_ids),
            models.Grade.published.is_(True),
        )
        .all()
    )

    performance_average = 0

    if grades:
        percentages = [
            (grade.score / grade.max_score) * 100
            for grade in grades
            if grade.max_score
        ]

        if percentages:
            performance_average = sum(percentages) / len(percentages)

    assignments = (
        db.query(models.Assignment)
        .filter(
            models.Assignment.subject_id.in_(subject_ids),
            models.Assignment.archived.is_(False),
        )
        .all()
    )

    submissions = 0

    if assignments:
        assignment_ids = [a.id for a in assignments]

        submissions = (
            db.query(func.count(models.Submission.id))
            .filter(
                models.Submission.assignment_id.in_(assignment_ids)
            )
            .scalar()
            or 0
        )

    possible_submissions = student_count * len(assignments)

    submission_rate = (
        (submissions / possible_submissions) * 100
        if possible_submissions
        else 0
    )

    insights = []

    if below_75:
        insights.append(
            f"{below_75} students are below the 75% attendance threshold."
        )

    if performance_average:
        insights.append(
            f"Average published academic performance is "
            f"{performance_average:.1f}%."
        )

    if submission_rate:
        insights.append(
            f"Assignment submission rate is {submission_rate:.1f}%."
        )

    return {
        "students": student_count,
        "subjects": len(assigned_subjects),
        "attendance": {
            "average": round(attendance_average, 1),
            "below_75": below_75,
        },
        "performance": {
            "average": round(performance_average, 1),
        },
        "assignments": {
            "total": len(assignments),
            "submission_rate": round(submission_rate, 1),
        },
        "insights": insights,
    }