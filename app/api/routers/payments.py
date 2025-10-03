# app/api/routers/payments.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List
from uuid import UUID
from decimal import Decimal

from app.core.db import get_db
from app.api.deps.tenancy import require_school
from app.models.payment import Payment, Invoice
from app.schemas.fee_schema import PaymentCreate, PaymentOut

router = APIRouter()

@router.post("/", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def record_payment(
    data: PaymentCreate,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Record payment against an invoice"""
    school_id = UUID(ctx["school_id"])
    
    # Get invoice
    invoice = db.execute(
        select(Invoice).where(
            Invoice.id == data.invoice_id,
            Invoice.school_id == school_id
        )
    ).scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    # CRITICAL FIX: Allow payments against PAID invoices (for overpayments)
    if invoice.status not in ["ISSUED", "PARTIAL", "PAID"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot record payment for invoice with status {invoice.status}"
        )
    
    # Calculate current balance
    existing_payments = db.execute(
        select(Payment).where(Payment.invoice_id == invoice.id)
    ).scalars().all()
    
    total_paid = sum(p.amount for p in existing_payments)
    balance = invoice.total - total_paid
    
    # Create payment (overpayments allowed)
    payment = Payment(
        school_id=school_id,
        invoice_id=invoice.id,
        amount=data.amount,
        method=data.method,
        txn_ref=data.txn_ref
    )
    
    db.add(payment)
    
    # Update invoice status (stays PAID even with overpayment)
    new_total_paid = total_paid + data.amount
    if new_total_paid >= invoice.total:
        invoice.status = "PAID"
    else:
        invoice.status = "PARTIAL"
    
    db.commit()
    db.refresh(payment)
    
    return PaymentOut.model_validate(payment)

@router.get("/student/{student_id}", response_model=List[PaymentOut])
async def get_student_payments(
    student_id: UUID,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """List all payments for a student"""
    school_id = UUID(ctx["school_id"])
    
    payments = db.execute(
        select(Payment)
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .where(
            Invoice.school_id == school_id,
            Invoice.student_id == student_id
        )
        .order_by(Payment.posted_at.desc())
    ).scalars().all()
    
    return [PaymentOut.model_validate(p) for p in payments]