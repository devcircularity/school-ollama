import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
import logging
from jinja2 import Template

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Email service using SMTP (Brevo)"""
    
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME
        self.use_tls = settings.SMTP_USE_TLS
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        reply_to: Optional[str] = None
    ) -> bool:
        """Send an email via SMTP"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            
            if reply_to:
                msg['Reply-To'] = reply_to
            
            # Attach text version
            text_part = MIMEText(body_text, 'plain', 'utf-8')
            msg.attach(text_part)
            
            # Attach HTML version if provided
            if body_html:
                html_part = MIMEText(body_html, 'html', 'utf-8')
                msg.attach(html_part)
            
            # Connect and send
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}", exc_info=True)
            return False
    
    def send_bulk_emails(
        self,
        recipients: List[dict],  # [{"email": "...", "name": "..."}]
        subject: str,
        body_text: str,
        body_html: Optional[str] = None
    ) -> dict:
        """Send emails to multiple recipients"""
        results = {
            "success": 0,
            "failed": 0,
            "errors": []
        }
        
        for recipient in recipients:
            email = recipient.get("email")
            if not email:
                results["failed"] += 1
                results["errors"].append(f"No email for {recipient.get('name', 'Unknown')}")
                continue
            
            success = self.send_email(
                to_email=email,
                subject=subject,
                body_text=body_text,
                body_html=body_html
            )
            
            if success:
                results["success"] += 1
            else:
                results["failed"] += 1
                results["errors"].append(f"Failed to send to {email}")
        
        return results


# Email Templates
class EmailTemplates:
    """Email templates for common notifications"""
    
    @staticmethod
    def pending_invoice_notification(
        guardian_name: str,
        student_name: str,
        invoice_total: float,
        invoice_balance: float,
        due_date: str,
        term: int,
        year: int
    ) -> tuple[str, str]:
        """Generate pending invoice email (text and HTML)"""
        
        # Text version
        text = f"""
Dear {guardian_name},

This is a reminder about the pending school fees for {student_name}.

Invoice Details:
- Academic Term: Term {term}, {year}
- Total Amount: KES {invoice_total:,.2f}
- Amount Paid: KES {(invoice_total - invoice_balance):,.2f}
- Balance Due: KES {invoice_balance:,.2f}
- Due Date: {due_date}

Please make payment at your earliest convenience to avoid any disruption to your child's education.

Payment Methods:
- M-PESA Paybill: [School Paybill Number]
- Bank Transfer: [School Bank Details]
- Cash/Cheque at School Office

For any queries, please contact the school office.

Best regards,
School Administration
"""
        
        # HTML version
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
        .content {{ background-color: #f9f9f9; padding: 20px; border-radius: 5px; margin: 20px 0; }}
        .invoice-details {{ background-color: white; padding: 15px; border-left: 4px solid #4CAF50; }}
        .amount {{ font-size: 24px; font-weight: bold; color: #4CAF50; }}
        .balance {{ font-size: 24px; font-weight: bold; color: #ff6b6b; }}
        .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>School Fees Payment Reminder</h2>
        </div>
        
        <div class="content">
            <p>Dear {guardian_name},</p>
            
            <p>This is a reminder about the pending school fees for <strong>{student_name}</strong>.</p>
            
            <div class="invoice-details">
                <h3>Invoice Details</h3>
                <table width="100%" style="margin: 15px 0;">
                    <tr>
                        <td><strong>Academic Term:</strong></td>
                        <td>Term {term}, {year}</td>
                    </tr>
                    <tr>
                        <td><strong>Total Amount:</strong></td>
                        <td class="amount">KES {invoice_total:,.2f}</td>
                    </tr>
                    <tr>
                        <td><strong>Amount Paid:</strong></td>
                        <td>KES {(invoice_total - invoice_balance):,.2f}</td>
                    </tr>
                    <tr>
                        <td><strong>Balance Due:</strong></td>
                        <td class="balance">KES {invoice_balance:,.2f}</td>
                    </tr>
                    <tr>
                        <td><strong>Due Date:</strong></td>
                        <td>{due_date}</td>
                    </tr>
                </table>
            </div>
            
            <p>Please make payment at your earliest convenience to avoid any disruption to your child's education.</p>
            
            <h4>Payment Methods:</h4>
            <ul>
                <li><strong>M-PESA Paybill:</strong> [School Paybill Number]</li>
                <li><strong>Bank Transfer:</strong> [School Bank Details]</li>
                <li><strong>Cash/Cheque:</strong> School Office</li>
            </ul>
            
            <p>For any queries, please contact the school office.</p>
        </div>
        
        <div class="footer">
            <p>This is an automated message from School Assistant.</p>
            <p>&copy; 2025 School Assistant. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
"""
        
        return text, html


# Singleton instance
email_service = EmailService()