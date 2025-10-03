# app/schemas/student.py
from pydantic import BaseModel, validator
from typing import Optional, List
from datetime import date, datetime
from uuid import UUID

class StudentCreate(BaseModel):
    admission_no: str
    first_name: str
    last_name: str
    gender: Optional[str] = None
    dob: Optional[date] = None
    class_id: Optional[UUID] = None
    
    @validator('admission_no')
    def validate_admission_no(cls, v):
        if not v or not v.strip():
            raise ValueError('Admission number cannot be empty')
        return v.strip()
    
    @validator('first_name', 'last_name')
    def validate_names(cls, v):
        if not v or not v.strip():
            raise ValueError('Name cannot be empty')
        return v.strip()

class StudentUpdate(BaseModel):
    admission_no: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[date] = None
    class_id: Optional[UUID] = None
    primary_guardian_id: Optional[UUID] = None
    status: Optional[str] = None

class StudentOut(BaseModel):
    id: UUID
    admission_no: str
    first_name: str
    last_name: str
    full_name: str
    gender: Optional[str]
    dob: Optional[date]
    class_id: Optional[UUID]
    class_name: Optional[str]
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class StudentDetail(StudentOut):
    updated_at: datetime

class StudentList(BaseModel):
    students: List[StudentOut]
    total: int
    page: int
    limit: int
    has_next: bool

class StudentSearch(BaseModel):
    admission_no: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    class_id: Optional[UUID] = None
    status: Optional[str] = None
