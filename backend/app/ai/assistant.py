

from datetime import datetime




"""
Response formatting for Campus Mind AI.

This module converts verified, structured campus data into
readable answers.

Academic values come from the database and Python calculations.
This module does not invent academic records.
"""


def format_query_answer(query_context: dict) -> str | None:
    """
    Format the result of build_query_context() into a readable answer.

    Return None when the intent does not yet have a formatter.
    """

    intent = query_context.get("intent")
    data = query_context.get("data")
    message = query_context.get("message")

    if not isinstance(data, dict):
        return message or None

    if message and not data:
        return message

    def percentage(value) -> str:
        return f"{float(value or 0):.1f}%"

    # ---------------------------------------------------------
    # Student attendance
    # ---------------------------------------------------------
    if intent == "student_attendance":
        total = int(data.get("total_classes") or 0)
        attended = int(data.get("total_attended") or 0)
        overall = percentage(data.get("overall_percentage"))

        subjects = data.get("subjects") or []

        answer = (
            f"Your overall attendance is {overall} "
            f"({attended} of {total} recorded classes attended)."
        )
        
        if subjects:
            details = "; ".join(
                f"{subject.get('code', 'N/A')} — "
                f"{subject.get('name') or subject.get('subject') or 'Unknown subject'}: "
                f"{percentage(subject.get('percentage'))}"
                for subject in subjects
            )
        
        

            answer += f"\n\nSubject-wise attendance: {details}."

        return answer

    # ---------------------------------------------------------
    # Lowest-attendance subject or subjects
    # ---------------------------------------------------------
    if intent == "lowest_attendance_subject":
        subjects = data.get("subjects") or []

        if not subjects:
            return "No subject-wise attendance records were found."

        lowest = percentage(
            data.get("lowest_attendance_percentage")
        )

        
        names = ", ".join(
            f"{subject.get('name') or subject.get('subject') or 'Unknown subject'} "
            f"({subject.get('code', 'N/A')})"
            for subject in subjects
        )
        

        if len(subjects) == 1:
            return (
                f"Your lowest attendance is {lowest}, in: {names}. "
                "This subject has the lowest recorded attendance "
                "among your courses."
            )

        return (
            f"Your lowest attendance is {lowest}, in: {names}. "
            "These subjects share the lowest recorded percentage."
        )

    
    
    
    # ---------------------------------------------------------
    # Subject-specific attendance, including follow-ups
    # ---------------------------------------------------------
    if intent == "subject_attendance":
        requested_codes = (
            query_context.get("entities", {}).get("subject_codes")
            or []
        )

        subjects = data.get("subjects") or []

        # Personal attendance data returned for a Student.
        if "overall_percentage" in data:
            if requested_codes:
                subjects = [
                    subject
                    for subject in subjects
                    if subject.get("code") in requested_codes
                ]

                if not subjects:
                    return (
                        "No attendance records were found "
                        "for the requested authorized subject."
                    )

                if len(subjects) == 1:
                    subject = subjects[0]
                    name = (
                        subject.get("name")
                        or subject.get("subject")
                        or "Unknown subject"
                    )
                    code = subject.get("code", "N/A")

                    return (
                        f"Your attendance in {name} ({code}) is "
                        f"{percentage(subject.get('percentage'))}."
                    )

                details = "; ".join(
                    f"{subject.get('name') or subject.get('subject') or 'Unknown subject'} "
                    f"({subject.get('code', 'N/A')}): "
                    f"{percentage(subject.get('percentage'))}"
                    for subject in subjects
                )

                return f"Your attendance in the requested subjects is: {details}."

            return format_query_answer(
                {
                    **query_context,
                    "intent": "student_attendance",
                }
            )

        # Class-level attendance data for Course Admins or Super Admins.
        if requested_codes:
            subjects = [
                subject
                for subject in subjects
                if subject.get("code") in requested_codes
            ]

        if not subjects:
            return (
                "No attendance records were found "
                "for the authorized subjects."
            )

        lines = ["Authorized subject attendance:"]

        for subject in subjects:
            name = (
                subject.get("name")
                or subject.get("subject")
                or "Unknown subject"
            )
            code = subject.get("code", "N/A")

            lines.append(
                f"- {code} — {name}: "
                f"{percentage(subject.get('percentage'))}"
            )

        return "\n".join(lines)
    
    
    
    
    # ---------------------------------------------------------
    # Student academic performance
    # ---------------------------------------------------------
    if intent == "student_performance":
        overall = percentage(data.get("overall_percentage"))
        subjects = data.get("subjects") or []
        entities = query_context.get("entities") or {}

        requested_codes = entities.get("subject_codes") or []
        is_specific_subject_query = bool(requested_codes)

        if is_specific_subject_query:
            if not subjects:
                return (
                    "No published performance records were found "
                    "for the requested subject."
                )

            if len(subjects) == 1:
                subject = subjects[0]
                code = subject.get("code", "N/A")
                name = (
                    subject.get("name")
                    or subject.get("subject")
                    or "Unknown subject"
                )
                score = percentage(subject.get("percentage"))

                return (
                    f"Your academic performance in {name} ({code}) "
                    f"is {score}."
                )

            details = "; ".join(
                f"{subject.get('name') or subject.get('subject') or 'Unknown subject'} "
                f"({subject.get('code', 'N/A')}): "
                f"{percentage(subject.get('percentage'))}"
                for subject in subjects
            )

            return f"Your academic performance in the requested subjects is: {details}."

        answer = f"Your overall academic performance is {overall}."

        if subjects:
            details = "; ".join(
                f"{subject.get('code', 'N/A')} — "
                f"{subject.get('name') or subject.get('subject') or 'Unknown subject'}: "
                f"{percentage(subject.get('percentage'))}"
                for subject in subjects
            )

            answer += f"\n\nSubject-wise performance: {details}."

        return answer
    
    
    

    # ---------------------------------------------------------
    # Student improvement priorities
    # ---------------------------------------------------------
    if intent == "improvement_priority":
        priorities = data.get("priorities") or []
        top = data.get("top_priority")

        if not top and not priorities:
            return "No academic improvement priorities were identified."

        if not top:
            top = priorities[0]

        subject_name = top.get("subject") or top.get("name")
        subject_name = subject_name or top.get("code", "the identified subject")

        reasons = top.get("reasons") or []

        answer = (
            f"Your first improvement priority is "
            f"{subject_name} ({top.get('code', 'N/A')}). "
            f"Attendance: {percentage(top.get('attendance'))}; "
            f"performance: {percentage(top.get('performance'))}."
        )

        
        if reasons:
            clean_reasons = [
                reason.rstrip().rstrip(".")
                for reason in reasons
            ]

            answer += (
                "\n\nWhy this is a priority: "
                + "; ".join(clean_reasons)
                + "."
            )
        
        
        remaining = [
            item for item in priorities
            if item.get("subject_id") != top.get("subject_id")
        ]

        if remaining:
            next_priority = remaining[0]
            next_name = (
                next_priority.get("subject")
                or next_priority.get("name")
                or next_priority.get("code", "another subject")
            )

            answer += f"\n\nAfter that, review {next_name}."

        return answer
    
    
    
    
    # ---------------------------------------------------------
    # Top-performing students
    # ---------------------------------------------------------
    if intent == "top_students":
        students = data.get("students") or []

        if not students:
            return (
                data.get("message")
                or "No eligible published grade records were found "
                   "for the authorized students."
            )

        lines = [
            "Top-performing students, ranked by average "
            "published grade percentage:"
        ]

        for student in students:
            rank = student.get("rank", "?")
            name = student.get("name", "Unknown student")
            student_number = student.get(
                "student_number",
                "N/A",
            )
            performance = float(
                student.get("average_performance") or 0
            )
            grade_count = int(
                student.get("grade_count") or 0
            )

            lines.append(
                f"{rank}. {name} ({student_number}) — "
                f"{performance:.1f}%"
            )

            if grade_count:
                lines.append(
                    f"   Based on {grade_count} published grade records."
                )

        lines.append(
            "\nThe ranking uses published grades from the subjects "
            "authorized for your account."
        )

        return "\n".join(lines)
    
    
    
    # ---------------------------------------------------------
    # Assignment submission status
    # ---------------------------------------------------------
    if intent == "assignment_submission_status":
        assignments = data.get("assignments") or []

        authorized_count = int(
            data.get("authorized_student_count") or 0
        )

        role = query_context.get("role")
        is_super_admin = role == "super_admin"

        if not assignments:
            return (
                query_context.get("message")
                or "No matching assignments were found."
            )

        assignment_number = data.get("assignment_number", "")

        if is_super_admin:
            lines = [
                f"Assignment {assignment_number} submission status "
                f"across the university.",
                f"Total university students: {authorized_count}.",
                f"Assignments found: {len(assignments)}.",
                "Each assignment is evaluated against students "
                "in its own course.",
            ]
        else:
            lines = [
                f"Assignment {assignment_number} submission status "
                f"for {authorized_count} authorized students:"
            ]

        # Super Admin gets a single 20-student sample across
        # all matching assignments, avoiding enormous responses.
        remaining_sample_slots = 20
        university_sample = []

        for assignment in assignments:
            title = assignment.get(
                "title",
                "Untitled assignment",
            )

            submitted = int(
                assignment.get("submitted_count") or 0
            )

            not_submitted = int(
                assignment.get("not_submitted_count") or 0
            )

            students = assignment.get("not_submitted") or []

            lines.append(f"\n{title}")
            lines.append(f"- Submitted: {submitted}")
            lines.append(f"- Not submitted: {not_submitted}")

            if not_submitted == 0:
                lines.append(
                    "- All students in this assignment's course "
                    "have recorded submissions."
                )
                continue

            
            
            
            
            if is_super_admin and remaining_sample_slots > 0:
                sample_limit = min(3, remaining_sample_slots)

                for student in students[:sample_limit]:
                    university_sample.append(
                        {
                            "assignment": title,
                            "student_number": student.get(
                                "student_number",
                                "Unknown student number",
                            ),
                            "name": student.get(
                                "name",
                                "Unknown student",
                            ),
                        }
                    )

        
            
            
            

                    remaining_sample_slots -= 1

            elif students and not is_super_admin:
                lines.append(
                    "\nStudents without recorded submissions:"
                )

                for student in students[:20]:
                    lines.append(
                        f"- {student.get('student_number', 'N/A')} "
                        f"— {student.get('name', 'Unknown student')}"
                    )

                if len(students) > 20:
                    lines.append(
                        f"- Showing 20 of {len(students)} "
                        "students without recorded submissions."
                    )

        if is_super_admin and university_sample:
            lines.append(
                "Sample of students without recorded submissions "
                "(up to 20 records, with at most 3 per assignment):"
            )

            for item in university_sample:
                lines.append(
                    f"- {item['student_number']} — {item['name']} "
                    f"({item['assignment']})"
                )

            lines.append(
                "\nThe assignment summaries above cover all matches; "
                "the student list is a limited sample."
            )

        return "\n".join(lines)
    
    
    
    
    
    
    # ---------------------------------------------------------
    # Student pending assignments
    # ---------------------------------------------------------
    if intent == "pending_assignments":
        assignments = data.get("assignments") or []
        count = int(data.get("pending_count") or 0)

        if not assignments:
            return "You have no pending assignments recorded in the system."

        now = datetime.now()
        lines = [
            f"You have {count} assignments with no recorded submissions."
        ]

        overdue_count = 0

        for assignment in assignments:
            title = assignment.get("title", "Untitled assignment")
            due_value = assignment.get("due_at")

            if isinstance(due_value, str):
                try:
                    due_value = datetime.fromisoformat(
                        due_value.replace("Z", "+00:00")
                    )
                except ValueError:
                    due_value = None

            if isinstance(due_value, datetime):
                if due_value.tzinfo is not None:
                    current_time = datetime.now(due_value.tzinfo)
                else:
                    current_time = now

                due_text = due_value.strftime("%d %b %Y, %I:%M %p")

                if due_value < current_time:
                    status = "OVERDUE"
                    overdue_count += 1
                elif due_value.date() == current_time.date():
                    status = "DUE TODAY"
                else:
                    status = "UPCOMING"

                lines.append(
                    f"- {title} — due {due_text} [{status}]"
                )
            else:
                lines.append(
                    f"- {title} — due date unavailable"
                )

        if overdue_count:
            lines.append(
                f"\nAttention: {overdue_count} of these assignments "
                "have passed their recorded due dates and have no "
                "recorded submissions."
            )

        lines.append(
            "\nCheck the assignment page for submission instructions "
            "or to confirm whether any submission records are missing."
        )

        return "\n".join(lines)
    
    
    
    
    
    # ---------------------------------------------------------
    # Course or university overview
    # ---------------------------------------------------------
    if intent == "class_overview":
        attendance = data.get("attendance") or {}
        performance = data.get("performance") or {}
        assignments = data.get("assignments") or {}

        lines = [
            "### Academic overview",
            f"- Authorized students: {data.get('students', 0)}",
            f"- Authorized subjects: {data.get('subjects', 0)}",
        ]

        if "average" in attendance:
            lines.append(
                f"- Average attendance: {percentage(attendance['average'])}"
            )

        if "below_75" in attendance:
            lines.append(
                f"- Students below 75% attendance: {attendance['below_75']}"
            )

        if "average" in performance:
            lines.append(
                f"- Average academic performance: "
                f"{percentage(performance['average'])}"
            )

        if "total" in assignments:
            lines.append(
                f"- Published assignments: {assignments['total']}"
            )

        if "submission_rate" in assignments:
            lines.append(
                f"- Assignment submission rate: "
                f"{percentage(assignments['submission_rate'])}"
            )

        subject_performance = performance.get("by_subject") or []

        if subject_performance:
            lines.append("\nSubject-wise performance:")

            for subject in subject_performance:
                value = subject.get(
                    "average",
                    subject.get("average_percentage", 0),
                )

                lines.append(
                    f"- {subject['subject']} — "
                    f"{subject.get('name', '')}: {percentage(value)}"
                )

        insights = data.get("insights") or []

        if insights:
            lines.append("\nObservations:")

            lines.extend(f"- {insight}" for insight in insights)

        return "\n".join(lines)

    # ---------------------------------------------------------
    # Attendance analytics
    # ---------------------------------------------------------
    
    
        if "overall_percentage" in data:
            requested_codes = (
                query_context.get("entities", {}).get("subject_codes")
                or []
            )

        if requested_codes:
            subjects = data.get("subjects") or []

            if not subjects:
                return (
                    "No attendance records were found "
                    "for the requested subject."
                )

            details = []

            for subject in subjects:
                details.append(
                    f"{subject.get('name') or subject.get('subject') or 'Unknown subject'} "
                    f"({subject.get('code', 'N/A')}): "
                    f"{percentage(subject.get('percentage'))}"
                )

            return (
                "Your attendance in "
                + "; ".join(details)
                + "."
            )

        return format_query_answer(
            {
                **query_context,
                "intent": "student_attendance",
            }
        )
    
    

    # ---------------------------------------------------------
    # Academic performance analytics
    # ---------------------------------------------------------
    if intent in {
        "subject_attendance",
        "class_attendance",
    }:
    
    
        
        # Personal performance returned for a Student.
        if "overall_percentage" in data:
            return format_query_answer(
                {
                    **query_context,
                    "intent": "student_performance",
                }
            )

        subjects = data.get("subjects") or []

        if not subjects:
            return "No published performance records were found."

        lines = [
            "Authorized subject performance:",
            f"- Overall subject average: "
            f"{percentage(data.get('overall_average'))}",
        ]

        for subject in subjects:
            value = subject.get(
                "average_percentage",
                subject.get("average", 0),
            )

            lines.append(
                f"- {subject['code']} — {subject['subject']}: "
                f"{percentage(value)}"
            )

        return "\n".join(lines)

    # ---------------------------------------------------------
    # Students needing attention or below a threshold
    # ---------------------------------------------------------
    if intent in {
        "students_needing_attention",
        "low_performance_students",
        "low_attendance_students",
    }:
        # Student queries must never show peer records.
        if query_context.get("role") == "student":
            attendance = data.get("attendance") or {}

            if attendance:
                current = attendance.get("overall_percentage", 0)
                threshold = data.get("threshold", 75)

                if data.get("below_threshold"):
                    return (
                        f"Your attendance is {percentage(current)}, "
                        f"below the required threshold of "
                        f"{percentage(threshold)}. "
                        "You should prioritize improving attendance."
                    )

                return (
                    f"Your attendance is {percentage(current)}, "
                    f"which meets the configured threshold."
                )

            return "No additional student records can be provided."

        students = data.get("students") or []
        count = int(data.get("count") or 0)

        if not students:
            return "No students met the specified criteria."

        lines = [f"Students identified: {count}."]

        for student in students[:20]:
            lines.append(
                f"- {student.get('name', 'Unknown student')} "
                f"({student.get('student_number', 'N/A')}): "
                f"attendance {percentage(student.get('attendance'))}, "
                f"performance {percentage(student.get('performance'))}."
            )

            reasons = student.get("reasons") or []

            if reasons:
                lines.append("  Reasons: " + "; ".join(reasons))

        if count > 20:
            lines.append(
                f"Showing 20 of {count} matching students."
            )

        return "\n".join(lines)

    # The intent may be detected before its data tool is implemented.
    return None