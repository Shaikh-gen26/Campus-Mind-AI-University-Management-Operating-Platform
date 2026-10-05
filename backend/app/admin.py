from datetime import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import insert, literal, select
from sqlalchemy.orm import Session
from . import models, schemas
from .database import get_db
from .security import hash_password, require_roles

router = APIRouter(prefix="/api", tags=["Administration"])
admin = require_roles("super_admin")
staff = require_roles("super_admin", "course_admin")


def _course_access(user, course_id):
    if user.role == "course_admin" and user.course_id != course_id:
        raise HTTPException(403, "Outside assigned course")


def _notify_students(db, title, body, notification_type, course_id=None):
    query = (
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
        .where(models.User.active.is_(True))
    )
    if course_id is not None:
        query = query.where(models.Student.course_id == course_id)
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
            query,
        )
    )


@router.post("/courses", status_code=201)
def add_course(
    data: schemas.CourseCreate, db: Session = Depends(get_db), _: models.User = Depends(admin)
):
    if db.scalar(select(models.Course).where(models.Course.code == data.code.upper())):
        raise HTTPException(409, "Course code already exists")
    row = models.Course(code=data.code.upper(), name=data.name)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "code": row.code, "name": row.name}


@router.patch("/courses/{course_id}")
def edit_course(
    course_id: int,
    data: schemas.CourseCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(admin),
):
    row = db.get(models.Course, course_id)
    if not row:
        raise HTTPException(404, "Course not found")
    if db.scalar(
        select(models.Course).where(
            models.Course.code == data.code.upper(), models.Course.id != course_id
        )
    ):
        raise HTTPException(409, "Course code already exists")
    row.code, row.name = data.code.upper(), data.name
    db.commit()
    return {"id": row.id, "code": row.code, "name": row.name}


@router.post("/subjects", status_code=201)
def add_subject(
    data: schemas.SubjectCreate, db: Session = Depends(get_db), _: models.User = Depends(admin)
):
    if not db.get(models.Course, data.course_id):
        raise HTTPException(404, "Course not found")
    if db.scalar(select(models.Subject).where(models.Subject.code == data.code.upper())):
        raise HTTPException(409, "Subject code already exists")
    row = models.Subject(code=data.code.upper(), name=data.name, course_id=data.course_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "code": row.code, "name": row.name, "course_id": row.course_id}


@router.patch("/subjects/{subject_id}")
def edit_subject(
    subject_id: int,
    data: schemas.SubjectUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(admin),
):
    row = db.get(models.Subject, subject_id)
    if not row:
        raise HTTPException(404, "Subject not found")
    if db.scalar(
        select(models.Subject).where(
            models.Subject.code == data.code.upper(), models.Subject.id != subject_id
        )
    ):
        raise HTTPException(409, "Subject code already exists")
    row.code, row.name = data.code.upper(), data.name
    db.commit()
    return {"id": row.id, "updated": True}


