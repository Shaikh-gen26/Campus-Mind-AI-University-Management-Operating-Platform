
from .intelligence import (
    get_course_intelligence,
    get_student_intelligence,
    get_risk_intelligence,
)
from .campus_ai_service import CampusAIError, generate_campus_answer
from .ai.memory import (
    load_conversation,
    load_history,
    save_exchange,
)
from .ai.prompts import build_system_prompt
from .ai.context import build_query_context
from .ai.assistant import format_query_answer
from datetime import datetime
import json
import logging
import re
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest, urlopen
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy import case, func, insert, literal, select
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .database import get_db
from . import models, schemas, admin
from .security import (
    SESSION_COOKIE,
    current_user,
    create_token,
    hash_password,
    require_roles,
    verify_password,
)
from .settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("campusmind")
dummy_password_hash = hash_password("invalid-account-password-material")
is_production = settings.app_env.lower() == "production"
app = FastAPI(
    title="Campus Mind AI",
    version="1.0.0",
    description="Intelligent University Operating System API",
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json",
)


limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.app_env != "test",
)

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
)


app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )


@app.middleware("http")
async def verify_cookie_request_origin(request: Request, call_next):
    unsafe_methods = {"POST", "PUT", "PATCH", "DELETE"}
    has_session_cookie = SESSION_COOKIE in request.cookies
    if request.method in unsafe_methods and has_session_cookie:
        origin = request.headers.get("origin")
        if not origin or origin.rstrip("/") not in settings.cors_origins:
            return JSONResponse(
                status_code=403, content={"detail": "Request origin is not allowed."}
            )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cache-Control", "no-store")
    if is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response


app.include_router(admin.router)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    logger.info("Constraint conflict on %s", request.url.path)
    return JSONResponse(
        status_code=409, content={"detail": "The request conflicts with existing university data."}
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "Request validation failed."})



def scope_course(user: models.User, subject_id: int, db: Session):
    subject = db.get(models.Subject, subject_id)

    if not subject:
        raise HTTPException(404, "Subject not found")

    if user.role == "course_admin":
        assigned = db.scalar(
            select(models.TeacherSubject.id).where(
                models.TeacherSubject.teacher_id == user.id,
                models.TeacherSubject.subject_id == subject_id,
            )
        )

        if not assigned:
            raise HTTPException(403, "Outside assigned subjects")

    return subject



def notify_course_students(
    db: Session, course_id: int, title: str, body: str, notification_type: str
):
    recipients = (
        select(
            models.User.id,
            literal(title),
            literal(body[:500]),
            literal(notification_type),
            literal(course_id),
            literal(False),
            literal(models.utcnow_naive()),
        )
        .join(models.Student, models.User.student_id == models.Student.id)
        .where(
            models.Student.course_id == course_id,
            models.User.active.is_(True),
        )
    )
    db.execute(
        insert(models.Notification).from_select(
            [
                "user_id",
                "title",
                "body",
                "notification_type",
                "course_id",
                "read",
                "created_at",
            ],
            recipients,
        )
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/ready")
def readiness(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ready"}


def authenticate_user(data: schemas.Login, db: Session) -> models.User:
    user = db.scalar(
        select(models.User).where(
            (models.User.login == data.username) | (models.User.email == data.username)
        )
    )
    account_password_hash = user.password_hash if user else dummy_password_hash
    password_matches = verify_password(data.password, account_password_hash)
    if not user or not user.active or not password_matches:
        raise HTTPException(401, "Incorrect credentials or inactive account")
    return user


@app.post("/api/auth/login")
@limiter.limit("5/minute")
def login(
    request: Request,
    data: schemas.Login,
    response: Response,
    db: Session = Depends(get_db),
):
    user = authenticate_user(data, db)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_token(user),
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=is_production,
        samesite="strict",
        path="/api",
    )
    return {"user": schemas.UserOut.model_validate(user)}


@app.post("/api/auth/token")
@limiter.limit("5/minute")
def issue_api_token(
    request: Request,
    data: schemas.Login,
    db: Session = Depends(get_db),
):
    user = authenticate_user(data, db)
    return {
        "access_token": create_token(user),
        "token_type": "bearer",
        "user": schemas.UserOut.model_validate(user),
    }


@app.post("/api/auth/logout")
def logout(
    response: Response, db: Session = Depends(get_db), user: models.User = Depends(current_user)
):
    user.token_version += 1
    db.commit()
    response.delete_cookie(
        key=SESSION_COOKIE, path="/api", secure=is_production, httponly=True, samesite="strict"
    )
    return {"message": "Session revoked"}


@app.get("/api/auth/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(current_user)):
    return user


@app.patch("/api/profile", response_model=schemas.UserOut)
def update_profile(
    data: schemas.ProfileUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    if db.scalar(
        select(models.User.id).where(models.User.email == data.email, models.User.id != user.id)
    ):
        raise HTTPException(409, "Email already in use")
    user.full_name, user.email = data.full_name, data.email
    if user.role == "student" and user.student_id:
        student = db.get(models.Student, user.student_id)
        if student:
            student.full_name, student.email = data.full_name, data.email
    db.commit()
    db.refresh(user)
    return user


@app.get("/api/courses")
def courses(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    q = select(models.Course)
    if user.role == "course_admin":
        q = q.where(models.Course.id == user.course_id)
    if user.role == "student":
        student = db.get(models.Student, user.student_id)
        q = q.where(models.Course.id == student.course_id if student else models.Course.id == -1)
    return [{"id": c.id, "code": c.code, "name": c.name} for c in db.scalars(q).all()]


@app.get("/api/students")
def students(
    search: str = "",
    course_id: int | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    if user.role == "student":
        raise HTTPException(403, "Student directory is restricted")
    q = select(models.Student)
    if user.role == "course_admin":
        q = q.where(models.Student.course_id == user.course_id)
    elif course_id:
        q = q.where(models.Student.course_id == course_id)
    if search:
        q = q.where(
            models.Student.full_name.ilike(f"%{search}%")
            | models.Student.student_number.ilike(f"%{search}%")
        )
    rows = db.scalars(q.order_by(models.Student.student_number).offset(offset).limit(limit)).all()
    return [
        {
            "id": s.id,
            "student_number": s.student_number,
            "full_name": s.full_name,
            "email": s.email,
            "course_id": s.course_id,
            "year": s.year,
            "active": bool(
                db.scalar(select(models.User.active).where(models.User.student_id == s.id))
            ),
        }
        for s in rows
    ]


@app.post("/api/students", status_code=201)
def create_student(
    data: schemas.StudentCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("super_admin")),
):
    course = db.get(models.Course, data.course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    if not data.student_number.upper().startswith(course.code):
        raise HTTPException(422, "Student ID must begin with the assigned course code")
    if db.scalar(
        select(models.Student.id).where(
            (models.Student.student_number == data.student_number)
            | (models.Student.email == data.email)
        )
    ) or db.scalar(
        select(models.User.id).where(
            (models.User.login == data.student_number) | (models.User.email == data.email)
        )
    ):
        raise HTTPException(409, "Student ID or email already exists")
    s = models.Student(**data.model_dump(exclude={"password"}))
    db.add(s)
    db.flush()
    db.add(
        models.User(
            login=s.student_number,
            email=s.email,
            full_name=s.full_name,
            password_hash=hash_password(data.password),
            role="student",
            student_id=s.id,
        )
    )
    db.commit()
    return {"id": s.id, "student_number": s.student_number}


@app.get("/api/students/{student_id}")
def student_detail(
    student_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)
):
    s = db.get(models.Student, student_id)
    if not s:
        raise HTTPException(404, "Student not found")
    if user.role == "student" and user.student_id != s.id:
        raise HTTPException(403, "Student records are private")
    if user.role == "course_admin" and user.course_id != s.course_id:
        raise HTTPException(403, "Outside assigned course")
    return {
        "id": s.id,
        "student_number": s.student_number,
        "full_name": s.full_name,
        "email": s.email,
        "course_id": s.course_id,
        "year": s.year,
    }



@app.get("/api/subjects")
def subjects(
    course_id: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    if user.role == "student":
        student = db.get(models.Student, user.student_id)
        course_id = student.course_id if student else -1

    q = select(models.Subject)

    if user.role == "course_admin":
        q = (
            q.join(
                models.TeacherSubject,
                models.TeacherSubject.subject_id == models.Subject.id,
            )
            .where(models.TeacherSubject.teacher_id == user.id)
        )
    elif course_id:
        q = q.where(models.Subject.course_id == course_id)

    return [
        {
            "id": x.id,
            "code": x.code,
            "name": x.name,
            "course_id": x.course_id,
        }
        for x in db.scalars(q.order_by(models.Subject.code)).all()
    ]



@app.get("/api/attendance")
def attendance(
    student_id: int | None = None,
    subject_id: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    if user.role == "student":
        if user.student_id is None:
            raise HTTPException(403, "Student profile is unavailable")
        student_id = user.student_id
    q = select(models.Attendance)
    if student_id:
        q = q.where(models.Attendance.student_id == student_id)
    if subject_id:
        scope_course(user, subject_id, db)
        q = q.where(models.Attendance.subject_id == subject_id)
    
    if user.role == "course_admin":
        q = q.join(
            models.TeacherSubject,
            models.TeacherSubject.subject_id == models.Attendance.subject_id,
        ).where(
            models.TeacherSubject.teacher_id == user.id
        )
    
    return [
        {
            "id": a.id,
            "student_id": a.student_id,
            "subject_id": a.subject_id,
            "held_on": a.held_on,
            "present": a.present,
        }
        for a in db.scalars(q).all()
    ]


@app.get("/api/attendance/summary")
def attendance_summary(
    student_id: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    if user.role == "student":
        student_id = user.student_id
    q = (
        select(
            models.Subject.id,
            models.Subject.name,
            func.count(models.Attendance.id),
            func.sum(case((models.Attendance.present.is_(True), 1), else_=0)),
        )
        .join(models.Attendance, models.Attendance.subject_id == models.Subject.id, isouter=True)
        .group_by(models.Subject.id, models.Subject.name)
    )
    
    
    if user.role == "course_admin":
        q = q.join(
            models.TeacherSubject,
            models.TeacherSubject.subject_id == models.Subject.id,
        ).where(
            models.TeacherSubject.teacher_id == user.id
        )
    
    
    elif user.role == "student":
        student = db.get(models.Student, user.student_id)
        q = q.where(
            models.Subject.course_id == (student.course_id if student else -1),
            models.Attendance.student_id == student_id,
        )
    elif student_id:
        q = q.where(models.Attendance.student_id == student_id)
    return [
        {
            "subject_id": r[0],
            "subject": r[1],
            "classes": int(r[2] or 0),
            "present": int(r[3] or 0),
            "percentage": round(100 * int(r[3] or 0) / int(r[2] or 1)),
        }
        for r in db.execute(q).all()
    ]


@app.post("/api/attendance", status_code=201)
def mark_attendance(
    data: schemas.AttendanceMark,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "course_admin")),
):
    subject = scope_course(user, data.subject_id, db)
    student = db.get(models.Student, data.student_id)
    if not student or student.course_id != subject.course_id:
        raise HTTPException(400, "Student is not enrolled in this subject's course")
    row = db.scalar(
        select(models.Attendance).where(
            models.Attendance.student_id == data.student_id,
            models.Attendance.subject_id == data.subject_id,
            models.Attendance.held_on == data.held_on,
        )
    )
    if row:
        row.present = data.present
    else:
        row = models.Attendance(**data.model_dump())
        db.add(row)
    db.commit()
    return {"id": row.id, "updated": True}


@app.get("/api/assignments")
def assignments(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    q = select(models.Assignment).join(models.Subject).where(models.Assignment.archived.is_(False))
    if user.role == "student":
        student = db.get(models.Student, user.student_id) if user.student_id else None
        if not student:
            raise HTTPException(403, "Student profile is unavailable")
        q = q.where(
            models.Subject.course_id == student.course_id, models.Assignment.published.is_(True)
        )
    
    if user.role == "course_admin":
        q = q.join(
            models.TeacherSubject,
            models.TeacherSubject.subject_id == models.Subject.id,
        ).where(
            models.TeacherSubject.teacher_id == user.id
        )
    
    
    rows = db.scalars(q.order_by(models.Assignment.due_at)).all()
    if user.role == "student":
        return [
            {
                "id": a.id,
                "title": a.title,
                "description": a.description,
                "due_at": a.due_at,
                "subject_id": a.subject_id,
                "subject": db.get(models.Subject, a.subject_id).name,
                "max_score": a.max_score,
                "submitted": db.scalar(
                    select(models.Submission.id).where(
                        models.Submission.assignment_id == a.id,
                        models.Submission.student_id == user.student_id,
                    )
                )
                is not None,
                "status": (
                    "submitted"
                    if db.scalar(
                        select(models.Submission.id).where(
                            models.Submission.assignment_id == a.id,
                            models.Submission.student_id == user.student_id,
                        )
                    )
                    else "late" if a.due_at < datetime.now() else "pending"
                ),
            }
            for a in rows
        ]
    return [
        {
            "id": a.id,
            "title": a.title,
            "description": a.description,
            "due_at": a.due_at,
            "subject_id": a.subject_id,
            "subject": db.get(models.Subject, a.subject_id).name,
            "max_score": a.max_score,
            "published": a.published,
        }
        for a in rows
    ]


@app.post("/api/assignments", status_code=201)
def create_assignment(
    data: schemas.AssignmentCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "course_admin")),
):
    subject = scope_course(user, data.subject_id, db)
    row = models.Assignment(**data.model_dump(), created_by=user.id)
    db.add(row)
    db.flush()
    if row.published:
        notify_course_students(
            db,
            subject.course_id,
            f"New assignment: {row.title}",
            f"Due {row.due_at:%d %b %Y}. Open Assignments for instructions.",
            "assignment",
        )
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@app.patch("/api/assignments/{assignment_id}")
def update_assignment(
    assignment_id: int,
    data: schemas.AssignmentUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "course_admin")),
):
    row = db.get(models.Assignment, assignment_id)
    if not row:
        raise HTTPException(404, "Assignment not found")
    subject = scope_course(user, row.subject_id, db)
    was_published = row.published
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    if row.published and not was_published:
        notify_course_students(
            db,
            subject.course_id,
            f"New assignment: {row.title}",
            f"Due {row.due_at:%d %b %Y}. Open Assignments for instructions.",
            "assignment",
        )
    db.commit()
    return {"id": row.id, "updated": True}


@app.delete("/api/assignments/{assignment_id}", status_code=204)
def archive_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "course_admin")),
):
    row = db.get(models.Assignment, assignment_id)
    if not row:
        raise HTTPException(404, "Assignment not found")
    scope_course(user, row.subject_id, db)
    row.archived = True
    row.published = False
    db.commit()


