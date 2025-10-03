# app/schemas/fee_schema.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

# Fee Item Schemas
class FeeItemCreate(BaseModel):
    item_name: str = Field(..., min_length=1, max_length=128)
    amount: Decimal = Field(..., ge=0, decimal_places=2)
    category: Literal["TUITION", "COCURRICULAR", "OTHER"] = "OTHER"
    billing_cycle: Literal["TERM", "ANNUAL", "ONE_OFF"] = "TERM"
    is_optional: bool = False
    class_id: Optional[UUID] = None  # Per-class override

    @field_validator('item_name')
    @classmethod
    def validate_item_name(cls, v: str) -> str:
        """Ensure item name is not just whitespace"""
        if not v.strip():
            raise ValueError('Item name cannot be empty or whitespace')
        return v.strip()

class FeeItemOut(FeeItemCreate):
    id: UUID
    fee_structure_id: UUID
    school_id: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Fee Structure Schemas
class FeeStructureCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    level: str = Field(..., max_length=32)  # 'ALL' or specific grade
    term: int = Field(..., ge=1, le=3)
    year: int = Field(..., ge=2020, le=2030)
    is_default: bool = False

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure structure name is not just whitespace"""
        if not v.strip():
            raise ValueError('Structure name cannot be empty or whitespace')
        return v.strip()

    @field_validator('level')
    @classmethod
    def validate_level(cls, v: str) -> str:
        """Normalize level value"""
        return v.strip().upper()

class FeeStructureOut(FeeStructureCreate):
    id: UUID
    school_id: UUID
    is_published: bool
    total_amount: Decimal = Decimal('0.00')  # Computed from items
    item_count: int = 0  # Number of fee items
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class FeeStructureDetail(FeeStructureOut):
    """Detailed view with all fee items included"""
    items: List[FeeItemOut] = []

class FeeStructureUpdate(BaseModel):
    """Schema for updating fee structure settings"""
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    is_default: Optional[bool] = None
    is_published: Optional[bool] = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Ensure structure name is not just whitespace if provided"""
        if v is not None and not v.strip():
            raise ValueError('Structure name cannot be empty or whitespace')
        return v.strip() if v else None

# Invoice Schemas
class InvoiceLineOut(BaseModel):
    id: UUID
    item_name: str
    amount: Decimal
    
    class Config:
        from_attributes = True

class InvoiceCreate(BaseModel):
    student_id: UUID
    term: int = Field(..., ge=1, le=3)
    year: int = Field(..., ge=2020, le=2030)
    due_date: Optional[date] = None

class InvoiceOut(BaseModel):
    id: UUID
    student_id: UUID
    term: int
    year: int
    total: Decimal
    status: Literal["DRAFT", "ISSUED", "PAID", "PARTIAL", "CANCELLED"]
    due_date: Optional[date]
    amount_paid: Decimal = Decimal('0.00')
    balance: Decimal = Decimal('0.00')
    overpayment: Decimal = Field(default=Decimal('0.00'))  # ADD THIS
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class InvoiceDetail(InvoiceOut):
    """Detailed invoice with line items and payment history"""
    lines: List[InvoiceLineOut] = []
    payments: List["PaymentOut"] = []

class GenerateInvoicesRequest(BaseModel):
    """Request to bulk generate invoices for students"""
    year: int = Field(..., ge=2020, le=2030)
    term: int = Field(..., ge=1, le=3)
    class_id: Optional[UUID] = None  # If None, generate for all classes
    level: Optional[str] = None  # If provided, filter by level
    fee_structure_id: Optional[UUID] = None  # If provided, use specific structure

class GenerateInvoicesResponse(BaseModel):
    """Response after generating invoices"""
    invoices_created: int
    total_amount: Decimal
    students_processed: int
    errors: List[str] = []

# Payment Schemas
class PaymentCreate(BaseModel):
    invoice_id: UUID
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    method: Literal["CASH", "BANK", "MPESA"]
    txn_ref: Optional[str] = Field(None, max_length=64)
    
    @field_validator('amount')
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Ensure payment amount has at most 2 decimal places"""
        if v <= 0:
            raise ValueError('Payment amount must be greater than zero')
        return v.quantize(Decimal('0.01'))

class PaymentOut(BaseModel):
    id: UUID
    invoice_id: UUID
    amount: Decimal
    method: str
    txn_ref: Optional[str]
    posted_at: datetime
    posted_by: Optional[UUID] = None  # User who recorded the payment
    
    class Config:
        from_attributes = True

# Arrears/Reports Schemas
class StudentArrears(BaseModel):
    """Individual student arrears details"""
    student_id: UUID
    student_name: str
    admission_no: str
    class_name: str
    total_invoiced: Decimal
    total_paid: Decimal
    balance: Decimal
    overpayment: Decimal = Decimal('0.00')  # ADD THIS

class ArrearsReport(BaseModel):
    """Comprehensive arrears report"""
    term: int
    year: int
    students: List[StudentArrears]
    total_outstanding: Decimal
    total_invoiced: Decimal
    total_paid: Decimal
    total_overpayment: Decimal = Decimal('0.00')  # ADD THIS
    collection_rate: float  # Percentage

class FeeStructureSummary(BaseModel):
    """Summary statistics for a fee structure"""
    structure_id: UUID
    structure_name: str
    term: int
    year: int
    level: str
    total_items: int
    total_amount: Decimal
    is_published: bool
    is_default: bool
    students_invoiced: int = 0
    total_collected: Decimal = Decimal('0.00')