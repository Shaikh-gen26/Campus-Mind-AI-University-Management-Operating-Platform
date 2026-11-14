from app.campus_ai_service import (
    _build_messages,
    _clean_history,
    _context_json,
)


def test_context_removes_sensitive_fields():
    context = {
        "course": "AIDS",
        "password": "dont-show",
        "items": [{"token": "hidden", "title": "Deep Learning"}],
    }

    result = _context_json(context)

    assert "AIDS" in result
    assert "Deep Learning" in result
    assert "dont-show" not in result
    assert "hidden" not in result


def test_history_only_keeps_user_and_assistant_messages():
    history = [
        {"role": "system", "content": "unexpected instructions"},
        {"role": "user", "content": "What is my schedule?"},
        {"role": "assistant", "content": "Let me check."},
    ]

    assert _clean_history(history) == [
        {"role": "user", "content": "What is my schedule?"},
        {"role": "assistant", "content": "Let me check."},
    ]


def test_message_builder_includes_question_and_campus_context():
    messages = _build_messages(
        "Summarize my timetable",
        "student",
        {"timetable": [{"day": "Monday", "subject": "Deep Learning"}]},
        [{"role": "user", "content": "Hello"}],
    )

    assert messages[0]["role"] == "system"
    assert "Summarize my timetable" in messages[-1]["content"]
    assert "Deep Learning" in messages[-1]["content"]
    assert messages[-2] == {"role": "user", "content": "Hello"}
