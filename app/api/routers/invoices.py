# app/api/routers/invoices.py
from fastapi import APIRouter, Depends, HTTPException, status, Query  # ADD Query here
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import List, Optional  # ADD Optional here
from uuid import UUID
from decimal import Decimal
from datetime import datetime, timedelta

from app.core.db import get_db
from app.api.deps.tenancy import require_school
from app.models.payment import Invoice, InvoiceLine, Payment
from app.models.student import Student
from app.models.fee import FeeStructure, FeeItem
from app.schemas.fee_schema import (
    GenerateInvoicesRequest, InvoiceOut, InvoiceDetail,
    InvoiceLineOut, PaymentOut
)

router = APIRouter()

@router.post("/generate/", response_model=List[InvoiceOut])
async def generate_invoices(
    data: GenerateInvoicesRequest,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Auto-generate invoices for students from default fee structure"""
    school_id = UUID(ctx["school_id"])
    
    # Find default fee structure for term/year
    structure = db.execute(
        select(FeeStructure).where(
            FeeStructure.school_id == school_id,
            FeeStructure.term == data.term,
            FeeStructure.year == data.year,
            FeeStructure.is_default == True,
            FeeStructure.is_published == True
        )
    ).scalar_one_or_none()
    
    if not structure:
        raise HTTPException(
            status_code=404,
            detail=f"No published default fee structure found for Term {data.term} {data.year}"
        )
    
    # Get students to invoice
    query = select(Student).where(
        Student.school_id == school_id,
        Student.status == "ACTIVE"
    )
    
    if data.class_id:
        query = query.where(Student.class_id == data.class_id)
    
    students = db.execute(query).scalars().all()
    
    if not students:
        raise HTTPException(status_code=404, detail="No students found")
    
    # Get fee items
    items = db.execute(
        select(FeeItem).where(FeeItem.fee_structure_id == structure.id)
    ).scalars().all()
    
    if not items:
        raise HTTPException(status_code=400, detail="Fee structure has no items")
    
    generated_invoices = []
    due_date = datetime.now().date() + timedelta(days=30)
    
    for student in students:
        # Check if invoice already exists
        existing = db.execute(
            select(Invoice).where(
                Invoice.school_id == school_id,
                Invoice.student_id == student.id,
                Invoice.term == data.term,
                Invoice.year == data.year
            )
        ).scalar_one_or_none()
        
        if existing:
            continue  # Skip if already invoiced
        
        # Filter items: class-specific overrides or general items
        applicable_items = [
            item for item in items
            if item.class_id is None or item.class_id == student.class_id
        ]
        
        total = sum(item.amount for item in applicable_items)
        
        # Create invoice
        invoice = Invoice(
            school_id=school_id,
            student_id=student.id,
            term=data.term,
            year=data.year,
            total=total,
            status="DRAFT",
            due_date=due_date
        )
        db.add(invoice)
        db.flush()
        
        # Create invoice lines
        for item in applicable_items:
            line = InvoiceLine(
                school_id=school_id,
                invoice_id=invoice.id,
                item_name=item.item_name,
                amount=item.amount
            )
            db.add(line)
        
        generated_invoices.append(invoice)
    
    db.commit()
    
    # FIX: Refresh all invoices to get updated timestamps
    for inv in generated_invoices:
        db.refresh(inv)
    
    # FIX: Properly serialize the response
    return [
        InvoiceOut(
            id=inv.id,
            student_id=inv.student_id,
            term=inv.term,
            year=inv.year,
            total=inv.total,
            status=inv.status,
            due_date=inv.due_date,
            created_at=inv.created_at,
            updated_at=inv.updated_at,
            amount_paid=Decimal('0.00'),
            balance=inv.total
        )
        for inv in generated_invoices
    ]

@router.get("/{invoice_id}", response_model=InvoiceDetail)
async def get_invoice(
    invoice_id: UUID,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Get detailed invoice with lines and payments"""
    school_id = UUID(ctx["school_id"])
    
    invoice = db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.school_id == school_id
        )
    ).scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    lines = db.execute(
        select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id)
    ).scalars().all()
    
    payments = db.execute(
        select(Payment).where(Payment.invoice_id == invoice_id).order_by(Payment.posted_at)
    ).scalars().all()
    
    # CANCELLED invoices have zero balance
    if invoice.status == "CANCELLED":
        amount_paid = Decimal('0.00')
        balance = Decimal('0.00')
        overpayment = Decimal('0.00')
    else:
        amount_paid = sum(p.amount for p in payments)
        balance = max(Decimal('0.00'), invoice.total - amount_paid)  # Don't show negative balance
        overpayment = max(Decimal('0.00'), amount_paid - invoice.total)  # Calculate overpayment
    
    return InvoiceDetail(
        **invoice.__dict__,
        amount_paid=amount_paid,
        balance=balance,
        overpayment=overpayment,
        lines=[InvoiceLineOut.model_validate(l) for l in lines],
        payments=[PaymentOut.model_validate(p) for p in payments]
    )

