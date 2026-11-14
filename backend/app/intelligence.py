from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models



def calculate_attendance_by_subject(db: Session, subject_ids):
    rows = (
        db.query(models.Attendance)
        .filter(models.Attendance.subject_id.in_(subject_ids))
        .all()
    )

    subject_map = {
        subject.id: subject
        for subject in db.query(models.Subject)
        .filter(models.Subject.id.in_(subject_ids))
        .all()
    }

    result = []

    grouped = {}

    for row in rows:
        grouped.setdefault(row.subject_id, []).append(row)

    for subject_id, records in grouped.items():
        if not records or subject_id not in subject_map:
            continue

        percentage = (
            sum(1 for row in records if row.present)
            / len(records)
        ) * 100

        subject = subject_map[subject_id]

        result.append({
            "subject": subject.code,
            "name": subject.name,
            "percentage": round(percentage, 1),
        })

    return result


def calculate_performance_by_subject(db: Session, subject_ids):
    grades = (
        db.query(models.Grade)
        .filter(
            models.Grade.subject_id.in_(subject_ids),
            models.Grade.published.is_(True),
        )
        .all()
    )

    subject_map = {
        subject.id: subject
        for subject in db.query(models.Subject)
        .filter(models.Subject.id.in_(subject_ids))
        .all()
    }

    result = []

    grouped = {}

    for grade in grades:
        grouped.setdefault(grade.subject_id, []).append(grade)

    for subject_id, records in grouped.items():
        if subject_id not in subject_map:
            continue

        percentages = [
            (grade.score / grade.max_score) * 100
            for grade in records
            if grade.max_score
        ]

        if not percentages:
            continue

        subject = subject_map[subject_id]

        result.append({
            "subject": subject.code,
            "name": subject.name,
            "average": round(
                sum(percentages) / len(percentages),
                1,
            ),
        })

    return result



