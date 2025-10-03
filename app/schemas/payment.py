from pydantic import BaseModel
from typing import Literal
from datetime import date
from uuid import UUID

class InvoiceOut(BaseModel):
    id: UUID
    school_id: UUID
    student_id: UUID
    term: int
    year: int
    total: float
    status: Literal['DRAFT', 'ISSUED', 'PAID', 'PARTIAL', 'CANCELLED']  # Added CANCELLED
    due_date: date | None
    amount_paid: float
    balance: float
    
    class Config:
        from_attributes = True


class InvoiceResponse(BaseModel):
    id: UUID
    student_id: UUID
    term: int
    year: int
    total: float
    status: Literal['DRAFT', 'ISSUED', 'PAID', 'PARTIAL', 'CANCELLED']  # Added CANCELLED
    due_date: date | None
    
    class Config:
        from_attributes = True