@router.patch("/students/{student_id}")
def edit_student(
    student_id: int,
    data: schemas.StudentUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(admin),
):
    student = db.get(models.Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    if not db.get(models.Course, data.course_id):
        raise HTTPException(404, "Course not found")
    if db.scalar(
        select(models.Student).where(
            models.Student.email == data.email, models.Student.id != student_id
        )
    ):
        raise HTTPException(409, "Email already in use")
    student.full_name, student.email, student.year, student.course_id = (
        data.full_name,
        data.email,
        data.year,
        data.course_id,
    )
    account = db.scalar(select(models.User).where(models.User.student_id == student.id))
    if account:
        account.full_name, account.email = data.full_name, data.email
    db.commit()
    return {"id": student.id, "updated": True}


@router.patch("/students/{student_id}/status")
def student_status(
    student_id: int, active: bool, db: Session = Depends(get_db), _: models.User = Depends(admin)
):
    student = db.get(models.Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    account = db.scalar(select(models.User).where(models.User.student_id == student.id))
    if account:
        account.active = active
    db.commit()
    return {"id": student.id, "active": active}


@router.patch("/students/{student_id}/password")
def reset_student_password(
    student_id: int,
    data: schemas.PasswordReset,
    db: Session = Depends(get_db),
    _: models.User = Depends(admin),
):
    student = db.get(models.Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")

    account = db.scalar(
        select(models.User).where(models.User.student_id == student.id)
    )
    if not account:
        raise HTTPException(404, "Student account not found")

    account.password_hash = hash_password(data.password)
    account.token_version += 1

    db.commit()

    return {
        "id": student.id,
        "login": account.login,
        "password_updated": True,
    }



@router.get("/administrators")
def administrators(
    db: Session = Depends(get_db),
    _: models.User = Depends(admin),
):
    rows = db.scalars(
        select(models.User)
        .where(models.User.role.in_(["super_admin", "course_admin"]))
        .order_by(models.User.role, models.User.login)
    ).all()

    result = []

    for u in rows:
        subject_rows = db.scalars(
            select(models.Subject)
            .join(
                models.TeacherSubject,
                models.TeacherSubject.subject_id == models.Subject.id,
            )
            .where(models.TeacherSubject.teacher_id == u.id)
            .order_by(models.Subject.code)
        ).all()

        result.append(
            {
                "id": u.id,
                "login": u.login,
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "course_id": u.course_id,
                "active": u.active,
                "subject_ids": [subject.id for subject in subject_rows],
                "subject_codes": [subject.code for subject in subject_rows],
                "subjects": [
                    {
                        "id": subject.id,
                        "code": subject.code,
                        "name": subject.name,
                    }
                    for subject in subject_rows
                ],
            }
        )

    return result



@router.patch("/administrators/{user_id}")
def edit_administrator(
    user_id: int,
    data: schemas.AdministratorUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(admin),
):
    user = db.get(models.User, user_id)

    if not user or user.role != "course_admin":
        raise HTTPException(404, "Course administrator not found")

    if db.scalar(
        select(models.User.id).where(
            models.User.email == data.email,
            models.User.id != user_id,
        )
    ):
        raise HTTPException(409, "Email already in use")

    course = db.get(models.Course, data.course_id)
    if not course:
        raise HTTPException(404, "Course not found")

    if len(data.subject_ids) != 2:
        raise HTTPException(400, "Exactly 2 subjects are required")

    if len(set(data.subject_ids)) != 2:
        raise HTTPException(400, "Exactly 2 different subjects are required")

    subjects = db.scalars(
        select(models.Subject).where(
            models.Subject.id.in_(data.subject_ids)
        )
    ).all()

    if len(subjects) != 2:
        raise HTTPException(400, "Exactly 2 valid subjects are required")

    if any(subject.course_id != data.course_id for subject in subjects):
        raise HTTPException(
            400,
            "Both subjects must belong to the selected course",
        )

    user.full_name = data.full_name
    user.email = data.email
    user.course_id = data.course_id

    existing_assignments = db.scalars(
        select(models.TeacherSubject).where(
            models.TeacherSubject.teacher_id == user.id
        )
    ).all()

    for assignment in existing_assignments:
        db.delete(assignment)

    db.flush()

    for subject in subjects:
        db.add(
            models.TeacherSubject(
                teacher_id=user.id,
                subject_id=subject.id,
            )
        )

    db.commit()

    return {
        "id": user.id,
        "updated": True,
        "course_id": user.course_id,
        "subject_ids": [subject.id for subject in subjects],
    }



@router.post("/administrators", status_code=201)
def add_course_admin(
    data: schemas.CourseAdminCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(admin),
):
    course = db.get(models.Course, data.course_id)
    if not course:
        raise HTTPException(404, "Course not found")

    if db.scalar(
        select(models.User).where(
            (models.User.login == data.login) | (models.User.email == data.email)
        )
    ):
        raise HTTPException(409, "Login or email already exists")

    subjects = db.scalars(
        select(models.Subject).where(
            models.Subject.id.in_(data.subject_ids)
        )
    ).all()

    if len(subjects) != 2:
        raise HTTPException(400, "Exactly 2 valid subjects are required")

    if len({subject.id for subject in subjects}) != 2:
        raise HTTPException(400, "Exactly 2 different subjects are required")

    if any(subject.course_id != data.course_id for subject in subjects):
        raise HTTPException(
            400,
            "Both subjects must belong to the selected course",
        )

    user = models.User(
        login=data.login,
        email=data.email,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        role="course_admin",
        course_id=data.course_id,
    )

    db.add(user)
    db.flush()

    for subject in subjects:
        db.add(
            models.TeacherSubject(
                teacher_id=user.id,
                subject_id=subject.id,
            )
        )

    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "login": user.login,
        "course_id": user.course_id,
        "subject_ids": [subject.id for subject in subjects],
    }


@router.patch("/administrators/{user_id}/status")
def administrator_status(
    user_id: int, active: bool, db: Session = Depends(get_db), _: models.User = Depends(admin)
):
    user = db.get(models.User, user_id)
    if not user or user.role != "course_admin":
        raise HTTPException(404, "Course administrator not found")
    user.active = active
    db.commit()
    return {"id": user.id, "active": user.active}


@router.patch("/administrators/{user_id}/password")
def reset_administrator_password(
    user_id: int,
    data: schemas.PasswordReset,
    db: Session = Depends(get_db),
    _: models.User = Depends(admin),
):
    user = db.get(models.User, user_id)

    if not user or user.role != "course_admin":
        raise HTTPException(404, "Course administrator not found")

    user.password_hash = hash_password(data.password)
    user.token_version += 1

    db.commit()

    return {
        "id": user.id,
        "login": user.login,
        "password_updated": True,
    }


@router.get("/faq-categories")
def faq_categories(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("super_admin", "course_admin", "student")),
):
    return [
        {"id": x.id, "name": x.name}
        for x in db.scalars(select(models.FAQCategory).order_by(models.FAQCategory.name)).all()
    ]


@router.post("/faq-categories", status_code=201)
def add_faq_category(
    data: schemas.FAQCategoryCreate, db: Session = Depends(get_db), _: models.User = Depends(admin)
):
    if db.scalar(select(models.FAQCategory).where(models.FAQCategory.name == data.name)):
        raise HTTPException(409, "Category already exists")
    row = models.FAQCategory(name=data.name)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name}