def get_student_intelligence(db: Session, user):
    """Personal academic intelligence for a student."""

    if not user.student_id:
        return {
            "students": 0,
            "subjects": 0,
            "attendance": {"average": 0, "below_75": False},
            "performance": {"average": 0},
            "assignments": {"total": 0, "submitted": 0, "completion_rate": 0},
            "insights": [],
        }

    student = (
        db.query(models.Student)
        .filter(models.Student.id == user.student_id)
        .first()
    )

    if not student:
        return {
            "students": 0,
            "subjects": 0,
            "attendance": {"average": 0, "below_75": False},
            "performance": {"average": 0},
            "assignments": {"total": 0, "submitted": 0, "completion_rate": 0},
            "insights": [],
        }

    subjects = (
        db.query(models.Subject)
        .filter(models.Subject.course_id == student.course_id)
        .all()
    )

    subject_ids = [subject.id for subject in subjects]

    attendance_rows = (
        db.query(models.Attendance)
        .filter(
            models.Attendance.student_id == student.id,
            models.Attendance.subject_id.in_(subject_ids),
        )
        .all()
    )

    attendance_average = 0

    if attendance_rows:
        attendance_average = (
            sum(1 for row in attendance_rows if row.present)
            / len(attendance_rows)
        ) * 100
        
        
    attendance_by_subject = []

    for subject in subjects:
        subject_attendance = [
            row
            for row in attendance_rows
            if row.subject_id == subject.id
        ]

        if subject_attendance:
            subject_percentage = (
                sum(1 for row in subject_attendance if row.present)
                / len(subject_attendance)
            ) * 100

            attendance_by_subject.append({
                "subject": subject.code,
                "name": subject.name,
                "percentage": round(subject_percentage, 1),
            })

    grades = (
        db.query(models.Grade)
        .filter(
            models.Grade.student_id == student.id,
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
        
        performance_by_subject = []

        for subject in subjects:
            subject_grades = [
                grade
                for grade in grades
                if grade.subject_id == subject.id and grade.max_score
            ]

            if subject_grades:
                subject_percentages = [
                    (grade.score / grade.max_score) * 100
                    for grade in subject_grades
                ]

                performance_by_subject.append({
                    "subject": subject.code,
                    "name": subject.name,
                    "average": round(
                        sum(subject_percentages) / len(subject_percentages),
                        1,
                    ),
                })
         
    assignments = (
        db.query(models.Assignment)
        .filter(
            models.Assignment.subject_id.in_(subject_ids),
            models.Assignment.archived.is_(False),
        )
        .all()
    )

    assignment_ids = [assignment.id for assignment in assignments]

    submitted = 0

    if assignment_ids:
        submitted = (
            db.query(func.count(models.Submission.id))
            .filter(
                models.Submission.student_id == student.id,
                models.Submission.assignment_id.in_(assignment_ids),
            )
            .scalar()
            or 0
        )

    completion_rate = (
        (submitted / len(assignments)) * 100
        if assignments
        else 0
    )

    insights = []

    if attendance_average < 75:
        insights.append(
            f"Your attendance is {attendance_average:.1f}%, "
            "which is below the 75% threshold."
        )

    if performance_average:
        insights.append(
            f"Your published academic performance is "
            f"{performance_average:.1f}%."
        )

    if completion_rate < 75 and assignments:
        insights.append(
            f"Your assignment completion rate is "
            f"{completion_rate:.1f}%."
        )

    return {
        "student": {
            "id": student.id,
            "name": student.full_name,
            "student_number": student.student_number,
        },
        "students": 1,
        "subjects": len(subjects),
        "attendance": {
            "average": round(attendance_average, 1),
            "below_75": attendance_average < 75,
            "by_subject": attendance_by_subject,
        },
        "performance": {
            "average": round(performance_average, 1),
            "by_subject": performance_by_subject,
        },
        "assignments": {
            "total": len(assignments),
            "submitted": submitted,
            "completion_rate": round(completion_rate, 1),
        },
        "insights": insights,
    }




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
    
    attendance_by_subject = calculate_attendance_by_subject(
        db,
        subject_ids,
    )   

    performance_by_subject = calculate_performance_by_subject(
        db,
        subject_ids,
    )

    

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
            "by_subject": attendance_by_subject,
        },
        "performance": {
            "average": round(performance_average, 1),
            "by_subject": performance_by_subject,
        },
        "assignments": {
            "total": len(assignments),
            "submission_rate": round(submission_rate, 1),
        },
        "insights": insights,
    }
    
    
def calculate_student_risk(
    db: Session,
    student: models.Student,
    subject_ids,
):
    """
    Rule-based academic risk analysis.

    Risk indicators:
    - Attendance below 75% = 2 points
    - Academic performance below 60% = 2 points
    - Assignment submission below 50% = 1 point

    Risk levels:
    - High: 4+ points
    - Medium: 2-3 points
    - Low: 0-1 points
    """

    # ---------------------------------------------------------
    # ATTENDANCE
    # ---------------------------------------------------------
    attendance_rows = (
        db.query(models.Attendance)
        .filter(
            models.Attendance.student_id == student.id,
            models.Attendance.subject_id.in_(subject_ids),
        )
        .all()
    )

    attendance_percentage = 0.0

    if attendance_rows:
        attendance_percentage = (
            sum(1 for row in attendance_rows if row.present)
            / len(attendance_rows)
        ) * 100

    # ---------------------------------------------------------
    # ACADEMIC PERFORMANCE
    # ---------------------------------------------------------
    grade_rows = (
        db.query(models.Grade)
        .filter(
            models.Grade.student_id == student.id,
            models.Grade.subject_id.in_(subject_ids),
            models.Grade.published.is_(True),
        )
        .all()
    )

    performance_percentage = 0.0

    grade_percentages = [
        (grade.score / grade.max_score) * 100
        for grade in grade_rows
        if grade.max_score
    ]

    if grade_percentages:
        performance_percentage = (
            sum(grade_percentages) / len(grade_percentages)
        )

    # ---------------------------------------------------------
    # ASSIGNMENT SUBMISSION
    # ---------------------------------------------------------
    assignments = (
        db.query(models.Assignment)
        .filter(
            models.Assignment.subject_id.in_(subject_ids),
            models.Assignment.archived.is_(False),
        )
        .all()
    )

    assignment_completion = 0.0

    if assignments:
        assignment_ids = [assignment.id for assignment in assignments]

        submissions = (
            db.query(models.Submission)
            .filter(
                models.Submission.student_id == student.id,
                models.Submission.assignment_id.in_(assignment_ids),
            )
            .all()
        )

        assignment_completion = (
            len(submissions) / len(assignments)
        ) * 100

    # ---------------------------------------------------------
    # RISK SCORING
    # ---------------------------------------------------------
    risk_score = 0
    risk_factors = []

    if attendance_percentage < 75:
        risk_score += 2
        risk_factors.append("attendance below 75%")

    if performance_percentage < 60:
        risk_score += 2
        risk_factors.append("academic performance below 60%")

    if assignments and assignment_completion < 50:
        risk_score += 1
        risk_factors.append("assignment completion below 50%")

    if risk_score >= 4:
        risk_level = "High"
    elif risk_score >= 2:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    return {
        "student_id": student.id,
        "student_number": student.student_number,
        "name": student.full_name,
        "attendance": round(attendance_percentage, 1),
        "performance": round(performance_percentage, 1),
        "assignment_completion": round(assignment_completion, 1),
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_factors": risk_factors,
    }
    