@app.post("/api/assignments/{assignment_id}/submissions", status_code=201)
def submit(
    assignment_id: int,
    data: schemas.SubmissionCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("student")),
):
    student = db.get(models.Student, user.student_id)
    task = db.get(models.Assignment, assignment_id)
    if not task or db.get(models.Subject, task.subject_id).course_id != student.course_id:
        raise HTTPException(404, "Assignment not found")
    if task.due_at < datetime.now():
        raise HTTPException(400, "Assignment deadline has passed")
    row = db.scalar(
        select(models.Submission).where(
            models.Submission.assignment_id == assignment_id,
            models.Submission.student_id == student.id,
        )
    )
    if row:
        row.content = data.content
        row.submitted_at = models.utcnow_naive()
    else:
        row = models.Submission(
            assignment_id=assignment_id, student_id=student.id, content=data.content
        )
        db.add(row)
    db.commit()
    return {"id": row.id, "submitted_at": row.submitted_at}


@app.get("/api/grades")
def grades(
    student_id: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    if user.role == "student":
        if user.student_id is None:
            raise HTTPException(403, "Student profile is unavailable")
        student_id = user.student_id
    q = select(models.Grade)
    if student_id:
        q = q.where(models.Grade.student_id == student_id)
    if user.role == "student":
        q = q.where(models.Grade.published.is_(True))
    
    if user.role == "course_admin":
        q = q.join(
            models.TeacherSubject,
            models.TeacherSubject.subject_id == models.Grade.subject_id,
        ).where(
            models.TeacherSubject.teacher_id == user.id
        )
    
    
    return [
        {
            "id": g.id,
            "student_id": g.student_id,
            "subject_id": g.subject_id,
            "assessment": g.assessment,
            "score": g.score,
            "max_score": g.max_score,
            "published": g.published,
            "letter_grade": (
                "A"
                if g.score / g.max_score >= 0.9
                else (
                    "B"
                    if g.score / g.max_score >= 0.8
                    else (
                        "C"
                        if g.score / g.max_score >= 0.7
                        else "D" if g.score / g.max_score >= 0.6 else "F"
                    )
                )
            ),
        }
        for g in db.scalars(q).all()
    ]


@app.post("/api/grades", status_code=201)
def add_grade(
    data: schemas.GradeCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "course_admin")),
):
    subject = scope_course(user, data.subject_id, db)
    student = db.get(models.Student, data.student_id)
    if not student or student.course_id != subject.course_id:
        raise HTTPException(400, "Student is not enrolled in this course")
    if data.score > data.max_score:
        raise HTTPException(422, "Score exceeds maximum")
    row = models.Grade(**data.model_dump())
    db.add(row)
    db.flush()
    if row.published:
        recipient = db.scalar(select(models.User).where(models.User.student_id == student.id))
        if recipient:
            db.add(
                models.Notification(
                    user_id=recipient.id,
                    title="A grade has been published",
                    body=f"{row.assessment} is now available in Grades.",
                    notification_type="grade",
                    course_id=student.course_id,
                )
            )
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@app.patch("/api/grades/{grade_id}")
def update_grade(
    grade_id: int,
    data: schemas.GradeUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "course_admin")),
):
    row = db.get(models.Grade, grade_id)
    if not row:
        raise HTTPException(404, "Grade not found")
    scope_course(user, row.subject_id, db)
    if data.score > data.max_score:
        raise HTTPException(422, "Score exceeds maximum")
    was_published = row.published
    row.score, row.max_score, row.published = data.score, data.max_score, data.published
    if row.published and not was_published:
        recipient = db.scalar(select(models.User).where(models.User.student_id == row.student_id))
        student = db.get(models.Student, row.student_id)
        if recipient and student:
            db.add(
                models.Notification(
                    user_id=recipient.id,
                    title="A grade has been published",
                    body=f"{row.assessment} is now available in Grades.",
                    notification_type="grade",
                    course_id=student.course_id,
                )
            )
    db.commit()
    return {"id": row.id, "updated": True}


