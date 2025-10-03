from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List
from uuid import UUID
import logging
from datetime import datetime

from app.core.db import get_db
from app.api.deps.tenancy import require_school
from app.models.notification import Notification
from app.models.guardian import Guardian, StudentGuardian
from app.models.student import Student
from app.models.payment import Invoice
from app.services.email_service import email_service, EmailTemplates
from app.schemas.notification import NotificationCreate, NotificationOut

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/notify-pending-invoices", status_code=status.HTTP_200_OK)
async def notify_pending_invoices(
    term: int,
    year: int,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """
    Notify all guardians about pending invoice payments for a specific term
    """
    school_id = UUID(ctx["school_id"])
    user = ctx["user"]
    
    try:
        # Get all unpaid/partial invoices for the term
        invoices = db.execute(
            select(Invoice).where(
                Invoice.school_id == school_id,
                Invoice.year == year,
                Invoice.term == term,
                Invoice.status.in_(["ISSUED", "PARTIAL"])
            )
        ).scalars().all()
        
        if not invoices:
            return {
                "message": f"No pending invoices found for Term {term} {year}",
                "sent": 0,
                "failed": 0
            }
        
        notifications_sent = 0
        notifications_failed = 0
        errors = []
        
        for invoice in invoices:
            # Get student
            student = db.get(Student, invoice.student_id)
            if not student:
                continue
            
            # Get primary guardian
            if student.primary_guardian_id:
                guardian = db.get(Guardian, student.primary_guardian_id)
            else:
                # Get any guardian
                guardian_link = db.execute(
                    select(StudentGuardian).where(
                        StudentGuardian.student_id == student.id
                    )
                ).scalars().first()
                
                guardian = db.get(Guardian, guardian_link.guardian_id) if guardian_link else None
            
            if not guardian or not guardian.email:
                logger.warning(f"No guardian email for student {student.admission_no}")
                notifications_failed += 1
                errors.append(f"No email for {student.first_name} {student.last_name}")
                continue
            
            # Calculate balance
            from app.models.payment import Payment
            payments = db.execute(
                select(Payment).where(Payment.invoice_id == invoice.id)
            ).scalars().all()
            
            total_paid = sum(float(p.amount) for p in payments)
            balance = float(invoice.total) - total_paid
            
            if balance <= 0:
                continue  # Skip if fully paid
            
            # Generate email content
            guardian_name = f"{guardian.first_name} {guardian.last_name}"
            student_name = f"{student.first_name} {student.last_name}"
            
            due_date = invoice.due_date.strftime("%B %d, %Y") if invoice.due_date else "Not specified"
            
            text_body, html_body = EmailTemplates.pending_invoice_notification(
                guardian_name=guardian_name,
                student_name=student_name,
                invoice_total=float(invoice.total),
                invoice_balance=balance,
                due_date=due_date,
                term=term,
                year=year
            )
            
            # Send email
            success = email_service.send_email(
                to_email=guardian.email,
                subject=f"School Fees Payment Reminder - {student_name} (Term {term} {year})",
                body_text=text_body,
                body_html=html_body
            )
            
            # Create notification record
            notification = Notification(
                school_id=str(school_id),
                type="EMAIL",
                subject=f"Pending Invoice - Term {term} {year}",
                body=text_body[:500],  # Store truncated version
                to_guardian_id=str(guardian.id),
                status="SENT" if success else "FAILED"
            )
            db.add(notification)
            
            if success:
                notifications_sent += 1
            else:
                notifications_failed += 1
                errors.append(f"Failed to send to {guardian.email}")
        
        db.commit()
        
        logger.info(
            f"Notification batch completed by {user.email}: "
            f"{notifications_sent} sent, {notifications_failed} failed"
        )
        
        return {
            "message": f"Notification process completed for Term {term} {year}",
            "sent": notifications_sent,
            "failed": notifications_failed,
            "errors": errors[:10]  # Limit error list
        }
    
    except Exception as e:
        logger.error(f"Error sending notifications: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send notifications"
        )


@router.post("/notify-specific-guardian", status_code=status.HTTP_200_OK)
async def notify_specific_guardian(
    student_id: UUID,
    subject: str,
    message: str,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Send a custom notification to a specific student's guardian"""
    school_id = UUID(ctx["school_id"])
    user = ctx["user"]
    
    # Get student
    student = db.execute(
        select(Student).where(
            Student.id == student_id,
            Student.school_id == school_id
        )
    ).scalar_one_or_none()
    
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Get primary guardian
    if student.primary_guardian_id:
        guardian = db.get(Guardian, student.primary_guardian_id)
    else:
        # Get any guardian
        guardian_link = db.execute(
            select(StudentGuardian).where(StudentGuardian.student_id == student.id)
        ).scalars().first()
        guardian = db.get(Guardian, guardian_link.guardian_id) if guardian_link else None
    
    if not guardian:
        raise HTTPException(
            status_code=404, 
            detail=f"No guardian found for {student.first_name} {student.last_name}"
        )
    
    if not guardian.email:
        raise HTTPException(
            status_code=404, 
            detail=f"Guardian {guardian.first_name} {guardian.last_name} has no email address"
        )
    
    # Send email
    success = email_service.send_email(
        to_email=guardian.email,
        subject=subject,
        body_text=message
    )
    
    # Create notification record
    notification = Notification(
        school_id=str(school_id),
        type="EMAIL",
        subject=subject,
        body=message[:500],
        to_guardian_id=str(guardian.id),
        status="SENT" if success else "FAILED"
    )
    db.add(notification)
    db.commit()
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send email")
    
    logger.info(
        f"Custom message sent to {guardian.email} regarding {student.first_name} {student.last_name} by {user.email}"
    )
    
    return {
        "message": "Notification sent successfully",
        "recipient": f"{guardian.first_name} {guardian.last_name}",
        "email": guardian.email,
        "student": f"{student.first_name} {student.last_name}"
    }

@router.get("/history", response_model=List[NotificationOut])
async def get_notification_history(
    limit: int = 50,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Get notification history for the school"""
    school_id = UUID(ctx["school_id"])
    
    notifications = db.execute(
        select(Notification)
        .where(Notification.school_id == str(school_id))
        .order_by(Notification.created_at.desc())
        .limit(limit)
    ).scalars().all()
    
    return [
        NotificationOut(
            id=n.id,
            type=n.type,
            subject=n.subject,
            body=n.body,
            to_guardian_id=n.to_guardian_id,
            to_user_id=n.to_user_id,
            status=n.status
        )
        for n in notifications
    ]

@router.post("/guardian-message", status_code=status.HTTP_200_OK)
async def send_guardian_message(
    notification_data: dict,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Send a custom message to all guardians of a specific student"""
    school_id = UUID(ctx["school_id"])
    user = ctx["user"]
    
    student_id = notification_data.get("student_id")
    message = notification_data.get("message")
    
    if not student_id or not message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="student_id and message are required"
        )
    
    try:
        student_uuid = UUID(student_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid student_id format"
        )
    
    # Get student
    student = db.execute(
        select(Student).where(
            Student.id == student_uuid,
            Student.school_id == school_id
        )
    ).scalar_one_or_none()
    
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    
    # Get all guardians for this student
    guardian_links = db.execute(
        select(StudentGuardian).where(
            StudentGuardian.student_id == student_uuid
        )
    ).scalars().all()
    
    if not guardian_links:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No guardians found for {student.first_name} {student.last_name}"
        )
    
    guardians = []
    for link in guardian_links:
        guardian = db.get(Guardian, link.guardian_id)
        if guardian and guardian.email:
            guardians.append(guardian)
    
    if not guardians:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No guardians with email addresses found"
        )
    
    # Send message to all guardians
    sent_count = 0
    failed_count = 0
    student_name = f"{student.first_name} {student.last_name}"
    
    for guardian in guardians:
        guardian_name = f"{guardian.first_name} {guardian.last_name}"
        
        # Create email body
        text_body = f"Dear {guardian_name},\n\n"
        text_body += f"This is a message regarding your child {student_name}:\n\n"
        text_body += f"{message}\n\n"
        text_body += f"Best regards,\n{user.email}"
        
        # Send email
        success = email_service.send_email(
            to_email=guardian.email,
            subject=f"Message regarding {student_name}",
            body_text=text_body
        )
        
        # Create notification record
        notification = Notification(
            school_id=str(school_id),
            type="EMAIL",
            subject=f"Message regarding {student_name}",
            body=text_body[:500],
            to_guardian_id=str(guardian.id),
            status="SENT" if success else "FAILED"
        )
        db.add(notification)
        
        if success:
            sent_count += 1
        else:
            failed_count += 1
    
    db.commit()
    
    logger.info(
        f"Message sent to {sent_count} guardian(s) for {student_name} by {user.email}"
    )
    
    return {
        "message": "Notification sent successfully",
        "sent_count": sent_count,
        "failed_count": failed_count,
        "student": student_name,
        "recipients": [f"{g.first_name} {g.last_name}" for g in guardians]
    }

