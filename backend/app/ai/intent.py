"""
Intent detection for Campus Mind AI.

This module identifies what the user is asking.

It does not:
- Retrieve database records.
- Calculate academic metrics.
- Enforce permissions.
- Generate the final AI response.
"""

import re
from typing import Any


# Rules are evaluated in order.
# More specific questions should appear before general questions.
INTENT_RULES = [
    (
        "compare_subjects",
        [
            r"\bcompare\b",
            r"\bcomparison\b",
            r"\bversus\b",
            r"\bvs\.?\b",
            r"\bdifference between\b",
        ],
    ),
    (
        "students_needing_attention",
        [
            r"\bneed(?:s|ing)? academic support\b",
            r"\bstudents? at risk\b",
            r"\bacademic risk\b",
            r"\bboth\b.*\battendance\b.*\b(?:grade|performance|mark)",
            r"\blow attendance\b.*\blow\b.*\b(?:grade|performance|mark)",
        ],
    ),
    (
        "assignment_submission_status",
        [
            r"\bnot submitted\b",
            r"\bnever submitted\b",
            r"\bmissing submissions?\b",
            r"\bwho submitted\b",
            r"\bsubmission status\b",
            r"\ball students submitted\b",
            r"\bwho has(?:n't| not) submitted\b",
            r"\bwho have(?:n't| not) submitted\b",
        ],
    ),
    
    
    
    (
        "pending_assignments",
        [
            r"\bpending assignments?\b",
            r"\bassignments? (?:are )?due\b",
            r"\bupcoming assignments?\b",
            r"\bmy assignments?\b",
            r"\bassignments? left\b",
            r"\bwhich assignments?\b.*\bnot submitted\b",
            r"\bwhich assignments?\b.*\bnot submit\b",
            r"\bassignments?\b.*\bi haven't submitted\b",
            r"\bassignments?\b.*\bi have not submitted\b",
        ],
    ),
    
    
    
    (
        "top_students",
        [
            r"\btop\s+\d+\s+students?\b",
            r"\bbest performing students?\b",
            r"\bhighest performing students?\b",
            r"\bclass rank(?:ing)?\b",
        ],
    ),
    (
        "lowest_attendance_subject",
        [
            r"\bwhich subject\b.*\blowest attendance\b",
            r"\blowest attendance subject\b",
            r"\bsubject\b.*\bworst attendance\b",
        ],
    ),
    (
        "low_attendance_students",
        [
            r"\bstudents?\b.*\b(?:below|under|less than)\s*\d*\s*%?\s*attendance\b",
            r"\bstudents?\b.*\blow attendance\b",
            r"\blow attendance students?\b",
            r"\battendance below\b",
            r"\bwho has the lowest attendance\b",
            r"\bwho have the lowest attendance\b",
        ],
    ),
    (
        "lowest_performance_subject",
        [
            r"\bwhich subject\b.*\b(?:lowest|worst)\b.*\bperformance\b",
            r"\bsubject\b.*\blowest performance\b",
            r"\bworst performing subject\b",
        ],
    ),
    (
        "low_performance_students",
        [
            r"\blow(?:est)? performing students?\b",
            r"\bstudents?\b.*\blow grades?\b",
            r"\bstudents?\b.*\blow marks\b",
            r"\bstudents?\b.*\blow academic performance\b",
        ],
    ),
    (
        "improvement_priority",
        [
            r"\bwhat should i improve\b",
            r"\bwhat should i improve first\b",
            r"\bwhere should i improve\b",
            r"\bwhat should i focus on\b",
            r"\bhow can i improve\b",
            r"\bhow do i improve\b",
            r"\bwhich subject\b.*\bfocus on\b",
            r"\bwhat subject\b.*\bfocus on\b",
        ],
    ),
    (
        "student_attendance",
        [
            r"\bmy attendance\b",
            r"\bhow is my attendance\b",
            r"\bwhat is my attendance\b",
            r"\bmy attendance percentage\b",
        ],
    ),
    (
        "student_performance",
        [
            r"\bmy academic performance\b",
            r"\bhow am i performing\b",
            r"\bmy grades\b",
            r"\bmy marks\b",
            r"\bmy academic results\b",
            r"\bhow did i perform\b",
        ],
    ),
    (
        "subject_attendance",
        [
            r"\battendance\b.*\b(?:subject|course)\b",
            r"\b(?:subject|course)\b.*\battendance\b",
        ],
    ),
    (
        "subject_performance",
        [
            r"\bperformance\b.*\b(?:subject|course)\b",
            r"\b(?:subject|course)\b.*\bperformance\b",
            r"\bgrades for\b",
            r"\bmarks for\b",
            r"\bperformance of\b",
        ],
    ),
    (
        "class_attendance",
        [
            r"\bclass attendance\b",
            r"\boverall attendance\b",
            r"\battendance summary\b",
            r"\banalyze attendance\b",
        ],
    ),
    (
        "class_overview",
        [
            r"\banalyze my class\b",
            r"\banalyze the class\b",
            r"\bclass overview\b",
            r"\bclass performance\b",
            r"\bhow is my class performing\b",
        ],
    ),
    (
        "upcoming_exams",
        [
            r"\bupcoming exams?\b",
            r"\bnext exam\b",
            r"\bwhen is my exam\b",
            r"\bexam schedule\b",
            r"\bexam timetable\b",
        ],
    ),
    (
        "timetable",
        [
            r"\bmy timetable\b",
            r"\bclass timetable\b",
            r"\bmy next class\b",
            r"\bnext lecture\b",
            r"\bclass schedule\b",
        ],
    ),
    (
        "faq_or_general",
        [
            r"\bhow do i log in\b",
            r"\bhow can i log in\b",
            r"\bforgot my password\b",
            r"\battendance policy\b",
            r"\buniversity policy\b",
            r"\bwhere can i find\b",
            r"\bhow do i access\b",
        ],
    ),
]