@app.get("/api/faqs")
def faqs(
    query: str = "",
    category_id: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    q = select(models.FAQ)
    if user.role != "super_admin":
        q = q.where(models.FAQ.published.is_(True))
    if query.strip():
        q = q.where(
            models.FAQ.question.ilike(f"%{query.strip()}%")
            | models.FAQ.answer.ilike(f"%{query.strip()}%")
        )
    if category_id:
        q = q.where(models.FAQ.category_id == category_id)
    return [
        {
            "id": f.id,
            "category_id": f.category_id,
            "category": db.get(models.FAQCategory, f.category_id).name,
            "question": f.question,
            "answer": f.answer,
            "published": f.published,
            "featured": f.featured,
        }
        for f in db.scalars(q.order_by(models.FAQ.question)).all()
    ]


@app.get("/api/analytics/overview")
def analytics(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "course_admin")),
):
    q = select(models.Course.id, models.Course.code, func.count(models.Student.id)).outerjoin(
        models.Student
    )
    if user.role == "course_admin":
        q = q.where(models.Course.id == user.course_id)
    rows = db.execute(q.group_by(models.Course.id, models.Course.code)).all()
    
    conditions = []
    if user.role == "course_admin":
        conditions = [
            models.Subject.id.in_(
                select(models.TeacherSubject.subject_id).where(
                    models.TeacherSubject.teacher_id == user.id
                )
            )
        ]
    
    attq = select(
        func.count(models.Attendance.id),
        func.sum(case((models.Attendance.present.is_(True), 1), else_=0)),
    ).join(models.Subject)
    if conditions:
        attq = attq.where(*conditions)
    attendance_total, present_total = db.execute(attq).one()
    student_total = db.scalar(
        select(func.count(models.Student.id)).where(models.Student.course_id == user.course_id)
        if user.role == "course_admin"
        else select(func.count(models.Student.id))
    )
    assignment_q = (
        select(func.count(models.Assignment.id))
        .join(models.Subject)
        .where(models.Assignment.archived.is_(False), models.Assignment.published.is_(True))
    )
    submission_q = (
        select(func.count(models.Submission.id))
        .join(models.Assignment)
        .join(models.Subject)
        .where(models.Assignment.archived.is_(False), models.Assignment.published.is_(True))
    )
    grade_q = select(func.avg(models.Grade.score * 100.0 / models.Grade.max_score)).join(
        models.Subject
    )
    
    if user.role == "course_admin":
        assigned_subject_ids = select(
            models.TeacherSubject.subject_id
        ).where(
            models.TeacherSubject.teacher_id == user.id
        )

        assignment_q = assignment_q.where(
            models.Assignment.subject_id.in_(assigned_subject_ids)
        )

        submission_q = submission_q.where(
            models.Assignment.subject_id.in_(assigned_subject_ids)
        )

        grade_q = grade_q.where(
            models.Grade.subject_id.in_(assigned_subject_ids)
        )
    
    assignment_count = int(db.scalar(assignment_q) or 0)
    submission_count = int(db.scalar(submission_q) or 0)
    expected_submissions = assignment_count * int(student_total or 0)
    average_marks = db.scalar(grade_q)
    risk_q = (
        select(
            models.Student.id,
            models.Student.student_number,
            models.Student.full_name,
            models.Course.code,
            func.count(models.Attendance.id),
            func.sum(case((models.Attendance.present.is_(True), 1), else_=0)),
        )
        .join(models.Course)
        .outerjoin(models.Attendance)
        .group_by(
            models.Student.id,
            models.Student.student_number,
            models.Student.full_name,
            models.Course.code,
        )
    )
    if user.role == "course_admin":
        risk_q = risk_q.where(models.Student.course_id == user.course_id)
    risk_q = (
        risk_q.having(func.count(models.Attendance.id) > 0)
        .having(
            func.sum(case((models.Attendance.present.is_(True), 1), else_=0))
            * 100.0
            / func.count(models.Attendance.id)
            < settings.attendance_alert_threshold
        )
        .order_by(
            func.sum(case((models.Attendance.present.is_(True), 1), else_=0))
            * 1.0
            / func.count(models.Attendance.id)
        )
        .limit(20)
    )
    risks = [
        {
            "student_id": r[0],
            "student_number": r[1],
            "full_name": r[2],
            "course": r[3],
            "attendance_percent": round(100 * int(r[5] or 0) / int(r[4] or 1)),
        }
        for r in db.execute(risk_q).all()
    ]
    top_q = (
        select(
            models.Student.id,
            models.Student.student_number,
            models.Student.full_name,
            models.Course.code,
            func.avg(models.Grade.score * 100.0 / models.Grade.max_score),
        )
        .join(models.Grade, models.Grade.student_id == models.Student.id)
        .join(models.Course)
        .where(models.Grade.published.is_(True))
        .group_by(
            models.Student.id,
            models.Student.student_number,
            models.Student.full_name,
            models.Course.code,
        )
    )
    if user.role == "course_admin":
        top_q = top_q.where(models.Student.course_id == user.course_id)
    top_performers = [
        {
            "student_id": r[0],
            "student_number": r[1],
            "full_name": r[2],
            "course": r[3],
            "average_marks_percent": round(float(r[4]), 1),
        }
        for r in db.execute(
            top_q.order_by(
                func.avg(models.Grade.score * 100.0 / models.Grade.max_score).desc()
            ).limit(10)
        ).all()
    ]
    activity_q = (
        select(models.Notification).order_by(models.Notification.created_at.desc()).limit(8)
    )
    if user.role == "course_admin":
        activity_q = activity_q.where(
            (models.Notification.course_id == user.course_id)
            | (models.Notification.course_id.is_(None))
        )
    activity = [
        {"title": n.title, "created_at": n.created_at, "notification_type": n.notification_type}
        for n in db.scalars(activity_q).all()
    ]
    return {
        "courses": [{"course_id": r[0], "code": r[1], "students": r[2]} for r in rows],
        "student_total": student_total,
        "attendance_percent": round(100 * int(present_total or 0) / int(attendance_total or 1)),
        "attendance_records": int(attendance_total or 0),
        "active_users": db.scalar(
            select(func.count(models.User.id)).where(models.User.active.is_(True))
            if user.role == "super_admin"
            else select(func.count(models.User.id)).where(
                models.User.active.is_(True), models.User.course_id == user.course_id
            )
        ),
        "average_marks_percent": (
            round(float(average_marks), 1) if average_marks is not None else None
        ),
        "assignment_completion_percent": (
            round(100 * submission_count / expected_submissions) if expected_submissions else 0
        ),
        "submissions": submission_count,
        "expected_submissions": expected_submissions,
        "attendance_risk_students": risks,
        "top_performers": top_performers,
        "recent_activity": activity,
        "attendance_alert_threshold": settings.attendance_alert_threshold,
    }


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    now = datetime.now()
    announcements_query = (
        select(models.Announcement)
        .where(models.Announcement.published.is_(True))
        .order_by(models.Announcement.published_at.desc())
        .limit(5)
    )
    if user.role == "super_admin":
        return {
            "role": user.role,
            "student_total": db.scalar(select(func.count(models.Student.id))),
            "course_total": db.scalar(select(func.count(models.Course.id))),
            "admin_total": db.scalar(
                select(func.count(models.User.id)).where(
                    models.User.role == "course_admin", models.User.active.is_(True)
                )
            ),
            "attendance": db.scalar(
                select(func.avg(models.Attendance.present.cast(models.Integer)))
            ),
            "announcements": [
                {"id": a.id, "title": a.title, "body": a.body}
                for a in db.scalars(announcements_query).all()
            ],
            "events": [
                {"id": e.id, "title": e.title, "starts_at": e.starts_at}
                for e in db.scalars(
                    select(models.Event)
                    .where(models.Event.starts_at >= now)
                    .order_by(models.Event.starts_at)
                    .limit(5)
                ).all()
            ],
        }
    if user.role == "course_admin":
        course_id = user.course_id
        student_count = db.scalar(
            select(func.count(models.Student.id)).where(models.Student.course_id == course_id)
        )
        total, present = db.execute(
            select(
                func.count(models.Attendance.id),
                func.sum(case((models.Attendance.present.is_(True), 1), else_=0)),
            )
            .join(models.Student)
            .where(models.Student.course_id == course_id)
        ).one()
        assignment_total = (
            db.scalar(
                select(func.count(models.Assignment.id))
                .join(models.Subject)
                .where(
                    models.Subject.course_id == course_id,
                    models.Assignment.archived.is_(False),
                    models.Assignment.published.is_(True),
                )
            )
            or 0
        )
        submission_total = (
            db.scalar(
                select(func.count(models.Submission.id))
                .join(models.Assignment)
                .join(models.Subject)
                .where(
                    models.Subject.course_id == course_id,
                    models.Assignment.archived.is_(False),
                    models.Assignment.published.is_(True),
                )
            )
            or 0
        )
        average_marks = db.scalar(
            select(func.avg(models.Grade.score * 100.0 / models.Grade.max_score))
            .join(models.Subject)
            .where(models.Subject.course_id == course_id)
        )
        return {
            "role": user.role,
            "course_id": course_id,
            "student_total": student_count,
            "attendance_percent": round(100 * int(present or 0) / int(total or 1)),
            "assignment_total": assignment_total,
            "assignment_completion_percent": (
                round(100 * submission_total / (assignment_total * int(student_count or 0)))
                if assignment_total and student_count
                else 0
            ),
            "average_marks_percent": (
                round(float(average_marks), 1) if average_marks is not None else None
            ),
            "announcements": [
                {"id": a.id, "title": a.title, "body": a.body}
                for a in db.scalars(
                    announcements_query.where(
                        (models.Announcement.course_id == course_id)
                        | (models.Announcement.course_id.is_(None))
                    )
                ).all()
            ],
        }
    student = db.get(models.Student, user.student_id)
    if not student:
        raise HTTPException(403, "Student profile is unavailable")
    total, present = db.execute(
        select(
            func.count(models.Attendance.id),
            func.sum(case((models.Attendance.present.is_(True), 1), else_=0)),
        ).where(models.Attendance.student_id == student.id)
    ).one()
    submitted = select(models.Submission.assignment_id).where(
        models.Submission.student_id == student.id
    )
    pending = db.scalar(
        select(func.count(models.Assignment.id))
        .join(models.Subject)
        .where(
            models.Subject.course_id == student.course_id,
            models.Assignment.due_at >= now,
            models.Assignment.id.not_in(submitted),
        )
    )
    average_marks = db.scalar(
        select(func.avg(models.Grade.score * 100.0 / models.Grade.max_score)).where(
            models.Grade.student_id == student.id, models.Grade.published.is_(True)
        )
    )
    attendance_percent = round(100 * int(present or 0) / int(total or 1))
    course_announcement_query = announcements_query.where(
        (models.Announcement.course_id == student.course_id)
        | (models.Announcement.course_id.is_(None))
    )
    return {
        "role": user.role,
        "student_id": student.id,
        "student_name": student.full_name,
        "course_id": student.course_id,
        "attendance_percent": attendance_percent,
        "attendance_warning": bool(
            total and attendance_percent < settings.attendance_alert_threshold
        ),
        "attendance_alert_threshold": settings.attendance_alert_threshold,
        "average_marks_percent": (
            round(float(average_marks), 1) if average_marks is not None else None
        ),
        "pending_assignments": pending,
        "upcoming_exams": db.scalar(
            select(func.count(models.Exam.id))
            .join(models.Subject)
            .where(models.Subject.course_id == student.course_id, models.Exam.starts_at >= now)
        ),
        "announcements": [
            {"id": a.id, "title": a.title, "body": a.body}
            for a in db.scalars(course_announcement_query).all()
        ],
        "events": [
            {"id": e.id, "title": e.title, "starts_at": e.starts_at}
            for e in db.scalars(
                select(models.Event)
                .where(models.Event.starts_at >= now)
                .order_by(models.Event.starts_at)
                .limit(5)
            ).all()
        ],
    }


