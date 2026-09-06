"""Request and response models for the REST API."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StudentBase(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(min_length=5, max_length=30)
    department: str = Field(min_length=2, max_length=100)
    year: int = Field(ge=1, le=10)


class StudentCreate(StudentBase):
    pass


class StudentUpdate(StudentBase):
    pass


class Student(StudentBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class OtpRequest(BaseModel):
    email: EmailStr
    role: str = Field(pattern="^(admin|user)$")


class OtpVerify(OtpRequest):
    code: str = Field(pattern=r"^\d{6}$")


class ManagedUserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr


class ManagedUserUpdate(BaseModel):
    is_active: bool