def get_risk_intelligence(db: Session, user):
    """
    Returns role-scoped academic risk analytics.
    """

    # ---------------------------------------------------------
    # DETERMINE AUTHORIZED SUBJECTS
    # ---------------------------------------------------------
    if user.role == "super_admin":

        subjects = (
            db.query(models.Subject)
            .order_by(models.Subject.code)
            .all()
        )

        students = (
            db.query(models.Student)
            .order_by(models.Student.full_name)
            .all()
        )

    elif user.role == "course_admin":

        subjects = (
            db.query(models.Subject)
            .join(
                models.TeacherSubject,
                models.TeacherSubject.subject_id == models.Subject.id,
            )
            .filter(
                models.TeacherSubject.teacher_id == user.id,
                models.Subject.course_id == user.course_id,
            )
            .order_by(models.Subject.code)
            .all()
        )

        subject_ids_for_students = [subject.id for subject in subjects]

        students = (
            db.query(models.Student)
            .filter(
                models.Student.course_id == user.course_id
            )
            .order_by(models.Student.full_name)
            .all()
        )

    elif user.role == "student":

        student = (
            db.query(models.Student)
            .filter(models.Student.id == user.student_id)
            .first()
        )

        if not student:
            return {
                "total_students": 0,
                "high_risk": 0,
                "medium_risk": 0,
                "low_risk": 0,
                "students": [],
            }

        subjects = (
            db.query(models.Subject)
            .filter(models.Subject.course_id == student.course_id)
            .order_by(models.Subject.code)
            .all()
        )

        students = [student]

    else:
        return {
            "total_students": 0,
            "high_risk": 0,
            "medium_risk": 0,
            "low_risk": 0,
            "students": [],
        }

    subject_ids = [subject.id for subject in subjects]

    # ---------------------------------------------------------
    # CALCULATE RISK
    # ---------------------------------------------------------
    results = []

    for student in students:

        result = calculate_student_risk(
            db,
            student,
            subject_ids,
        )

        results.append(result)

    # ---------------------------------------------------------
    # SUMMARY
    # ---------------------------------------------------------
    high_risk = sum(
        1 for student in results
        if student["risk_level"] == "High"
    )

    medium_risk = sum(
        1 for student in results
        if student["risk_level"] == "Medium"
    )

    low_risk = sum(
        1 for student in results
        if student["risk_level"] == "Low"
    )

    # Highest-risk students first
    results.sort(
        key=lambda student: (
            -student["risk_score"],
            student["attendance"],
            student["performance"],
        )
    )

    return {
        "total_students": len(results),
        "high_risk": high_risk,
        "medium_risk": medium_risk,
        "low_risk": low_risk,
        "students": results,
    }