@router.post("/faqs", status_code=201)
def add_faq(
    data: schemas.FAQCreate, db: Session = Depends(get_db), _: models.User = Depends(admin)
):
    if not db.get(models.FAQCategory, data.category_id):
        raise HTTPException(404, "FAQ category not found")
    row = models.FAQ(**data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.patch("/faqs/{faq_id}")
def edit_faq(
    faq_id: int,
    data: schemas.FAQCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(admin),
):
    row = db.get(models.FAQ, faq_id)
    if not row:
        raise HTTPException(404, "FAQ not found")
    if not db.get(models.FAQCategory, data.category_id):
        raise HTTPException(404, "FAQ category not found")
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.commit()
    return {"id": row.id, "updated": True}


@router.delete("/faqs/{faq_id}", status_code=204)
def archive_faq(faq_id: int, db: Session = Depends(get_db), _: models.User = Depends(admin)):
    row = db.get(models.FAQ, faq_id)
    if not row:
        raise HTTPException(404, "FAQ not found")
    row.published = False
    db.commit()


@router.post("/faq-feedback/{faq_id}", status_code=201)
def faq_feedback(
    faq_id: int,
    data: schemas.FeedbackCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "course_admin", "student")),
):
    if not db.get(models.FAQ, faq_id):
        raise HTTPException(404, "FAQ not found")
    previous = db.scalar(
        select(models.FAQFeedback).where(
            models.FAQFeedback.faq_id == faq_id, models.FAQFeedback.user_id == user.id
        )
    )
    if previous:
        previous.helpful = data.helpful
    else:
        db.add(models.FAQFeedback(faq_id=faq_id, user_id=user.id, helpful=data.helpful))
    db.commit()
    return {"saved": True}