@router.post("/broadcast", status_code=status.HTTP_200_OK)
async def broadcast_to_all_guardians(
    notification_data: dict,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Send a broadcast message to all guardians in the school"""
    school_id = UUID(ctx["school_id"])
    user = ctx["user"]
    
    message = notification_data.get("message")
    subject = notification_data.get("subject", "Important School Announcement")
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="message is required"
        )
    
    try:
        # Get all students in the school
        students = db.execute(
            select(Student).where(Student.school_id == school_id)
        ).scalars().all()
        
        if not students:
            return {
                "message": "No students found in the school",
                "sent_count": 0,
                "failed_count": 0,
                "total_guardians": 0
            }
        
        # Get all guardian IDs from student-guardian relationships
        student_ids = [student.id for student in students]
        
        guardian_links = db.execute(
            select(StudentGuardian).where(
                StudentGuardian.student_id.in_(student_ids)
            )
        ).scalars().all()
        
        if not guardian_links:
            return {
                "message": "No guardians found in the school",
                "sent_count": 0,
                "failed_count": 0,
                "total_guardians": 0
            }
        
        # Get unique guardian IDs
        guardian_ids = list(set(link.guardian_id for link in guardian_links))
        
        # Fetch all guardians with emails
        guardians = []
        for guardian_id in guardian_ids:
            guardian = db.get(Guardian, guardian_id)
            if guardian and guardian.email:
                guardians.append(guardian)
        
        if not guardians:
            return {
                "message": "No guardians with email addresses found",
                "sent_count": 0,
                "failed_count": 0,
                "total_guardians": 0
            }
        
        # Send message to all guardians
        sent_count = 0
        failed_count = 0
        
        for guardian in guardians:
            guardian_name = f"{guardian.first_name} {guardian.last_name}"
            
            # Create email body
            text_body = f"Dear {guardian_name},\n\n"
            text_body += f"{message}\n\n"
            text_body += f"Best regards,\nSchool Administration"
            
            # Send email
            success = email_service.send_email(
                to_email=guardian.email,
                subject=subject,
                body_text=text_body
            )
            
            # Create notification record
            notification = Notification(
                school_id=str(school_id),
                type="EMAIL",
                subject=subject,
                body=text_body[:500],
                to_guardian_id=str(guardian.id),
                status="SENT" if success else "FAILED"
            )
            db.add(notification)
            
            if success:
                sent_count += 1
            else:
                failed_count += 1
        
        db.commit()
        
        logger.info(
            f"Broadcast message sent to {sent_count}/{len(guardians)} guardians by {user.email}"
        )
        
        return {
            "message": "Broadcast completed",
            "sent_count": sent_count,
            "failed_count": failed_count,
            "total_guardians": len(guardians)
        }
    
    except Exception as e:
        logger.error(f"Error broadcasting message: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send broadcast message: {str(e)}"
        )
    
@router.post("/unpaid-balances", status_code=status.HTTP_200_OK)
async def notify_guardians_with_balances(
    notification_data: dict,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Send fee reminders to guardians whose students have outstanding balances"""
    school_id = UUID(ctx["school_id"])
    user = ctx["user"]
    
    year = notification_data.get("year")
    term = notification_data.get("term")
    
    if not year or not term:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="year and term are required"
        )
    
    try:
        # Get all unpaid/partial invoices for the term
        invoices = db.execute(
            select(Invoice).where(
                Invoice.school_id == school_id,
                Invoice.year == year,
                Invoice.term == term,
                Invoice.status.in_(["ISSUED", "PARTIAL"])
            )
        ).scalars().all()
        
        if not invoices:
            return {
                "message": f"No outstanding balances found for Term {term} {year}",
                "notifications_sent": 0,
                "failed": 0
            }
        
        notifications_sent = 0
        notifications_failed = 0
        errors = []
        
        for invoice in invoices:
            # Calculate balance from payments
            from app.models.payment import Payment
            payments = db.execute(
                select(Payment).where(Payment.invoice_id == invoice.id)
            ).scalars().all()
            
            total_paid = sum(float(p.amount) for p in payments)
            balance = float(invoice.total) - total_paid
            
            # Skip if no balance
            if balance <= 0:
                continue
            
            # Get student
            student = db.get(Student, invoice.student_id)
            if not student:
                continue
            
            # Get primary guardian or any guardian
            if student.primary_guardian_id:
                guardian = db.get(Guardian, student.primary_guardian_id)
            else:
                guardian_link = db.execute(
                    select(StudentGuardian).where(
                        StudentGuardian.student_id == student.id
                    )
                ).scalars().first()
                
                guardian = db.get(Guardian, guardian_link.guardian_id) if guardian_link else None
            
            if not guardian or not guardian.email:
                logger.warning(f"No guardian email for student {student.admission_no}")
                notifications_failed += 1
                errors.append(f"No email for {student.first_name} {student.last_name}")
                continue
            
            # Generate email content
            guardian_name = f"{guardian.first_name} {guardian.last_name}"
            student_name = f"{student.first_name} {student.last_name}"
            
            due_date = invoice.due_date.strftime("%B %d, %Y") if invoice.due_date else "Not specified"
            
            text_body, html_body = EmailTemplates.pending_invoice_notification(
                guardian_name=guardian_name,
                student_name=student_name,
                invoice_total=float(invoice.total),
                invoice_balance=balance,
                due_date=due_date,
                term=term,
                year=year
            )
            
            # Send email
            success = email_service.send_email(
                to_email=guardian.email,
                subject=f"Fee Balance Reminder - {student_name} (Term {term} {year})",
                body_text=text_body,
                body_html=html_body
            )
            
            # Create notification record
            notification = Notification(
                school_id=str(school_id),
                type="EMAIL",
                subject=f"Fee Balance - Term {term} {year}",
                body=text_body[:500],
                to_guardian_id=str(guardian.id),
                status="SENT" if success else "FAILED"
            )
            db.add(notification)
            
            if success:
                notifications_sent += 1
            else:
                notifications_failed += 1
                errors.append(f"Failed to send to {guardian.email}")
        
        db.commit()
        
        logger.info(
            f"Balance notifications sent by {user.email}: "
            f"{notifications_sent} sent, {notifications_failed} failed"
        )
        
        return {
            "message": f"Notification process completed for Term {term} {year}",
            "notifications_sent": notifications_sent,
            "failed": notifications_failed,
            "errors": errors[:10]
        }
    
    except Exception as e:
        logger.error(f"Error sending balance notifications: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send balance notifications"
        )