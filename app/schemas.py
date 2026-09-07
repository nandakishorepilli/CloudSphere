from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class StudentBase(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(min_length=5, max_length=30)
    department: str = Field(min_length=2, max_length=100)
    year: int = Field(ge=1, le=10)
    roll_number: str = Field(min_length=2, max_length=50)
    course_id: int = Field(gt=0)

class StudentCreate(StudentBase): pass
class StudentUpdate(StudentBase): pass
class Student(StudentBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime

class StudentListItem(BaseModel):
    """List representation that keeps pre-migration student records readable."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    email: EmailStr
    phone: str
    department: str
    year: int
    roll_number: str | None = None
    course_id: int | None = None
    course_name: str | None = None
    account_status: str
    created_at: datetime

class OtpRequest(BaseModel):
    email: EmailStr
    role: str = Field(pattern="^(admin|user)$")
class OtpVerify(OtpRequest): code: str = Field(pattern=r"^\d{6}$")
class ManagedUserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
class ManagedUserUpdate(BaseModel): is_active: bool

class AttendanceMark(BaseModel):
    student_id: int = Field(gt=0)
    status: str = Field(pattern="^(present|absent)$")
class AttendanceSave(BaseModel):
    course_id: int = Field(gt=0)
    attendance_date: date
    marks: list[AttendanceMark] = Field(min_length=1)