def detect_intent(question: str) -> dict[str, Any]:
    """
    Identify the most likely intent and extract basic entities.

    The result is a routing suggestion, not an authorization decision.
    """

    normalized = re.sub(
        r"\s+",
        " ",
        question.strip().lower(),
    )

    subject_codes = list(
        dict.fromkeys(
            re.findall(
                r"\b[A-Z]{2,10}\d{2,4}\b",
                question.upper(),
            )
        )
    )

    assignment_match = re.search(
        r"\bassignment\s*(?:number\s*)?(\d+)\b",
        normalized,
    )

    limit_match = re.search(
        r"\btop\s+(\d+)\b",
        normalized,
    )

    threshold_match = re.search(
        r"\b(?:below|under|less than)\s*(\d{1,3})\s*%?",
        normalized,
    )

    entities = {
        "subject_codes": subject_codes,
        "assignment_number": (
            int(assignment_match.group(1))
            if assignment_match
            else None
        ),
        "limit": (
            int(limit_match.group(1))
            if limit_match
            else None
        ),
        "attendance_threshold": (
            float(threshold_match.group(1))
            if threshold_match
            else None
        ),
    }
    
    
    # Personal assignment queries should use the student's
    # own pending-assignment records, not the general
    # assignment-submission-status handler.
    if re.search(
        r"\bwhich assignments?\b.*\bnot submitted\b",
        normalized,
    ):
        return {
            "intent": "pending_assignments",
            "confidence": 0.95,
            "entities": entities,
            "original_question": question.strip(),
        }
    
    
    
    for intent_name, patterns in INTENT_RULES:
        if any(
            re.search(pattern, normalized)
            for pattern in patterns
        ):
            return {
                "intent": intent_name,
                "confidence": 0.9,
                "entities": entities,
                "original_question": question.strip(),
            }

    return {
        "intent": "general_campus_question",
        "confidence": 0.3,
        "entities": entities,
        "original_question": question.strip(),
    }