@router.get("/student/{student_id}", response_model=List[InvoiceOut])
async def get_student_invoices(
    student_id: UUID,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Get all invoices for a student"""
    school_id = UUID(ctx["school_id"])
    
    invoices = db.execute(
        select(Invoice).where(
            Invoice.school_id == school_id,
            Invoice.student_id == student_id
        ).order_by(Invoice.year.desc(), Invoice.term.desc())
    ).scalars().all()
    
    result = []
    for inv in invoices:
        # CANCELLED invoices have zero balance
        if inv.status == "CANCELLED":
            amount_paid = Decimal('0.00')
            balance = Decimal('0.00')
            overpayment = Decimal('0.00')
        else:
            payments = db.execute(
                select(Payment).where(Payment.invoice_id == inv.id)
            ).scalars().all()
            
            amount_paid = sum(p.amount for p in payments)
            balance = max(Decimal('0.00'), inv.total - amount_paid)
            overpayment = max(Decimal('0.00'), amount_paid - inv.total)
        
        result.append(InvoiceOut(
            **inv.__dict__,
            amount_paid=amount_paid,
            balance=balance,
            overpayment=overpayment
        ))
    
    return result

@router.put("/{invoice_id}/issue", response_model=InvoiceOut)
async def issue_invoice(
    invoice_id: UUID,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Issue invoice (DRAFT → ISSUED)"""
    school_id = UUID(ctx["school_id"])
    
    invoice = db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.school_id == school_id
        )
    ).scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if invoice.status != "DRAFT":
        raise HTTPException(status_code=400, detail=f"Cannot issue invoice with status {invoice.status}")
    
    invoice.status = "ISSUED"
    db.commit()
    db.refresh(invoice)
    
    # TODO: Queue notification to guardians
    
    return InvoiceOut(
        **invoice.__dict__,
        amount_paid=Decimal('0.00'),
        balance=invoice.total
    )


@router.put("/bulk-issue/", response_model=dict)
async def bulk_issue_invoices(
    year: int = Query(...),
    term: int = Query(...),
    class_id: Optional[UUID] = None,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Issue all DRAFT invoices for a term (DRAFT → ISSUED)"""
    school_id = UUID(ctx["school_id"])
    
    query = select(Invoice).where(
        Invoice.school_id == school_id,
        Invoice.year == year,
        Invoice.term == term,
        Invoice.status == "DRAFT"
    )
    
    if class_id:
        query = query.join(Student).where(Student.class_id == class_id)
    
    invoices = db.execute(query).scalars().all()
    
    if not invoices:
        raise HTTPException(
            status_code=404,
            detail=f"No DRAFT invoices found for Term {term} {year}"
        )
    
    issued_count = 0
    for invoice in invoices:
        invoice.status = "ISSUED"
        issued_count += 1
    
    db.commit()
    
    return {
        "issued_count": issued_count,
        "term": term,
        "year": year,
        "message": f"Issued {issued_count} invoices. Parents will be notified."
    }

@router.get("/", response_model=List[InvoiceOut])
async def list_all_invoices(
    year: Optional[int] = None,
    term: Optional[int] = None,
    class_id: Optional[UUID] = None,
    status: Optional[str] = None,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """List all invoices with optional filters"""
    school_id = UUID(ctx["school_id"])
    
    query = select(Invoice).where(Invoice.school_id == school_id)
    
    if year:
        query = query.where(Invoice.year == year)
    if term:
        query = query.where(Invoice.term == term)
    if status:
        query = query.where(Invoice.status == status)
    if class_id:
        query = query.join(Student).where(Student.class_id == class_id)
    
    invoices = db.execute(
        query.order_by(Invoice.year.desc(), Invoice.term.desc())
    ).scalars().all()
    
    result = []
    for inv in invoices:
        payments = db.execute(
            select(Payment).where(Payment.invoice_id == inv.id)
        ).scalars().all()
        
        amount_paid = sum(p.amount for p in payments)
        balance = inv.total - amount_paid
        
        result.append(InvoiceOut(
            id=inv.id,
            student_id=inv.student_id,
            term=inv.term,
            year=inv.year,
            total=inv.total,
            status=inv.status,
            due_date=inv.due_date,
            created_at=inv.created_at,
            updated_at=inv.updated_at,
            amount_paid=amount_paid,
            balance=balance
        ))
    
    return result

@router.put("/{invoice_id}/cancel", response_model=InvoiceOut)
async def cancel_invoice(
    invoice_id: UUID,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Cancel an invoice (any status → CANCELLED)"""
    school_id = UUID(ctx["school_id"])
    
    invoice = db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.school_id == school_id
        )
    ).scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if invoice.status == "PAID":
        raise HTTPException(
            status_code=400, 
            detail="Cannot cancel a paid invoice. Issue a refund instead."
        )
    
    invoice.status = "CANCELLED"
    db.commit()
    db.refresh(invoice)
    
    # CANCELLED invoices have zero balance (they're voided)
    return InvoiceOut(
        id=invoice.id,
        student_id=invoice.student_id,
        term=invoice.term,
        year=invoice.year,
        total=invoice.total,
        status=invoice.status,
        due_date=invoice.due_date,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
        amount_paid=Decimal('0.00'),
        balance=Decimal('0.00')  # CANCELLED = no balance
    )