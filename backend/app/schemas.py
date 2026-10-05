from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    login: str
    email: str
    full_name: str
    role: str
    active: bool
    course_id: int | None
    student_id: int | None


class StudentCreate(BaseModel):
    student_number: str = Field(min_length=5, max_length=20)
    full_name: str
    email: str
    course_id: int
    year: int = Field(ge=1, le=6)
    password: str = Field(min_length=10)


class AttendanceMark(BaseModel):
    subject_id: int
    held_on: date
    student_id: int
    present: bool


class AssignmentCreate(BaseModel):
    subject_id: int
    title: str
    description: str = ""
    due_at: datetime
    max_score: int = Field(default=100, gt=0)
    published: bool = True


class SubmissionCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class GradeCreate(BaseModel):
    student_id: int
    subject_id: int
    assessment: str
    score: int = Field(ge=0)
    max_score: int = Field(gt=0)
    published: bool = True


class Ask(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    kind: Literal["campus", "academic"] = "campus"
    conversation_id: int | None = None


class StudentUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: str
    year: int = Field(ge=1, le=6)
    course_id: int


class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: str


class CourseCreate(BaseModel):
    code: str = Field(min_length=2, max_length=12)
    name: str = Field(min_length=2, max_length=160)


class SubjectCreate(BaseModel):
    code: str = Field(min_length=2, max_length=24)
    name: str = Field(min_length=2, max_length=160)
    course_id: int


class CourseAdminCreate(BaseModel):
    login: str = Field(min_length=3, max_length=80)
    email: str
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=10)
    course_id: int
    subject_ids: list[int] = Field(min_length=2, max_length=2)

class FAQCreate(BaseModel):
    category_id: int
    question: str = Field(min_length=5, max_length=400)
    answer: str = Field(min_length=2, max_length=10000)
    published: bool = True
    featured: bool = False


class FAQCategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    body: str = Field(min_length=2, max_length=10000)
    course_id: int | None = None
    published: bool = True


class EventCreate(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = ""
    starts_at: datetime
    location: str = Field(min_length=2, max_length=160)


class ExamCreate(BaseModel):
    subject_id: int
    title: str = Field(min_length=3, max_length=160)
    starts_at: datetime
    room: str = Field(min_length=2, max_length=40)
    status: Literal["scheduled", "postponed", "cancelled", "completed"] = "scheduled"


class TimetableCreate(BaseModel):
    subject_id: int
    weekday: int = Field(ge=0, le=6)
    starts_at: str
    ends_at: str
    room: str = Field(min_length=1, max_length=40)
    faculty: str = Field(min_length=2, max_length=160)


class NotificationRead(BaseModel):
    read: bool


class FeedbackCreate(BaseModel):
    helpful: bool


class AdministratorUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: str
    course_id: int
    subject_ids: list[int] = Field(min_length=2, max_length=2)
    
class PasswordReset(BaseModel):
    password: str = Field(min_length=10, max_length=1024)


class SubjectUpdate(BaseModel):
    code: str = Field(min_length=2, max_length=24)
    name: str = Field(min_length=2, max_length=160)


class GradeUpdate(BaseModel):
    score: int = Field(ge=0)
    max_score: int = Field(gt=0)
    published: bool = True


class AssignmentUpdate(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = ""
    due_at: datetime
    max_score: int = Field(default=100, gt=0)
    published: bool = True


class EventUpdate(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = ""
    starts_at: datetime
    location: str = Field(min_length=2, max_length=160)