@app.get("/api/submissions")
def submissions(
    assignment_id: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "course_admin")),
):
    q = select(models.Submission).join(models.Assignment).join(models.Subject)
    
    
    if user.role == "course_admin":
        q = q.join(
            models.TeacherSubject,
            models.TeacherSubject.subject_id == models.Subject.id,
        ).where(
            models.TeacherSubject.teacher_id == user.id
        )
        
        
    if assignment_id:
        q = q.where(models.Submission.assignment_id == assignment_id)
    return [
        {
            "id": s.id,
            "assignment_id": s.assignment_id,
            "student_id": s.student_id,
            "content": s.content,
            "submitted_at": s.submitted_at,
        }
        for s in db.scalars(q).all()
    ]



@app.get("/api/timetable")
def timetable(
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    course_id = user.course_id

    if user.role == "student":
        student = db.get(models.Student, user.student_id)
        course_id = student.course_id if student else -1

    if user.role == "course_admin":
        q = (
            select(models.Timetable, models.Subject)
            .join(models.Subject)
            .join(
                models.TeacherSubject,
                models.TeacherSubject.subject_id == models.Subject.id,
            )
            .where(
                models.TeacherSubject.teacher_id == user.id
            )
        )
    else:
        q = (
            select(models.Timetable, models.Subject)
            .join(models.Subject)
            .where(models.Subject.course_id == course_id)
            if course_id
            else select(models.Timetable, models.Subject)
        )

    return [
        {
            "id": t.id,
            "subject": s.name,
            "weekday": t.weekday,
            "starts_at": t.starts_at,
            "ends_at": t.ends_at,
            "room": t.room,
            "faculty": t.faculty,
        }
        for t, s in db.execute(q).all()
    ]




@app.get("/api/exams")
def exams(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    course_id = user.course_id

    if user.role == "student":
        student = db.get(models.Student, user.student_id)
        course_id = student.course_id if student else -1

    if user.role == "course_admin":
        q = (
            select(models.Exam, models.Subject)
            .join(models.Subject)
            .join(
                models.TeacherSubject,
                models.TeacherSubject.subject_id == models.Subject.id,
            )
            .where(
                models.TeacherSubject.teacher_id == user.id
            )
        )
    else:
        q = (
            select(models.Exam, models.Subject)
            .join(models.Subject)
            .where(models.Subject.course_id == course_id)
            if course_id
            else select(models.Exam, models.Subject)
        )

    return [
        {
            "id": e.id,
            "title": e.title,
            "subject": s.name,
            "starts_at": e.starts_at,
            "room": e.room,
            "status": (
                "completed"
                if e.starts_at < datetime.now() and e.status == "scheduled"
                else e.status
            ),
        }
        for e, s in db.execute(q).all()
    ]




@app.get("/api/announcements")
def announcements(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    q = select(models.Announcement)
    if user.role != "super_admin":
        q = q.where(models.Announcement.published.is_(True))
    if user.role == "course_admin":
        q = q.where(
            (models.Announcement.course_id == user.course_id)
            | (models.Announcement.course_id.is_(None))
        )
    if user.role == "student":
        student = db.get(models.Student, user.student_id)
        cid = student.course_id if student else -1
        q = q.where(
            (models.Announcement.course_id == cid) | (models.Announcement.course_id.is_(None))
        )
    return [
        {
            "id": a.id,
            "title": a.title,
            "body": a.body,
            "course_id": a.course_id,
            "published_at": a.published_at,
            "updated_at": a.updated_at,
            "author_id": a.author_id,
            "published": a.published,
        }
        for a in db.scalars(q.order_by(models.Announcement.published_at.desc())).all()
    ]


@app.get("/api/events")
def events(db: Session = Depends(get_db), _: models.User = Depends(current_user)):
    return [
        {
            "id": e.id,
            "title": e.title,
            "description": e.description,
            "starts_at": e.starts_at,
            "location": e.location,
        }
        for e in db.scalars(select(models.Event).order_by(models.Event.starts_at)).all()
    ]


@app.get("/api/notifications")
def notifications(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    return [
        {
            "id": n.id,
            "title": n.title,
            "body": n.body,
            "read": n.read,
            "notification_type": n.notification_type,
            "course_id": n.course_id,
            "created_at": n.created_at,
        }
        for n in db.scalars(
            select(models.Notification)
            .where(models.Notification.user_id == user.id)
            .order_by(models.Notification.created_at.desc())
        ).all()
    ]


@app.get("/api/notifications/unread-count")
def unread_notifications(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    return {
        "unread": db.scalar(
            select(func.count(models.Notification.id)).where(
                models.Notification.user_id == user.id, models.Notification.read.is_(False)
            )
        )
        or 0
    }


@app.get("/api/intelligence/overview")
def intelligence_overview(
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    if user.role == "student":
        return get_student_intelligence(db, user)

    return get_course_intelligence(db, user)


@app.get("/api/intelligence/risk")
def intelligence_risk(
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    return get_risk_intelligence(db, user)



@app.post("/api/ai/ask")
def ask(
    data: schemas.Ask, db: Session = Depends(get_db), user: models.User = Depends(current_user)
):
    
    conv = load_conversation(
        db=db,
        user=user,
        conversation_id=data.conversation_id,
        kind=data.kind,
    )

    history = load_history(db=db, conversation=conv)
    
    # New role-aware academic intelligence pipeline.
    # The existing campus FAQ mode remains unchanged.
    structured_query_context = None
    formatted_academic_answer = None

    if data.kind == "academic":
        structured_query_context = build_query_context(
            db=db,
            user=user,
            question=data.question,
            history=history,
        )

        # Only use the new response pipeline when it retrieved data.
        # Otherwise, let the existing handler process the question.
        if structured_query_context.get("data") is not None:
            formatted_academic_answer = format_query_answer(
                structured_query_context
            )
    
    
    stop = {
        "what",
        "when",
        "where",
        "which",
        "please",
        "could",
        "would",
        "about",
        "from",
        "with",
        "your",
        "have",
        "this",
        "that",
        "does",
        "tell",
        "show",
        "mine",
        "my",
        "the",
        "and",
        "for",
    }
    terms = {
        x for x in re.findall(r"[a-z0-9]+", data.question.lower()) if len(x) > 2 and x not in stop
    }
    hits = db.scalars(select(models.FAQ).where(models.FAQ.published.is_(True))).all()
    ranked = sorted(
        (
            (len(terms & set(re.findall(r"[a-z0-9]+", (f.question + " " + f.answer).lower()))), f)
            for f in hits
        ),
        key=lambda x: x[0],
        reverse=True,
    )
    relevant = [f for score, f in ranked if score > 0][:4]
    context = "\n".join(f"FAQ: {f.question}\nAnswer: {f.answer}" for f in relevant)
    academic_response = ""
    authorization_denied = False 
    question_terms = set(re.findall(r"[a-z0-9]+", data.question.lower()))
    # ---------------------------------------------------------
    # Initialize database-grounded query variables
    # These are used by deterministic AI queries for all roles.
    # ---------------------------------------------------------
    attendance_rows = []
    assignment_rows = []
    grade_rows = []
    student_rows = []
    assigned_subject_ids = []
    assigned_subject_names = []
    course = None
    student_count = 0
    
    
    if user.role == "super_admin":
        course_rows = db.execute(
            select(models.Course.code, func.count(models.Student.id))
            .outerjoin(models.Student)
            .group_by(models.Course.id, models.Course.code)
        ).all()
        student_count = sum(int(row[1]) for row in course_rows)
        
        
        
        # ---------------------------------------------------------
        # University-wide academic data for deterministic queries
        # ---------------------------------------------------------

        student_rows = db.execute(
            select(
                models.Student.id,
                models.Student.student_number,
                models.Student.full_name,
                models.Student.email,
                models.Student.year,
            )
            .order_by(models.Student.full_name)
        ).all()

        assigned_subject_rows = db.execute(
            select(
                models.Subject.id,
                models.Subject.code,
                models.Subject.name,
            )
            .order_by(models.Subject.code)
        ).all()

        assigned_subject_ids = [
            row[0] for row in assigned_subject_rows
        ]

        assigned_subject_names = [
            f"{row[1]} - {row[2]}"
            for row in assigned_subject_rows
        ]

        attendance_rows = db.execute(
            select(
                models.Student.id,
                models.Student.full_name,
                models.Subject.id,
                models.Subject.name,
                func.count(models.Attendance.id),
                func.sum(
                    case(
                        (models.Attendance.present.is_(True), 1),
                        else_=0,
                    )
                ),
            )
            .join(
                models.Attendance,
                models.Attendance.student_id == models.Student.id,
            )
            .join(
                models.Subject,
                models.Subject.id == models.Attendance.subject_id,
            )
            .group_by(
                models.Student.id,
                models.Student.full_name,
                models.Subject.id,
                models.Subject.name,
            )
            .order_by(
                models.Student.full_name,
                models.Subject.name,
            )
        ).all()

        assignment_rows = db.execute(
            select(
                models.Assignment.id,
                models.Assignment.title,
                models.Assignment.due_at,
                models.Subject.name,
            )
            .join(
                models.Subject,
                models.Subject.id == models.Assignment.subject_id,
            )
            .where(
                models.Assignment.published.is_(True),
                models.Assignment.archived.is_(False),
            )
            .order_by(models.Assignment.due_at.desc())
        ).all()

        grade_rows = db.execute(
            select(
                models.Student.id,
                models.Student.full_name,
                models.Subject.name,
                models.Grade.assessment,
                models.Grade.score,
                models.Grade.max_score,
            )
            .join(
                models.Student,
                models.Student.id == models.Grade.student_id,
            )
            .join(
                models.Subject,
                models.Subject.id == models.Grade.subject_id,
            )
            .where(
                models.Grade.published.is_(True),
            )
            .order_by(
                models.Student.full_name,
                models.Subject.name,
            )
        ).all()
        
        
        
        context += (
            f"\n\nAuthorized university context: {student_count} enrolled students across {len(course_rows)} courses; {db.scalar(select(func.count(models.User.id)).where(models.User.role == 'course_admin', models.User.active.is_(True)))} active Course Admin accounts. Enrollment: "
            + ", ".join(f"{code} {count}" for code, count in course_rows)
        )
        
        if question_terms & {
            "student",
            "students",
            "enrolled",
            "enrollment",
            "university",
            "total",
            "many",
        }:
            academic_response = (
                f"There are {student_count} students enrolled across {len(course_rows)} courses. "
                + ", ".join(f"{code}: {count}" for code, count in course_rows)
                + "."
            )
    
    
    
    
            
    elif user.role == "course_admin" and user.course_id:
        course = db.get(models.Course, user.course_id)
        
        attendance_rows = []
        assignment_rows = []
        grade_rows = []
        
        # ---------------------------------------------------------
        # Authorized subjects for this Course Admin
        # ---------------------------------------------------------
        assigned_subject_rows = db.execute(
            select(models.Subject.id, models.Subject.code, models.Subject.name)
            .join(
                models.TeacherSubject,
                models.TeacherSubject.subject_id == models.Subject.id,
            )
            .where(
                models.TeacherSubject.teacher_id == user.id,
                models.Subject.course_id == user.course_id,
            )
            .order_by(models.Subject.name)
        ).all()

        assigned_subject_ids = [row[0] for row in assigned_subject_rows]

        assigned_subject_names = [
            f"{row[1]} - {row[2]}"
            for row in assigned_subject_rows
        ]
        
        
        # ---------------------------------------------------------
        # Explicit subject authorization check
        # Prevent Course Admins from asking for data belonging
        # to subjects that are not assigned to them.
        # ---------------------------------------------------------
        # authorization_denied = False

        normalized_question = re.sub(
            r"[^a-z0-9]+",
            " ",
            data.question.lower(),
        ).strip()

        all_course_subjects = db.scalars(
            select(models.Subject).where(
                models.Subject.course_id == user.course_id
            )
        ).all()

        unauthorized_subject = None

        for subject in all_course_subjects:
            subject_code = subject.code.lower().strip()
            subject_name = subject.name.lower().strip()

            code_match = subject_code in normalized_question
            name_match = subject_name in normalized_question

            if (
                (code_match or name_match)
                and subject.id not in assigned_subject_ids
            ):
                unauthorized_subject = subject
                authorization_denied = True
                break
        
        
        # Supply verified, role-scoped academic data to the AI provider.
        if (
            data.kind == "academic"
            and structured_query_context is not None
            and structured_query_context.get("data") is not None
        ):
            context += (
                "\n\nVERIFIED STRUCTURED ACADEMIC QUERY RESULT (JSON):\n"
                + json.dumps(
                    structured_query_context,
                    ensure_ascii=False,
                    default=str,
                )
            )
        
        
        
        if authorization_denied:
            academic_response = (
                f"I can't provide academic records for "
                f"**{unauthorized_subject.name} ({unauthorized_subject.code})** "
                f"because it is not assigned to your Course Admin account."
            )
        
        
        
        # ---------------------------------------------------------
        # Authorized students
        # Course Admin can see students in their assigned course.
        # ---------------------------------------------------------
        student_rows = db.execute(
            select(
                models.Student.id,
                models.Student.student_number,
                models.Student.full_name,
                models.Student.email,
                models.Student.year,
            )
            .where(models.Student.course_id == user.course_id)
            .order_by(models.Student.full_name)
        ).all()

        student_count = len(student_rows)

        context += (
            f"\n\nAUTHORIZED COURSE ADMIN CONTEXT:\n"
            f"Course: {course.name if course else 'Unknown course'} "
            f"({course.code if course else ''})\n"
            f"Enrolled students: {student_count}\n"
            f"Assigned subjects: "
            f"{', '.join(assigned_subject_names) or 'No subjects assigned'}"
        )

        # ---------------------------------------------------------
        # Student roster
        # ---------------------------------------------------------
        if student_rows:
            context += "\n\nAuthorized student roster:\n"

            context += "\n".join(
                (
                    f"- {student[2]} "
                    f"(Student No: {student[1]}, Year: {student[4]}, "
                    f"Email: {student[3]})"
                )
                for student in student_rows
            )

        # ---------------------------------------------------------
        # Attendance summary by student and assigned subject
        # ---------------------------------------------------------
        if assigned_subject_ids:
            attendance_rows = db.execute(
                select(
                    models.Student.id,
                    models.Student.full_name,
                    models.Subject.id,
                    models.Subject.name,
                    func.count(models.Attendance.id),
                    func.sum(
                        case(
                            (models.Attendance.present.is_(True), 1),
                            else_=0,
                        )
                    ),
                )
                .join(
                    models.Attendance,
                    models.Attendance.student_id == models.Student.id,
                )
                .join(
                    models.Subject,
                    models.Subject.id == models.Attendance.subject_id,
                )
                .where(
                    models.Student.course_id == user.course_id,
                    models.Subject.id.in_(assigned_subject_ids),
                )
                .group_by(
                    models.Student.id,
                    models.Student.full_name,
                    models.Subject.id,
                    models.Subject.name,
                )
                .order_by(models.Student.full_name, models.Subject.name)
            ).all()

            if attendance_rows:
                context += "\n\nAttendance by authorized subject:\n"

                attendance_context = []

                for (
                    student_id,
                    student_name,
                    subject_id,
                    subject_name,
                    total_classes,
                    present_classes,
                ) in attendance_rows:
                    total_classes = int(total_classes or 0)
                    present_classes = int(present_classes or 0)

                    percentage = round(
                        100 * present_classes / total_classes
                    ) if total_classes else 0

                    attendance_context.append(
                        f"- {student_name} | {subject_name} | "
                        f"{present_classes}/{total_classes} | "
                        f"{percentage}%"
                    )

                context += "\n".join(attendance_context)

        # ---------------------------------------------------------
        # Assignments + submission status
        # ---------------------------------------------------------
        if assigned_subject_ids:
            assignment_rows = db.execute(
                select(
                    models.Assignment.id,
                    models.Assignment.title,
                    models.Assignment.due_at,
                    models.Subject.name,
                )
                .join(
                    models.Subject,
                    models.Subject.id == models.Assignment.subject_id,
                )
                .where(
                    models.Assignment.subject_id.in_(assigned_subject_ids),
                    models.Assignment.published.is_(True),
                    models.Assignment.archived.is_(False),
                )
                .order_by(models.Assignment.due_at.desc())
            ).all()

            if assignment_rows:
                context += "\n\nAuthorized assignments and submission status:\n"

                assignment_context = []

                student_ids = [student[0] for student in student_rows]

                for assignment_id, title, due_at, subject_name in assignment_rows:
                    submitted_student_ids = set(
                        db.scalars(
                            select(models.Submission.student_id).where(
                                models.Submission.assignment_id == assignment_id,
                                models.Submission.student_id.in_(student_ids),
                            )
                        ).all()
                    )

                    submitted = len(submitted_student_ids)
                    pending = max(len(student_ids) - submitted, 0)

                    assignment_context.append(
                        f"- {title} | {subject_name} | "
                        f"Due: {due_at:%d %b %Y} | "
                        f"Submitted: {submitted} | "
                        f"Pending: {pending}"
                    )

                context += "\n".join(assignment_context)

        # ---------------------------------------------------------
        # Grade / performance data
        # ---------------------------------------------------------
        if assigned_subject_ids:
            grade_rows = db.execute(
                select(
                    models.Student.id,
                    models.Student.full_name,
                    models.Subject.name,
                    models.Grade.assessment,
                    models.Grade.score,
                    models.Grade.max_score,
                )
                .join(
                    models.Student,
                    models.Student.id == models.Grade.student_id,
                )
                .join(
                    models.Subject,
                    models.Subject.id == models.Grade.subject_id,
                )
                .where(
                    models.Student.course_id == user.course_id,
                    models.Grade.subject_id.in_(assigned_subject_ids),
                    models.Grade.published.is_(True),
                )
                .order_by(
                    models.Student.full_name,
                    models.Subject.name,
                )
            ).all()

            if grade_rows:
                context += "\n\nAuthorized published grade records:\n"

                grade_context = []

                for (
                    student_id,
                    student_name,
                    subject_name,
                    assessment,
                    score,
                    max_score,
                ) in grade_rows:
                    percentage = (
                        round(100 * score / max_score, 1)
                        if max_score
                        else 0
                    )

                    grade_context.append(
                        f"- {student_name} | {subject_name} | "
                        f"{assessment} | {score}/{max_score} | "
                        f"{percentage}%"
                    )

                context += "\n".join(grade_context)

        # ---------------------------------------------------------
        # Deterministic responses for simple factual queries
        # ---------------------------------------------------------
        
        
        
        
        
    # ---------------------------------------------------------
    # Deterministic responses for database-grounded queries
    # These work even when the external AI provider is unavailable.
    # ---------------------------------------------------------

    # Attendance below a requested threshold.
    if (
        question_terms & {"attendance", "attend"}
        and question_terms & {"below", "under", "less", "lower"}
    ):
        threshold_match = re.search(
            r"(?:below|under|less\s+than|lower\s+than)\s*(\d+(?:\.\d+)?)\s*%?",
            data.question.lower(),
        )

        threshold = (
            float(threshold_match.group(1))
            if threshold_match
            else 75.0
        )

        student_attendance = {}

        for (
            student_id,
            student_name,
            subject_id,
            subject_name,
            total_classes,
            present_classes,
        ) in attendance_rows:
            total_classes = int(total_classes or 0)
            present_classes = int(present_classes or 0)

            record = student_attendance.setdefault(
                student_id,
                {
                    "name": student_name,
                    "total": 0,
                    "present": 0,
                },
            )

            record["total"] += total_classes
            record["present"] += present_classes

        below_threshold = []

        for record in student_attendance.values():
            percentage = (
                round(100 * record["present"] / record["total"], 1)
                if record["total"]
                else 0
            )

            if percentage < threshold:
                below_threshold.append(
                    (
                        record["name"],
                        percentage,
                        record["present"],
                        record["total"],
                    )
                )

        below_threshold.sort(key=lambda row: row[1])

        if below_threshold:
            rows = [
                f"{i}. **{name}** — {percentage}% ({present}/{total})"
                for i, (name, percentage, present, total)
                in enumerate(below_threshold, start=1)
            ]

            academic_response = (
                f"### Students below {threshold:g}% attendance\n\n"
                f"Found **{len(below_threshold)}** student(s).\n\n"
                + "\n".join(rows)
            )
        else:
            academic_response = (
                f"No students with recorded attendance are below "
                f"{threshold:g}%."
            )

    # Assignment/submission query.
    elif question_terms & {
        "assignment",
        "assignments",
        "submission",
        "submissions",
    } and question_terms & {
        "missing",
        "pending",
        "submitted",
        "submit",
        "hasn't",
        "haven't",
        "not",
    }:
        if assignment_rows and student_rows:
            latest_assignment = assignment_rows[0]

            assignment_id = latest_assignment[0]
            assignment_title = latest_assignment[1]
            due_at = latest_assignment[2]
            subject_name = latest_assignment[3]

            student_ids = [student[0] for student in student_rows]

            submitted_student_ids = set(
                db.scalars(
                    select(models.Submission.student_id).where(
                        models.Submission.assignment_id == assignment_id,
                        models.Submission.student_id.in_(student_ids),
                    )
                ).all()
            )

            missing_students = [
                student
                for student in student_rows
                if student[0] not in submitted_student_ids
            ]

            if missing_students:
                missing_lines = [
                    f"{i}. **{student[2]}** — {student[1]}"
                    for i, student in enumerate(missing_students, start=1)
                ]

                academic_response = (
                    f"### Missing submissions\n\n"
                    f"Latest assignment: **{assignment_title}**\n"
                    f"Subject: **{subject_name}**\n"
                    f"Due: **{due_at:%d %b %Y}**\n\n"
                    f"Students who have not submitted: "
                    f"**{len(missing_students)}**\n\n"
                    + "\n".join(missing_lines)
                )
            else:
                academic_response = (
                    f"All {student_count} students have submitted "
                    f"**{assignment_title}**."
                )
        else:
            academic_response = (
                "There is not enough assignment or student data "
                "to determine missing submissions."
            )
    
    
    
    # Grade/performance ranking query.
    elif (
        question_terms & {
            "grade",
            "grades",
            "score",
            "scores",
            "marks",
            "performance",
            "result",
            "results",
        }
        and question_terms & {
            "top",
            "highest",
            "best",
            "ranking",
            "rank",
        }
    ):
        student_performance = {}

        for (
            student_id,
            student_name,
            subject_name,
            assessment,
            score,
            max_score,
        ) in grade_rows:
            score = float(score or 0)
            max_score = float(max_score or 0)

            if max_score <= 0:
                continue

            record = student_performance.setdefault(
                student_id,
                {
                    "name": student_name,
                    "total_score": 0.0,
                    "total_max": 0.0,
                    "assessments": 0,
                },
            )

            record["total_score"] += score
            record["total_max"] += max_score
            record["assessments"] += 1

        ranked_students = []

        for record in student_performance.values():
            if record["total_max"] <= 0:
                continue

            percentage = round(
                100 * record["total_score"] / record["total_max"],
                1,
            )

            ranked_students.append(
                (
                    record["name"],
                    percentage,
                    record["assessments"],
                )
            )

        ranked_students.sort(
            key=lambda row: row[1],
            reverse=True,
        )

        # Try to detect a requested number such as "top 10".
        top_match = re.search(
            r"\btop\s+(\d+)\b",
            data.question.lower(),
        )

        requested_count = (
            int(top_match.group(1))
            if top_match
            else 10
        )

        requested_count = max(1, min(requested_count, 50))

        top_students = ranked_students[:requested_count]

        if top_students:
            ranking_lines = [
                f"{i}. **{name}** — {percentage}% "
                f"({assessments} published grade record(s))"
                for i, (name, percentage, assessments)
                in enumerate(top_students, start=1)
            ]

            academic_response = (
                f"### Top {len(top_students)} students by published grades\n\n"
                f"Ranking is based on the combined percentage across "
                f"published grade records in your assigned subjects.\n\n"
                + "\n".join(ranking_lines)
            )
        else:
            academic_response = (
                "No published grade records are available for ranking."
            )


    # Class analysis query.
    elif (
        question_terms
        & {
            "analyze",
            "analysis",
            "overview",
            "summary",
            "performance",
        }
        and question_terms
        & {
            "class",
            "course",
            "students",
        }
    ):
        # ---------------------------------------------------------
        # Attendance analysis
        # ---------------------------------------------------------
        class_attendance = {}

        for (
            student_id,
            student_name,
            subject_id,
            subject_name,
            total_classes,
            present_classes,
        ) in attendance_rows:
            total_classes = int(total_classes or 0)
            present_classes = int(present_classes or 0)

            record = class_attendance.setdefault(
                student_id,
                {
                    "name": student_name,
                    "total": 0,
                    "present": 0,
                },
            )

            record["total"] += total_classes
            record["present"] += present_classes

        attendance_percentages = []

        for record in class_attendance.values():
            if record["total"] > 0:
                percentage = (
                    100
                    * record["present"]
                    / record["total"]
                )
                attendance_percentages.append(
                    (
                        record["name"],
                        round(percentage, 1),
                        record["present"],
                        record["total"],
                    )
                )

        average_attendance = (
            round(
                sum(row[1] for row in attendance_percentages)
                / len(attendance_percentages),
                1,
            )
            if attendance_percentages
            else 0
        )

        low_attendance = [
            row
            for row in attendance_percentages
            if row[1] < 75
        ]

        low_attendance.sort(key=lambda row: row[1])

        # ---------------------------------------------------------
        # Assignment analysis
        # ---------------------------------------------------------
        latest_assignment_title = None
        latest_assignment_subject = None
        latest_assignment_due = None
        latest_submission_rate = None

        if assignment_rows and student_rows:
            latest_assignment = assignment_rows[0]

            assignment_id = latest_assignment[0]
            latest_assignment_title = latest_assignment[1]
            latest_assignment_due = latest_assignment[2]
            latest_assignment_subject = latest_assignment[3]

            student_ids = [student[0] for student in student_rows]

            submitted_count = db.scalar(
                select(func.count(models.Submission.id)).where(
                    models.Submission.assignment_id == assignment_id,
                    models.Submission.student_id.in_(student_ids),
                )
            )

            submitted_count = int(submitted_count or 0)

            latest_submission_rate = round(
                100 * submitted_count / len(student_ids),
                1,
            )

        # ---------------------------------------------------------
        # Grade analysis
        # ---------------------------------------------------------
        student_performance = {}

        for (
            student_id,
            student_name,
            subject_name,
            assessment,
            score,
            max_score,
        ) in grade_rows:
            score = float(score or 0)
            max_score = float(max_score or 0)

            if max_score <= 0:
                continue

            record = student_performance.setdefault(
                student_id,
                {
                    "name": student_name,
                    "score": 0.0,
                    "maximum": 0.0,
                    "assessments": 0,
                },
            )

            record["score"] += score
            record["maximum"] += max_score
            record["assessments"] += 1

        performance_rows = []

        for record in student_performance.values():
            if record["maximum"] > 0:
                percentage = round(
                    100 * record["score"] / record["maximum"],
                    1,
                )

                performance_rows.append(
                    (
                        record["name"],
                        percentage,
                        record["assessments"],
                    )
                )

        performance_rows.sort(
            key=lambda row: row[1],
            reverse=True,
        )

        average_grade = (
            round(
                sum(row[1] for row in performance_rows)
                / len(performance_rows),
                1,
            )
            if performance_rows
            else 0
        )

        # ---------------------------------------------------------
        # Build class analysis response
        # ---------------------------------------------------------
        analysis_parts = [
            f"### Class Analysis — {course.name if course else 'Your Course'}",
            "",
            f"**Total enrolled students:** {student_count}",
            f"**Assigned subjects:** "
            f"{', '.join(assigned_subject_names) or 'None'}",
            "",
            "### Attendance",
            f"- Students with attendance records: **{len(attendance_percentages)}**",
            f"- Average attendance: **{average_attendance}%**",
            f"- Students below 75%: **{len(low_attendance)}**",
        ]

        if low_attendance:
            risk_preview = "\n".join(
                f"  - {name}: {percentage}%"
                for name, percentage, _, _ in low_attendance[:5]
            )

            analysis_parts.extend(
                [
                    "",
                    "**Lowest attendance:**",
                    risk_preview,
                ]
            )

        # ---------------------------------------------------------
        # Assignment section
        # ---------------------------------------------------------
        analysis_parts.extend(
            [
                "",
                "### Assignments",
            ]
        )

        if latest_assignment_title:
            analysis_parts.extend(
                [
                    f"- Latest assignment: **{latest_assignment_title}**",
                    f"- Subject: **{latest_assignment_subject}**",
                    f"- Due: **{latest_assignment_due:%d %b %Y}**",
                    f"- Submission rate: **{latest_submission_rate}%**",
                ]
            )
        else:
            analysis_parts.append(
                "- No published assignments are currently available."
            )

        # ---------------------------------------------------------
        # Grade section
        # ---------------------------------------------------------
        analysis_parts.extend(
            [
                "",
                "### Academic Performance",
                f"- Students with published grades: **{len(performance_rows)}**",
                f"- Average published grade percentage: **{average_grade}%**",
            ]
        )

        if performance_rows:
            top_preview = "\n".join(
                f"  {i}. {name} — {percentage}%"
                for i, (name, percentage, _) in enumerate(
                    performance_rows[:5],
                    start=1,
                )
            )

            analysis_parts.extend(
                [
                    "",
                    "**Top 5 by published grades:**",
                    top_preview,
                ]
            )

        # ---------------------------------------------------------
        # Final observations
        # ---------------------------------------------------------
        analysis_parts.extend(
            [
                "",
                "### Overall observations",
            ]
        )

        if low_attendance:
            analysis_parts.append(
                f"- **{len(low_attendance)}** students are below the "
                f"75% attendance threshold and may need attendance follow-up."
            )
        else:
            analysis_parts.append(
                "- No student with recorded attendance is below 75%."
            )

        if latest_submission_rate is not None:
            analysis_parts.append(
                f"- The latest assignment has a **{latest_submission_rate}%** "
                f"submission rate."
            )

        if performance_rows:
            analysis_parts.append(
                f"- Published grade records currently show an average of "
                f"**{average_grade}%**."
            )
        else:
            analysis_parts.append(
                "- No published grade records are currently available for analysis."
            )

        academic_response = "\n".join(analysis_parts)
    
    
    # Student roster query.
    elif (
        question_terms & {"student", "students", "roster"}
        and question_terms & {"list", "show", "all", "who"}
    ):
        if student_rows:
            student_lines = [
                f"{i}. {student[2]} — {student[1]} — Year {student[4]}"
                for i, student in enumerate(student_rows, start=1)
            ]

            academic_response = (
                f"### Students in {course.name if course else 'your course'}\n\n"
                f"Total students: **{student_count}**\n\n"
                + "\n".join(student_lines)
            )
        else:
            academic_response = (
                "No students are currently enrolled in your course."
            )

    # General course/student-count query.
    elif question_terms & {
        "student",
        "students",
        "enrolled",
        "enrollment",
        "course",
        "class",
        "count",
        "many",
    }:
        academic_response = (
            f"Your assigned course, "
            f"{course.name if course else 'course'}, "
            f"has **{student_count} enrolled students**. "
            f"Assigned subjects: "
            f"{', '.join(assigned_subject_names) or 'none'}."
        )
    
    
    
    
    
            
            
            
            
    if user.role == "student":
        student = db.get(models.Student, user.student_id)
        if student:
            attendance_rows = db.scalars(
                select(models.Attendance).where(models.Attendance.student_id == student.id)
            ).all()
            total = len(attendance_rows)
            present = sum(1 for x in attendance_rows if x.present)
            assignments_rows = db.scalars(
                select(models.Assignment)
                .join(models.Subject)
                .where(models.Subject.course_id == student.course_id)
            ).all()
            grades_rows = db.scalars(
                select(models.Grade).where(models.Grade.student_id == student.id)
            ).all()
            exam_rows = db.execute(
                select(models.Exam, models.Subject)
                .join(models.Subject)
                .where(
                    models.Subject.course_id == student.course_id,
                    models.Exam.starts_at >= datetime.now(),
                )
                .order_by(models.Exam.starts_at)
                .limit(8)
            ).all()
            course = db.get(models.Course, student.course_id)
            personal = f"Student's course: {course.name if course else 'unknown'}. Attendance: {present}/{total} records present ({round(100*present/total) if total else 0}%). Assignments available: {len(assignments_rows)}. Grades recorded: {len(grades_rows)}."
            context += "\n\nAuthorized personal academic context:\n" + personal
            timetable_rows = []
            if question_terms & {"attendance", "present", "absent"}:
                by_subject = db.execute(
                    select(
                        models.Subject.name,
                        func.count(models.Attendance.id),
                        func.sum(
                            case(
                                (models.Attendance.present.is_(True), 1),
                                else_=0,
                            )
                        ),
                    )
                    .join(
                        models.Attendance,
                        models.Attendance.subject_id == models.Subject.id,
                    )
                    .where(models.Attendance.student_id == student.id)
                    .group_by(models.Subject.name)
                ).all()

                attendance_data = [
                    (
                        name,
                        int(attended or 0),
                        int(count or 0),
                        round(
                            100
                            * int(attended or 0)
                            / int(count or 1)
                        ),
                    )
                    for name, count, attended in by_subject
                ]

                if attendance_data and question_terms & {
                    "lowest",
                    "least",
                    "minimum",
                }:
                    lowest_percentage = min(
                        row[3] for row in attendance_data
                    )
                    lowest_subjects = [
                        row[0]
                        for row in attendance_data
                        if row[3] == lowest_percentage
                    ]

                    if len(lowest_subjects) == 1:
                        academic_response = (
                            f"Your subject with the lowest attendance is "
                            f"{lowest_subjects[0]} at "
                            f"{lowest_percentage}%."
                        )
                    else:
                        academic_response = (
                            f"Your subjects with the lowest attendance are "
                            f"{', '.join(lowest_subjects)}, all at "
                            f"{lowest_percentage}%."
                        )

                elif attendance_data and question_terms & {
                    "highest",
                    "most",
                    "maximum",
                }:
                    highest_percentage = max(
                        row[3] for row in attendance_data
                    )
                    highest_subjects = [
                        row[0]
                        for row in attendance_data
                        if row[3] == highest_percentage
                    ]

                    if len(highest_subjects) == 1:
                        academic_response = (
                            f"Your subject with the highest attendance is "
                            f"{highest_subjects[0]} at "
                            f"{highest_percentage}%."
                        )
                    else:
                        academic_response = (
                            f"Your subjects with the highest attendance are "
                            f"{', '.join(highest_subjects)}, all at "
                            f"{highest_percentage}%."
                        )

                else:
                    details = "; ".join(
                        f"{name}: {attended}/{count} ({percentage}%)"
                        for name, attended, count, percentage in attendance_data
                    )

                    academic_response = (
                        f"Your overall attendance is "
                        f"{round(100 * present / total) if total else 0}% "
                        f"({present} of {total} recorded classes). "
                        f"By subject: "
                        f"{details or 'No attendance has been recorded yet.'}"
                    )
            elif question_terms & {"timetable", "schedule", "class", "classes"}:
                if timetable_rows:
                    weekday_names = {
                        0: "Monday",
                        1: "Tuesday",
                        2: "Wednesday",
                        3: "Thursday",
                        4: "Friday",
                        5: "Saturday",
                        6: "Sunday",
                    }

                    timetable_details = "; ".join(
                        f"{subject.name}: {weekday_names.get(entry.weekday, 'Unknown day')}, "
                        f"{entry.starts_at:%H:%M}-{entry.ends_at:%H:%M}, "
                        f"Room {entry.room}, Faculty {entry.faculty}"
                        for entry, subject in timetable_rows
                    )

                    academic_response = (
                        f"Your current timetable: {timetable_details}"
                    )
                else:
                    academic_response = (
                        "No timetable entries are currently available for your course."
                    )
            elif question_terms & {
                "assignment",
                "assignments",
                "submission",
                "submissions",
                "pending",
            }:
                items = []
                for task in assignments_rows:
                    submitted = (
                        db.scalar(
                            select(models.Submission.id).where(
                                models.Submission.assignment_id == task.id,
                                models.Submission.student_id == student.id,
                            )
                        )
                        is not None
                    )
                    subject = db.get(models.Subject, task.subject_id)
                    items.append(
                        f"{task.title} ({subject.name if subject else 'Course subject'}), due {task.due_at:%d %b %Y}, {'submitted' if submitted else 'not submitted'}"
                    )
                academic_response = "Your assignments: " + (
                    "; ".join(items[:8])
                    if items
                    else "No assignments have been posted for your course."
                )
            elif question_terms & {"grade", "grades", "score", "scores", "marks", "results"}:
                details = []
                for grade in grades_rows:
                    subject = db.get(models.Subject, grade.subject_id)
                    details.append(
                        f"{subject.name if subject else 'Subject'} — {grade.assessment}: {grade.score}/{grade.max_score}"
                    )
                academic_response = "Your recorded grades: " + (
                    "; ".join(details[:10])
                    if details
                    else "No grades have been published to your account yet."
                )
            elif question_terms & {"exam", "exams", "examination", "examinations", "test", "tests"}:
                details = [
                    f"{exam.title} ({subject.name}) — {exam.starts_at:%d %b %Y %H:%M}, {exam.room}"
                    for exam, subject in exam_rows
                ]
                academic_response = "Your upcoming exams: " + (
                    "; ".join(details) if details else "No upcoming exam schedule is available yet."
                )
            elif question_terms & {"progress", "summary", "performance", "study", "plan"}:
                academic_response = f"{personal} Upcoming exams: " + (
                    "; ".join(
                        f"{exam.title} ({subject.name}) — {exam.starts_at:%d %b %Y %H:%M}"
                        for exam, subject in exam_rows
                    )
                    if exam_rows
                    else "none are posted."
                )
    # Add current campus information within the same role scope before it reaches the model.
    announcements_query = (
        select(models.Announcement).order_by(models.Announcement.published_at.desc()).limit(5)
    )
    if user.role == "course_admin":
        announcements_query = announcements_query.where(
            (models.Announcement.course_id == user.course_id)
            | (models.Announcement.course_id.is_(None))
        )
    elif user.role == "student":
        student = db.get(models.Student, user.student_id) if user.student_id else None
        announcements_query = announcements_query.where(
            (models.Announcement.course_id == (student.course_id if student else -1))
            | (models.Announcement.course_id.is_(None))
        )
    announcement_rows = db.scalars(announcements_query).all()
    event_rows = db.scalars(
        select(models.Event)
        .where(models.Event.starts_at >= datetime.now())
        .order_by(models.Event.starts_at)
        .limit(5)
    ).all()
    if announcement_rows:
        context += "\n\nCurrent authorized announcements:\n" + "\n".join(
            f"{a.title}: {a.body[:500]}" for a in announcement_rows
        )
    if event_rows:
        context += "\n\nUpcoming campus events:\n" + "\n".join(
            f"{e.title}: {e.starts_at:%d %b %Y %H:%M}, {e.location}" for e in event_rows
        )
    scoped_course = user.course_id
    
    timetable_rows = []
    
    if user.role == "student" and user.student_id:
        student_record = db.get(models.Student, user.student_id)
        scoped_course = student_record.course_id if student_record else None
        
    
    
    if scoped_course:
        timetable_query = (
            select(models.Timetable, models.Subject)
            .join(models.Subject)
        )

        if user.role == "course_admin":
            timetable_query = (
                timetable_query
                .join(
                    models.TeacherSubject,
                    models.TeacherSubject.subject_id == models.Subject.id,
                )
                .where(
                    models.TeacherSubject.teacher_id == user.id
                )
            )
        else:
            timetable_query = timetable_query.where(
                models.Subject.course_id == scoped_course
            )

        timetable_rows = db.execute(
            timetable_query
            .order_by(models.Timetable.weekday, models.Timetable.starts_at)
            .limit(12)
        ).all()
        
    
    
        if timetable_rows:
            context += "\n\nAuthorized course timetable:\n" + "\n".join(
                f"{subject.name}: weekday {entry.weekday}, {entry.starts_at:%H:%M}-{entry.ends_at:%H:%M}, room {entry.room}, faculty {entry.faculty}"
                for entry, subject in timetable_rows
            )
        
        
        
    # this query must run for super admin too.    
    exam_query = (
        select(models.Exam, models.Subject)
        .join(models.Subject)
        .where(models.Exam.starts_at >= datetime.now())
    )

    if user.role == "course_admin":
        exam_query = (
            exam_query
            .join(
                models.TeacherSubject,
                models.TeacherSubject.subject_id == models.Subject.id,
            )
            .where(models.TeacherSubject.teacher_id == user.id)
        )

    elif user.role == "student":
        exam_query = exam_query.where(
            models.Subject.course_id == scoped_course
        )

    upcoming_rows = db.execute(
        exam_query
        .order_by(models.Exam.starts_at)
        .limit(20)
    ).all()    
        
        
        
        
    if upcoming_rows:
        context += "\n\nUpcoming course exams:\n" + "\n".join(
            f"{exam.title}: {subject.name}, {exam.starts_at:%d %b %Y %H:%M}, {exam.room}, status {exam.status}"
            for exam, subject in upcoming_rows
        )
    
    if authorization_denied:
        answer = academic_response

    elif settings.ai_api_key and settings.ai_model:
        try:
            answer = generate_campus_answer(
                data.question,
                role=str(user.role),
                campus_context={
                    "authorized_campus_context": (
                        context or "No matching authoritative campus data was found."
                    ),
                    "verified_academic_answer": formatted_academic_answer,
                },
                history=[
                    {"role": message.role, "content": message.content}
                    for message in history
                ],
            )
        except CampusAIError as exc:
            logging.warning("Campus Mind AI request failed: %s", str(exc))
            if academic_response:
                answer = academic_response
            elif formatted_academic_answer:
                answer = formatted_academic_answer
            elif relevant:
                answer = (
                    "The AI provider is temporarily unavailable.\\n\\n"
                    "Based on published campus information: "
                    + " ".join(f.answer for f in relevant)
                )
            else:
                answer = (
                    "The AI provider is temporarily unavailable, and "
                    "no deterministic answer was available for this question."
                )

    elif data.kind == "academic" and formatted_academic_answer:
        answer = formatted_academic_answer
    elif academic_response:
        answer = academic_response
    elif relevant:
        answer = (
            "Based on published campus information: "
            + " ".join(f.answer for f in relevant)
        )
    else:
        answer = (
            "I couldn't find an authoritative answer in published campus "
            "information. Please contact your course office or university "
            "administration to confirm."
        )

    conv = save_exchange(
        db=db,
        user=user,
        conversation=conv,
        kind=data.kind,
        question=data.question,
        answer=answer,
    )
        
    return {
        "conversation_id": conv.id,
        "answer": answer,
        "sources": (
            []
            if (
                data.kind == "academic"
                and formatted_academic_answer is not None
            )
            else [
                {"faq_id": f.id, "question": f.question}
                for f in relevant
            ]
        ),
    }
