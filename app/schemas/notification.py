from pydantic import BaseModel, EmailStr
from typing import Optional

class NotificationCreate(BaseModel):
    type: str  # EMAIL or IN_APP
    subject: Optional[str] = None
    body: str
    to_guardian_id: Optional[str] = None
    to_user_id: Optional[str] = None

class NotificationOut(BaseModel):
    id: str
    type: str
    subject: Optional[str]
    body: str
    to_guardian_id: Optional[str]
    to_user_id: Optional[str]
    status: str
    
    class Config:
        from_attributes = True