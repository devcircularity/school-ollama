# app/services/auth_service.py - Authentication business logic
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.core.config import settings
from app.core.security import (
    hash_password, 
    verify_password, 
    create_access_token,
    generate_reset_token,
    hash_reset_token
)
from app.models.user import User
from app.models.password_reset import PasswordResetToken
from app.models.school import SchoolMember

logger = logging.getLogger(__name__)

class AuthService:
    """Service class for authentication operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_user(
        self, 
        email: str, 
        full_name: str, 
        password: str,
        roles: List[str] = None
    ) -> User:
        """
        Create a new user account
        
        Args:
            email: User email (will be lowercased)
            full_name: User's full name
            password: Plain text password (will be hashed)
            roles: List of user roles (defaults to ['ADMIN'])
        
        Returns:
            Created User object
        
        Raises:
            ValueError: If user already exists
        """
        email = email.lower().strip()
        
        # Check if user exists
        existing_user = self.db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        
        if existing_user:
            raise ValueError("User with this email already exists")
        
        # Set default roles if not provided
        if roles is None:
            roles = ["ADMIN"]
        
        # Create user
        user = User(
            email=email,
            full_name=full_name.strip(),
            password_hash=hash_password(password),
            is_active=True,
            is_verified=False
        )
        
        # Set roles
        user.set_roles(roles)
        
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        logger.info(f"User created: {email}")
        return user
    
    def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """
        Authenticate user with email and password
        
        Args:
            email: User email
            password: Plain text password
        
        Returns:
            User object if authentication successful, None otherwise
        """
        email = email.lower().strip()
        
        user = self.db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        
        if not user or not user.is_active:
            return None
        
        if not verify_password(password, user.password_hash):
            return None
        
        # Update last login
        user.last_login = datetime.utcnow()
        self.db.commit()
        
        logger.info(f"User authenticated: {email}")
        return user
    
    def get_user_schools(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get schools that user is a member of
        
        Args:
            user_id: User UUID as string
        
        Returns:
            List of school dictionaries with id, name, and role
        """
        memberships = self.db.execute(
            select(SchoolMember).where(SchoolMember.user_id == user_id)
        ).scalars().all()
        
        schools = []
        for membership in memberships:
            school = self.db.get(School, membership.school_id)
            if school:
                schools.append({
                    "id": str(membership.school_id),
                    "name": school.name,
                    "role": membership.role
                })
        
        return schools
    
    def create_access_token_for_user(self, user: User, active_school_id: str = None) -> str:
        """
        Create access token for authenticated user
        
        Args:
            user: Authenticated user object
            active_school_id: Optional active school ID for the session
        
        Returns:
            JWT access token string
        """
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "roles": user.roles
        }
        
        if active_school_id:
            token_data["active_school_id"] = active_school_id
        
        return create_access_token(token_data)
    
    def initiate_password_reset(self, email: str, client_ip: str = None) -> bool:
        """
        Initiate password reset process
        
        Args:
            email: User email
            client_ip: Client IP address for security logging
        
        Returns:
            True if reset initiated (or if email doesn't exist - for security)
        """
        email = email.lower().strip()
        
        user = self.db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        
        if not user or not user.is_active:
            # Don't reveal if user exists
            logger.info(f"Password reset attempted for non-existent user: {email}")
            return True
        
        # Check if user has too many active tokens
        if user.get_active_reset_tokens_count() >= 3:
            logger.warning(f"Too many reset tokens for user: {email}")
            return True
        
        # Generate reset token
        plain_token = generate_reset_token()
        hashed_token = hash_reset_token(plain_token)
        
        # Create reset token record
        reset_token = PasswordResetToken(
            user_id=user.id,
            token=hashed_token,
            expires_at=datetime.utcnow() + timedelta(hours=settings.RESET_TOKEN_EXPIRE_HOURS),
            created_ip=client_ip
        )
        
        self.db.add(reset_token)
        self.db.commit()
        
        # Send reset email
        if settings.SMTP_HOST:
            try:
                self._send_reset_email(user.email, user.full_name, plain_token)
            except Exception as e:
                logger.error(f"Failed to send reset email to {email}: {e}")
        else:
            # In development, log the token
            if settings.ENV == "dev":
                logger.info(f"DEV: Reset token for {email}: {plain_token}")
        
        logger.info(f"Password reset initiated for: {email}")
        return True
    
    def verify_reset_token(self, email: str, token: str) -> bool:
        """
        Verify that a reset token is valid
        
        Args:
            email: User email
            token: Plain reset token
        
        Returns:
            True if token is valid and not expired
        """
        email = email.lower().strip()
        
        user = self.db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        
        if not user:
            return False
        
        hashed_token = hash_reset_token(token)
        
        reset_token = self.db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.token == hashed_token
            )
        ).scalar_one_or_none()
        
        return reset_token is not None and reset_token.is_valid()
    
    def reset_password(self, email: str, token: str, new_password: str, client_ip: str = None) -> bool:
        """
        Reset user password using valid token
        
        Args:
            email: User email
            token: Plain reset token
            new_password: New password (will be hashed)
            client_ip: Client IP address for security logging
        
        Returns:
            True if password was reset successfully
        
        Raises:
            ValueError: If token is invalid or expired
        """
        email = email.lower().strip()
        
        user = self.db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        
        if not user:
            raise ValueError("Invalid reset token")
        
        hashed_token = hash_reset_token(token)
        
        reset_token = self.db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.token == hashed_token
            )
        ).scalar_one_or_none()
        
        if not reset_token or not reset_token.is_valid():
            raise ValueError("Invalid or expired reset token")
        
        # Update password
        user.password_hash = hash_password(new_password)
        
        # Mark token as used
        reset_token.mark_used(client_ip)
        
        self.db.commit()
        
        logger.info(f"Password reset completed for: {email}")
        return True
    
    def _send_reset_email(self, email: str, full_name: str, token: str):
        """
        Send password reset email
        
        Args:
            email: Recipient email
            full_name: Recipient name
            token: Plain reset token
        """
        if not settings.SMTP_HOST:
            logger.warning("SMTP not configured, cannot send reset email")
            return
        
        # Create reset URL (you'll need to adjust this for your frontend)
        reset_url = f"https://your-frontend-domain.com/reset-password?token={token}&email={email}"
        
        # Email content
        subject = "Reset Your School Assistant Password"
        html_content = f"""
        <html>
            <body>
                <h2>Password Reset Request</h2>
                <p>Hello {full_name},</p>
                <p>You requested to reset your password for School Assistant. Click the link below to reset your password:</p>
                <p><a href="{reset_url}">Reset Password</a></p>
                <p>This link will expire in {settings.RESET_TOKEN_EXPIRE_HOURS} hours.</p>
                <p>If you didn't request this reset, please ignore this email.</p>
                <p>Best regards,<br>School Assistant Team</p>
            </body>
        </html>
        """
        
        text_content = f"""
        Hello {full_name},
        
        You requested to reset your password for School Assistant. 
        Click the link below to reset your password:
        
        {reset_url}
        
        This link will expire in {settings.RESET_TOKEN_EXPIRE_HOURS} hours.
        
        If you didn't request this reset, please ignore this email.
        
        Best regards,
        School Assistant Team
        """
        
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg["To"] = email
        
        # Attach parts
        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))
        
        # Send email
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Reset email sent to: {email}")