@router.post("/announcements", status_code=201)
def add_announcement(
    data: schemas.AnnouncementCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(staff),
):
    course_id = data.course_id if user.role == "super_admin" else user.course_id
    if user.role == "course_admin" and data.course_id not in (None, user.course_id):
        raise HTTPException(403, "Outside assigned course")
    if course_id and not db.get(models.Course, course_id):
        raise HTTPException(404, "Course not found")
    row = models.Announcement(
        title=data.title,
        body=data.body,
        course_id=course_id,
        author_id=user.id,
        published=data.published,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    if row.published:
        _notify_students(db, f"Announcement: {row.title}", row.body, "announcement", course_id)
        db.commit()
    return {"id": row.id}


@router.patch("/announcements/{announcement_id}")
def edit_announcement(
    announcement_id: int,
    data: schemas.AnnouncementCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(staff),
):
    row = db.get(models.Announcement, announcement_id)
    if not row:
        raise HTTPException(404, "Announcement not found")
    if user.role == "course_admin" and row.course_id != user.course_id:
        raise HTTPException(403, "Outside assigned course")
    if user.role == "course_admin" and data.course_id not in (None, user.course_id):
        raise HTTPException(403, "Outside assigned course")
    was_published = row.published
    row.title, row.body, row.published = data.title, data.body, data.published
    if user.role == "super_admin":
        row.course_id = data.course_id
    if row.published and not was_published:
        _notify_students(db, f"Announcement: {row.title}", row.body, "announcement", row.course_id)
    db.commit()
    return {"id": row.id, "updated": True}


@router.post("/events", status_code=201)
def add_event(
    data: schemas.EventCreate, db: Session = Depends(get_db), _: models.User = Depends(admin)
):
    row = models.Event(**data.model_dump())
    db.add(row)
    db.flush()
    _notify_students(
        db,
        f"Campus event: {row.title}",
        f"{row.starts_at:%d %b %Y %H:%M} at {row.location}.",
        "event",
    )
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.patch("/events/{event_id}")
def edit_event(
    event_id: int,
    data: schemas.EventUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(admin),
):
    row = db.get(models.Event, event_id)
    if not row:
        raise HTTPException(404, "Event not found")
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.commit()
    return {"id": row.id, "updated": True}


@router.patch("/notifications/{notification_id}")
def mark_notification(
    notification_id: int,
    data: schemas.NotificationRead,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "course_admin", "student")),
):
    row = db.get(models.Notification, notification_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Notification not found")
    row.read = data.read
    db.commit()
    return {"id": row.id, "read": row.read}


@router.post("/exams", status_code=201)
def add_exam(
    data: schemas.ExamCreate, db: Session = Depends(get_db), user: models.User = Depends(staff)
):
    subject = db.get(models.Subject, data.subject_id)
    if not subject:
        raise HTTPException(404, "Subject not found")
    
    if user.role == "course_admin":
        assigned = db.scalar(
        select(models.TeacherSubject.id).where(
            models.TeacherSubject.teacher_id == user.id,
            models.TeacherSubject.subject_id == subject.id,
        )
    )
    if not assigned:
        raise HTTPException(403, "Outside assigned subjects")
    
    row = models.Exam(**data.model_dump())
    db.add(row)
    db.flush()
    _notify_students(
        db,
        f"Exam scheduled: {row.title}",
        f"{row.starts_at:%d %b %Y %H:%M} in {row.room}.",
        "exam",
        subject.course_id,
    )
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.patch("/exams/{exam_id}")
def edit_exam(
    exam_id: int,
    data: schemas.ExamCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(staff),
):
    row = db.get(models.Exam, exam_id)
    subject = db.get(models.Subject, data.subject_id)
    if not row or not subject:
        raise HTTPException(404, "Exam or subject not found")
    
    
    if user.role == "course_admin":
        existing_assignment = db.scalar(
        select(models.TeacherSubject.id).where(
            models.TeacherSubject.teacher_id == user.id,
            models.TeacherSubject.subject_id == row.subject_id,
        )
    )
    new_assignment = db.scalar(
        select(models.TeacherSubject.id).where(
            models.TeacherSubject.teacher_id == user.id,
            models.TeacherSubject.subject_id == subject.id,
        )
    )

    if not existing_assignment or not new_assignment:
        raise HTTPException(403, "Outside assigned subjects")
    
    
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.commit()
    return {"id": row.id, "updated": True}


@router.post("/timetable", status_code=201)
def add_timetable_entry(
    data: schemas.TimetableCreate, db: Session = Depends(get_db), user: models.User = Depends(staff)
):
    subject = db.get(models.Subject, data.subject_id)
    if not subject:
        raise HTTPException(404, "Subject not found")
    
    
    if user.role == "course_admin":
        assigned = db.scalar(
        select(models.TeacherSubject.id).where(
            models.TeacherSubject.teacher_id == user.id,
            models.TeacherSubject.subject_id == subject.id,
        )
    )
    if not assigned:
        raise HTTPException(403, "Outside assigned subjects")
    
    
    try:
        start, end = time.fromisoformat(data.starts_at), time.fromisoformat(data.ends_at)
    except ValueError:
        raise HTTPException(422, "Times must use HH:MM format")
    if start >= end:
        raise HTTPException(422, "Class end time must follow start time")
    row = models.Timetable(
        subject_id=data.subject_id,
        weekday=data.weekday,
        starts_at=start,
        ends_at=end,
        room=data.room,
        faculty=data.faculty,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.patch("/timetable/{entry_id}")
def edit_timetable_entry(
    entry_id: int,
    data: schemas.TimetableCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(staff),
):
    row = db.get(models.Timetable, entry_id)
    subject = db.get(models.Subject, data.subject_id)
    if not row or not subject:
        raise HTTPException(404, "Timetable entry or subject not found")
    
    
    if user.role == "course_admin":
        existing_assignment = db.scalar(
        select(models.TeacherSubject.id).where(
            models.TeacherSubject.teacher_id == user.id,
            models.TeacherSubject.subject_id == row.subject_id,
        )
    )
    new_assignment = db.scalar(
        select(models.TeacherSubject.id).where(
            models.TeacherSubject.teacher_id == user.id,
            models.TeacherSubject.subject_id == subject.id,
        )
    )

    if not existing_assignment or not new_assignment:
        raise HTTPException(403, "Outside assigned subjects")
    
    
    try:
        start, end = time.fromisoformat(data.starts_at), time.fromisoformat(data.ends_at)
    except ValueError:
        raise HTTPException(422, "Times must use HH:MM format")
    if start >= end:
        raise HTTPException(422, "Class end time must follow start time")
    row.subject_id, row.weekday, row.starts_at, row.ends_at, row.room, row.faculty = (
        data.subject_id,
        data.weekday,
        start,
        end,
        data.room,
        data.faculty,
    )
    db.commit()
    return {"id": row.id, "updated": True}


@router.get("/conversations")
def conversations(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "course_admin", "student")),
):
    rows = db.scalars(
        select(models.AIConversation)
        .where(models.AIConversation.user_id == user.id)
        .order_by(models.AIConversation.created_at.desc())
    ).all()
    return [{"id": c.id, "kind": c.kind, "created_at": c.created_at} for c in rows]


@router.get("/conversations/{conversation_id}")
def conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "course_admin", "student")),
):
    row = db.get(models.AIConversation, conversation_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    messages = db.scalars(
        select(models.AIMessage)
        .where(models.AIMessage.conversation_id == row.id)
        .order_by(models.AIMessage.id)
    ).all()
    return {
        "id": row.id,
        "kind": row.kind,
        "messages": [
            {"role": x.role, "content": x.content, "created_at": x.created_at} for x in messages
        ],
    }


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "course_admin", "student")),
):
    row = db.get(models.AIConversation, conversation_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    db.execute(delete(models.AIMessage).where(models.AIMessage.conversation_id == row.id))
    db.delete(row)
    db.commit()
