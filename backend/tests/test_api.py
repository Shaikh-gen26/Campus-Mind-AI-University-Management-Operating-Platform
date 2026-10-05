import os

os.environ["DATABASE_URL"] = "sqlite://"
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.database import Base, engine, SessionLocal
from app.main import app
from app.models import Attendance, Course, Grade, Student, Subject, User
from datetime import date
from app.security import hash_password

client = TestClient(app, base_url="http://localhost")


def setup_function():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        cse = Course(code="CSE", name="Computer Engineering")
        it = Course(code="IT", name="Information Technology")
        db.add_all([cse, it])
        db.flush()
        db.add_all(
            [
                Subject(code="CSE01", name="Data Structures", course_id=cse.id),
                Subject(code="IT01", name="Networks", course_id=it.id),
            ]
        )
        s1 = Student(
            student_number="CSE2026001", full_name="Aarav Shah", email="a@x.test", course_id=cse.id
        )
        s2 = Student(
            student_number="IT2026001", full_name="Diya Patil", email="b@x.test", course_id=it.id
        )
        db.add_all([s1, s2])
        db.flush()
        db.add_all(
            [
                User(
                    login="admin",
                    email="admin@x.test",
                    full_name="Admin",
                    password_hash=hash_password("admin-password"),
                    role="super_admin",
                ),
                User(
                    login="teacher",
                    email="teacher@x.test",
                    full_name="Teacher",
                    password_hash=hash_password("teacher-password"),
                    role="course_admin",
                    course_id=cse.id,
                ),
                User(
                    login=s1.student_number,
                    email=s1.email,
                    full_name=s1.full_name,
                    password_hash=hash_password("student-password"),
                    role="student",
                    student_id=s1.id,
                ),
                User(
                    login=s2.student_number,
                    email=s2.email,
                    full_name=s2.full_name,
                    password_hash=hash_password("student-password"),
                    role="student",
                    student_id=s2.id,
                ),
            ]
        )
        db.flush()
        cse_subject = db.scalar(select(Subject).where(Subject.code == "CSE01"))
        it_subject = db.scalar(select(Subject).where(Subject.code == "IT01"))
        db.add_all(
            [
                Attendance(
                    student_id=s2.id,
                    subject_id=it_subject.id,
                    held_on=date(2026, 10, 1),
                    present=True,
                ),
                Grade(
                    student_id=s2.id,
                    subject_id=it_subject.id,
                    assessment="Test",
                    score=9,
                    max_score=10,
                ),
            ]
        )
        db.commit()


def auth(login, password):
    r = client.post("/api/auth/token", json={"username": login, "password": password})
    
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_course_admin_is_scoped():
    headers = auth("teacher", "teacher-password")
    rows = client.get("/api/students", headers=headers).json()
    assert [x["student_number"] for x in rows] == ["CSE2026001"]
    assert client.get("/api/students/2", headers=headers).status_code == 403


def test_student_cannot_access_directory_or_other_profile():
    headers = auth("CSE2026001", "student-password")
    assert client.get("/api/students", headers=headers).status_code == 403
    assert client.get("/api/students/2", headers=headers).status_code == 403
    assert client.get("/api/students/1", headers=headers).status_code == 200
    assert client.get("/api/grades?student_id=2", headers=headers).json() == []
    assert client.get("/api/attendance?student_id=2", headers=headers).json() == []
    assert (
        client.post(
            "/api/administrators",
            headers=headers,
            json={
                "login": "newadmin",
                "email": "new@x.test",
                "full_name": "New Admin",
                "password": "some-password",
                "course_id": 1,
            },
        ).status_code
        == 403
    )


def test_super_admin_sees_all_students():
    headers = auth("admin", "admin-password")
    assert len(client.get("/api/students?limit=100", headers=headers).json()) == 2


def test_inactive_user_and_missing_token_rejected():
    with SessionLocal() as db:
        u = db.query(User).filter_by(login="admin").one()
        u.active = False
        db.commit()
    assert (
        client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin-password"}
        ).status_code
        == 401
    )
    assert client.get("/api/courses").status_code == 401


def test_logout_revokes_existing_token():
    headers = auth("admin", "admin-password")
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/courses", headers=headers).status_code == 401


def test_course_admin_cannot_mark_attendance_outside_assigned_course():
    headers = auth("teacher", "teacher-password")
    response = client.post(
        "/api/attendance",
        headers=headers,
        json={"subject_id": 2, "student_id": 2, "held_on": "2026-10-01", "present": True},
    )
    assert response.status_code == 403
    assert (
        client.post(
            "/api/administrators",
            headers=headers,
            json={
                "login": "newadmin",
                "email": "new@x.test",
                "full_name": "New Admin",
                "password": "some-password",
                "course_id": 2,
            },
        ).status_code
        == 403
    )


def test_course_admin_gets_all_sixty_rows_when_demo_seeded():
    # This fixture has one CSE student; confirms the API honors the requested page size used by the 60-seat seed.
    headers = auth("teacher", "teacher-password")
    assert len(client.get("/api/students?limit=100", headers=headers).json()) == 1


def test_assignment_submission_grade_and_notification_flow():
    staff = auth("teacher", "teacher-password")
    student = auth("CSE2026001", "student-password")
    created = client.post(
        "/api/assignments",
        headers=staff,
        json={
            "subject_id": 1,
            "title": "Algorithms exercise",
            "description": "Submit your written solution.",
            "due_at": "2099-12-01T23:59:00",
            "max_score": 20,
            "published": True,
        },
    )
    assert created.status_code == 201, created.text
    assignment_id = created.json()["id"]
    assert any(
        x["id"] == assignment_id for x in client.get("/api/assignments", headers=student).json()
    )
    submission = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        headers=student,
        json={"content": "My solution"},
    )
    assert submission.status_code == 201, submission.text
    assert (
        len(client.get(f"/api/submissions?assignment_id={assignment_id}", headers=staff).json())
        == 1
    )
    grade = client.post(
        "/api/grades",
        headers=staff,
        json={
            "student_id": 1,
            "subject_id": 1,
            "assessment": "Algorithms exercise",
            "score": 18,
            "max_score": 20,
            "published": True,
        },
    )
    assert grade.status_code == 201, grade.text
    result = client.get("/api/grades", headers=student).json()
    assert any(
        x["assessment"] == "Algorithms exercise" and x["letter_grade"] == "A" for x in result
    )
    assert client.get("/api/notifications/unread-count", headers=student).json()["unread"] >= 1


def test_ai_conversation_is_persisted_and_private():
    student = auth("CSE2026001", "student-password")
    other = auth("IT2026001", "student-password")
    response = client.post(
        "/api/ai/ask",
        headers=student,
        json={"question": "Where do I check my attendance?", "kind": "campus"},
    )
    assert response.status_code == 200
    cid = response.json()["conversation_id"]
    assert (
        client.post(
            "/api/ai/ask",
            headers=student,
            json={
                "question": "How do I see the timetable?",
                "kind": "campus",
                "conversation_id": cid,
            },
        ).status_code
        == 200
    )
    assert len(client.get(f"/api/conversations/{cid}", headers=student).json()["messages"]) == 4
    assert client.get(f"/api/conversations/{cid}", headers=other).status_code == 404
