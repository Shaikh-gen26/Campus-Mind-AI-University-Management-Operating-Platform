"""
Role-aware context builder for Campus Mind AI.

This module identifies the current user's role and the data
scope they are permitted to access.

It does not generate AI responses or calculate academic results.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session
import re
from .. import models

from .tools import (
    get_authorized_subject_ids,
    get_authorized_students,
    get_authorized_subject_attendance,
    get_authorized_subject_performance,
    get_student_attendance,
    get_student_performance,
    get_student_improvement_priority,
    get_students_needing_attention,
    compare_student_subjects,
    get_pending_assignments,
    get_assignment_submission_status,
    get_top_students,
)


from ..intelligence import (
    get_course_intelligence,
    get_student_intelligence,
)

from .intent import detect_intent
from .tools import (
    get_authorized_subject_ids,
    get_authorized_students,
    get_authorized_subject_attendance,
    get_authorized_subject_performance,
    get_student_attendance,
    get_student_performance,
    get_student_improvement_priority,
    get_students_needing_attention,
    compare_student_subjects,
)

def build_role_context(
    db: Session,
    user: models.User,
) -> dict:
    """
    Build a basic, role-aware context for the current user.

    Student:
        Only their own student record and course subjects.

    Course Admin:
        Only authorized subjects and their course's student count.

    Super Admin:
        University-wide subject and student scope.

    The returned context describes permissions; it does not
    provide a complete roster or expose unrelated academic records.
    """

    context = {
        "user_id": user.id,
        "email": user.email,
        "role": user.role,
        "course_id": user.course_id,
        "student_id": user.student_id,
        "scope": "none",
        "authorized_subject_ids": [],
        "subjects": [],
        "authorized_student_count": 0,
        "current_student": None,
    }

    # Determine which subjects this user may access.
    subject_ids = get_authorized_subject_ids(db, user)

    context["authorized_subject_ids"] = subject_ids

    # Include only authorized subject information.
    if subject_ids:
        subject_rows = db.execute(
            select(
                models.Subject.id,
                models.Subject.code,
                models.Subject.name,
            )
            .where(models.Subject.id.in_(subject_ids))
            .order_by(models.Subject.code)
        ).all()

        context["subjects"] = [
            {
                "id": row.id,
                "code": row.code,
                "name": row.name,
            }
            for row in subject_rows
        ]

    # Super Admin: university-wide scope.
    if user.role == "super_admin":
        context["scope"] = "university"

        context["authorized_student_count"] = (
            db.scalar(
                select(func.count(models.Student.id))
            )
            or 0
        )

        return context

    # Course Admin: authorized subjects and course students.
    if user.role == "course_admin":
        context["scope"] = "course"

        students = get_authorized_students(db, user)

        context["authorized_student_count"] = len(students)

        return context

    # Student: only their own record.
    if user.role == "student":
        context["scope"] = "self"

        if not user.student_id:
            return context

        student = db.get(
            models.Student,
            user.student_id,
        )

        if not student:
            return context

        context["authorized_student_count"] = 1

        context["current_student"] = {
            "id": student.id,
            "student_number": student.student_number,
            "name": student.full_name,
            "course_id": student.course_id,
        }

        return context

    # Unknown roles receive no academic data scope.
    context["scope"] = "none"
    context["authorized_subject_ids"] = []
    context["subjects"] = []
    context["authorized_student_count"] = 0

    return context

def build_query_context(
    db: Session,
    user: models.User,
    question: str,
    history: list[models.AIMessage] | None = None,
) -> dict:
    """
    Detect the user's intent and retrieve relevant campus data.

    The role-aware context and existing data tools determine
    what information can be returned to the assistant.

    This function retrieves data; it does not generate the final
    natural-language response.
    """

   
    detection = detect_intent(question)
    intent = detection["intent"]

    role_context = build_role_context(db, user)
    subject_ids = role_context["authorized_subject_ids"]

    # Resolve academic-performance follow-ups using conversation history.
    normalized_question = question.strip().lower()

    is_performance_followup = (
        intent == "general_campus_question"
        and bool(
            re.search(
                r"\b(?:what about|how about|and)\b"
                r".*\b(?:performance|grades?|marks?)\b",
                normalized_question,
            )
        )
    )

    if is_performance_followup and history and subject_ids:
        previous_answer = next(
            (
                message.content
                for message in reversed(history)
                if message.role == "assistant"
                and message.content
            ),
            "",
        )

        previous_subject_codes = list(
            dict.fromkeys(
                re.findall(
                    r"\b[A-Z]{2,10}\d{2,4}\b",
                    previous_answer.upper(),
                )
            )
        )

        if previous_subject_codes:
            # Resolve only subjects authorized for the current user.
            matched_subjects = db.execute(
                select(
                    models.Subject.id,
                    models.Subject.code,
                )
                .where(
                    models.Subject.code.in_(previous_subject_codes),
                    models.Subject.id.in_(subject_ids),
                )
            ).all()

            authorized_codes = [
                row.code for row in matched_subjects
            ]

            if authorized_codes:
                detection["intent"] = "subject_performance"
                detection["entities"]["subject_codes"] = authorized_codes
                detection["entities"]["follow_up"] = True
                intent = detection["intent"]
    
    
    
    # Resolve attendance follow-ups using conversation history.
    is_attendance_followup = (
        intent == "general_campus_question"
        and bool(
            re.search(
                r"\b(?:what about|how about|and)\b"
                r".*\b(?:attendance|attend)\b",
                normalized_question,
            )
        )
    )

    if is_attendance_followup and history and subject_ids:
        previous_answer = next(
            (
                message.content
                for message in reversed(history)
                if message.role == "assistant" and message.content
            ),
            "",
        )

        previous_subject_codes = list(
            dict.fromkeys(
                re.findall(
                    r"\b[A-Z]{2,10}\d{2,4}\b",
                    previous_answer.upper(),
                )
            )
        )

        if previous_subject_codes:
            matched_subjects = db.execute(
                select(
                    models.Subject.id,
                    models.Subject.code,
                )
                .where(
                    models.Subject.code.in_(previous_subject_codes),
                    models.Subject.id.in_(subject_ids),
                )
            ).all()

            authorized_codes = [
                row.code for row in matched_subjects
            ]

            if authorized_codes:
                detection["intent"] = "subject_attendance"
                detection["entities"]["subject_codes"] = authorized_codes
                detection["entities"]["follow_up"] = True
                intent = detection["intent"]
    
    
    
    # Resolve requested subject codes within the user's authorization scope.
    requested_codes = (
        detection.get("entities", {}).get("subject_codes") or []
    )

    requested_subject_ids = subject_ids

    if requested_codes:
        matched_subject_ids = db.scalars(
            select(models.Subject.id).where(
                models.Subject.code.in_(requested_codes),
                models.Subject.id.in_(subject_ids),
            )
        ).all()

        requested_subject_ids = list(matched_subject_ids)
    result = {
    "intent": intent,
    "entities": detection["entities"],
    "role": user.role,
    "scope": role_context["scope"],
    "authorized_subject_ids": subject_ids,
    "data": None,
    "message": None,
    }
    # Reject explicitly requested subjects outside the user's scope.
    # Never let an empty subject filter fall back to all authorized subjects.
    if requested_codes and not requested_subject_ids:
        result["message"] = (
            "The requested subject is not available within your "
            "authorized academic scope."
        )
        result["data"] = None
        return result
    
    # ---------------------------------------------------------
    # Students below an attendance threshold
    # ---------------------------------------------------------
    if intent == "low_attendance_students":
        threshold = float(
            detection["entities"].get("attendance_threshold") or 75.0
        )
        threshold = max(1.0, min(threshold, 100.0))

        # Students may see their own attendance, never their peers'.
        if user.role == "student":
            if not user.student_id:
                result["message"] = (
                    "No student record is linked to your account."
                )
                return result

            attendance_data = get_student_attendance(
                db=db,
                student_id=user.student_id,
                subject_ids=subject_ids,
            )

            below_threshold = (
                float(attendance_data.get("overall_percentage") or 0)
                < threshold
            )

            result["data"] = {
                "student_id": user.student_id,
                "attendance": attendance_data,
                "threshold": threshold,
                "below_threshold": below_threshold,
                # Retain this key for compatibility with the existing formatter.
                "meets_threshold": not below_threshold,
            }
            return result

        # Course Admins and Super Admins use their authorized roster.
        if user.role not in {"course_admin", "super_admin"}:
            result["message"] = (
                "Your account is not authorized to view attendance analytics."
            )
            return result

        authorized_students = get_authorized_students(db, user)

        attendance_data = get_students_needing_attention(
            db=db,
            students=authorized_students,
            subject_ids=subject_ids,
        )

        matching_students = [
            student
            for student in attendance_data.get("students", [])
            if student.get("attendance") is not None
            and float(student["attendance"]) < threshold
        ]

        result["data"] = {
            "count": len(matching_students),
            "students": matching_students,
            "attendance_threshold": threshold,
        }

        return result
    
   

    result = {
        "intent": intent,
        "entities": detection["entities"],
        "role": user.role,
        "scope": role_context["scope"],
        "authorized_subject_ids": subject_ids,
        "data": None,
        "message": None,
    }

    # A Student can retrieve only their own personal records.
    if intent == "student_attendance":
        if user.role != "student" or not user.student_id:
            result["message"] = (
                "Personal student attendance is available "
                "only to an authenticated student account."
            )
            return result

        result["data"] = get_student_attendance(
            db=db,
            student_id=user.student_id,
            subject_ids=subject_ids,
        )
        return result

    if intent == "student_performance":
        if user.role != "student" or not user.student_id:
            result["message"] = (
                "Personal student performance is available "
                "only to an authenticated student account."
            )
            return result

        result["data"] = get_student_performance(
            db=db,
            student_id=user.student_id,
            subject_ids=subject_ids,
        )
        return result

    # Personalized improvement recommendations for Students.
    if intent == "improvement_priority":
        if user.role != "student" or not user.student_id:
            result["message"] = (
                "Personal improvement priorities require "
                "a student account."
            )
            return result

        result["data"] = get_student_improvement_priority(
            db=db,
            student_id=user.student_id,
            subject_ids=subject_ids,
        )
        return result

    # Class-wide or personal subject attendance.
    if intent in {
        "subject_attendance",
        "lowest_attendance_subject",
        "class_attendance",
        "low_attendance_students",
    }:
        if user.role == "student":
            if not user.student_id:
                result["message"] = (
                    "No student record is linked to this account."
                )
                return result

            attendance_data = get_student_attendance(
                db=db,
                student_id=user.student_id,
                subject_ids=(
                    requested_subject_ids
                    if requested_codes
                    else subject_ids
                ),
            )

            result["data"] = attendance_data

            # Do not give a Student access to peer records.
            
            if intent == "lowest_attendance_subject":
                subjects = attendance_data.get("subjects", [])

                if not subjects:
                    result["data"] = {
                        "student_id": user.student_id,
                        "subjects": [],
                        "message": "No attendance records were found.",
                    }
                    return result

                lowest_percentage = min(
                    float(subject["percentage"])
                    for subject in subjects
                )

                lowest_subjects = [
                    subject
                    for subject in subjects
                    if float(subject["percentage"]) == lowest_percentage
                ]

                result["data"] = {
                    "student_id": user.student_id,
                    "lowest_attendance_percentage": lowest_percentage,
                    "subjects": lowest_subjects,
                }

                return result

            result["data"] = attendance_data

            # Do not give a Student access to peer records.
            if intent == "low_attendance_students":
                threshold = (
                    detection["entities"].get("attendance_threshold")
                    or 75.0
                )

                result["data"] = {
                    "student_id": user.student_id,
                    "attendance": attendance_data,
                    "threshold": threshold,
                    "meets_threshold": (
                        attendance_data["overall_percentage"] < threshold
                    ),
                }

            return result
                # ---------------------------------------------------------
    # Pending assignments for Students
    # ---------------------------------------------------------
    if intent == "pending_assignments":
        if user.role != "student" or not user.student_id:
            result["message"] = (
                "Personal pending assignments are available "
                "only to an authenticated student account."
            )
            return result

        result["data"] = get_pending_assignments(
            db=db,
            student_id=user.student_id,
            subject_ids=subject_ids,
        )

        return result
                
    
    
    # ---------------------------------------------------------
    # Assignment submission status for authorized classes
    # ---------------------------------------------------------
    if intent == "assignment_submission_status":

        # Students cannot view other students' submission records.
        if user.role == "student":
            result["message"] = (
                "For privacy, I can show your own pending assignments, "
                "but I cannot provide other students' submission records."
            )
            return result

        if user.role not in {"course_admin", "super_admin"}:
            result["message"] = (
                "Your account is not authorized to view submission status."
            )
            return result

        assignment_number = detection["entities"].get(
            "assignment_number"
        )

        if assignment_number is None:
            result["message"] = (
                "Please specify the assignment number, "
                "for example: Which students have not submitted Assignment 2?"
            )
            return result

        if not subject_ids:
            result["message"] = (
                "No authorized subjects were found for your account."
            )
            return result

        # Find matching assignments only within authorized subjects.
        assignments = db.scalars(
            select(models.Assignment)
            .where(
                models.Assignment.subject_id.in_(subject_ids),
                models.Assignment.published.is_(True),
                models.Assignment.archived.is_(False),
                models.Assignment.title.ilike(
                    f"%Assignment {assignment_number}"
                ),
            )
            .order_by(
                models.Assignment.subject_id,
                models.Assignment.id,
            )
        ).all()

        if not assignments:
            result["message"] = (
                f"No published Assignment {assignment_number} "
                "was found in your authorized subjects."
            )
            return result

        
        
        # Restrict the expected student roster to the course
        # associated with each assignment.
        authorized_students = get_authorized_students(db, user)

        assignment_results = []

        for assignment in assignments:
            subject = db.get(
                models.Subject,
                assignment.subject_id,
            )

            if subject is None:
                continue

            # Never count students outside this assignment's course.
            assignment_students = [
                student
                for student in authorized_students
                if student.course_id == subject.course_id
            ]

            student_ids = [
                student.id
                for student in assignment_students
            ]

            submission_data = get_assignment_submission_status(
                db=db,
                assignment_id=assignment.id,
                student_ids=student_ids,
            )

            assignment_results.append(
                {
                    "assignment_id": assignment.id,
                    "title": assignment.title,
                    "subject_id": assignment.subject_id,
                    "student_count": len(assignment_students),
                    "submitted_count": submission_data[
                        "submitted_count"
                    ],
                    "not_submitted_count": submission_data[
                        "not_submitted_count"
                    ],
                    "not_submitted": submission_data[
                        "not_submitted"
                    ],
                }
            )

        result["data"] = {
            "assignment_number": assignment_number,
            "role": user.role,
            "authorized_student_count": len(authorized_students),
            "assignments": assignment_results,
        }

        return result
        
                
            

        # Course Admin and Super Admin use authorized class data.
        if intent == "low_attendance_students":
            students = get_authorized_students(db, user)

            attention_data = get_students_needing_attention(
                db=db,
                students=students,
                subject_ids=subject_ids,
            )

            threshold = (
                detection["entities"].get(
                    "attendance_threshold"
                )
                or 75.0
            )

            filtered_students = [
                student
                for student in attention_data["students"]
                if student["attendance"] < threshold
            ]

            result["data"] = {
                "count": len(filtered_students),
                "students": filtered_students,
                "attendance_threshold": threshold,
            }

            return result

        result["data"] = get_authorized_subject_attendance(
            db=db,
            user=user,
        )
        return result

    
    
    # ---------------------------------------------------------
    # Subject-level academic performance
    # ---------------------------------------------------------
    if intent == "subject_performance":
        if requested_codes and not requested_subject_ids:
            result["message"] = (
                "The requested subject was not found in your "
                "authorized academic scope."
            )
            return result

        if user.role == "student":
            if not user.student_id:
                result["message"] = (
                    "No student record is linked to this account."
                )
                return result

            result["data"] = get_student_performance(
                db=db,
                student_id=user.student_id,
                subject_ids=requested_subject_ids,
            )
            return result

        performance_data = get_authorized_subject_performance(
            db=db,
            user=user,
        )

        # Filter administrative results when specific subjects were requested.
        if requested_codes:
            performance_data["subjects"] = [
                subject
                for subject in performance_data.get("subjects", [])
                if subject.get("code") in requested_codes
            ]

            if not performance_data["subjects"]:
                result["message"] = (
                    "No published performance records were found "
                    "for the requested authorized subjects."
                )
                return result

            averages = [
                float(
                    subject.get("average_percentage")
                    or subject.get("average")
                    or 0
                )
                for subject in performance_data["subjects"]
            ]

            performance_data["overall_average"] = round(
                sum(averages) / len(averages),
                1,
            )

        result["data"] = performance_data
        return result
    
    
    

    # Academic-performance and attendance concerns.
    if intent in {
        "students_needing_attention",
        "low_performance_students",
    }:
        students = get_authorized_students(db, user)

        attention_data = get_students_needing_attention(
            db=db,
            students=students,
            subject_ids=subject_ids,
        )

        if intent == "low_performance_students":
            filtered_students = [
                student
                for student in attention_data["students"]
                if student["performance"] < 60.0
            ]

            result["data"] = {
                "count": len(filtered_students),
                "students": filtered_students,
                "performance_threshold": 60.0,
            }
        else:
            result["data"] = attention_data

        return result
    
    
    
    # ---------------------------------------------------------
    # Top-performing students
    # ---------------------------------------------------------
    if intent == "top_students":

        # Student accounts cannot access peers' academic records.
        if user.role == "student":
            result["message"] = (
                "For privacy, student accounts can view their own "
                "academic records. Student rankings are available "
                "to authorized Course Admins and Super Admins."
            )
            return result

        if user.role not in {"course_admin", "super_admin"}:
            result["message"] = (
                "Your account is not authorized to view student rankings."
            )
            return result

        authorized_students = get_authorized_students(db, user)

        requested_limit = (
            detection["entities"].get("limit") or 10
        )

        result["data"] = get_top_students(
            db=db,
            students=authorized_students,
            subject_ids=subject_ids,
            limit=requested_limit,
        )

        return result
    
    

    # General academic overview.
    if intent == "class_overview":
        if user.role == "student":
            result["data"] = get_student_intelligence(
                db,
                user,
            )
        else:
            result["data"] = get_course_intelligence(
                db,
                user,
            )

        return result

    # Recognized intents without a connected data tool.
    result["message"] = (
        "This question has been recognized, but its dedicated "
        "data tool has not been connected yet."
    )

    return result
