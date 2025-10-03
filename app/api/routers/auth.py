# app/api/routers/auth.py - Fixed to work with new TokenManager
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timedelta
from typing import Dict, Any
import logging

from app.core.db import get_db
from app.core.security import (
    token_manager,  # Use the new token_manager instance
    password_manager,  # Use the new password_manager instance
    reset_token_manager,  # Use the new reset_token_manager instance
)
from app.api.deps.auth import get_current_user
from app.models.user import User
from app.models.password_reset import PasswordResetToken
from app.models.school import SchoolMember
from app.schemas.auth import (
    RegisterIn, 
    LoginIn, 
    LoginOut, 
    SwitchSchoolIn,
    ForgotPasswordIn,
    ForgotPasswordOut,
    VerifyResetTokenIn,
    VerifyResetTokenOut,
    ResetPasswordIn,
    ResetPasswordOut
)

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/register", response_model=LoginOut, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: RegisterIn,
    request: Request,
    db: Session = Depends(get_db)
):
    """Register a new user account"""
    
    # Validate password strength using new password_manager
    validation_result = password_manager.validate_password_strength(user_data.password)
    if not validation_result["valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="; ".join(validation_result["feedback"])
        )
    
    # Check if user already exists
    existing_user = db.execute(
        select(User).where(User.email == user_data.email.lower())
    ).scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists"
        )
    
    # Create new user with new password_manager
    hashed_password = password_manager.hash_password(user_data.password)
    new_user = User(
        email=user_data.email.lower(),
        full_name=user_data.full_name,
        password_hash=hashed_password,
        roles_csv="ADMIN",
        is_active=True,
        is_verified=False
    )
    
    db.add(new_user)
    
    try:
        db.commit()
        db.refresh(new_user)
        logger.info(f"New user registered: {new_user.email}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating user account"
        )
    
    # Create access token using new token_manager with proper parameters
    additional_claims = {
        "email": new_user.email,
        "roles": new_user.roles
    }
    
    access_token = token_manager.create_access_token(
        subject=str(new_user.id),
        additional_claims=additional_claims
    )
    
    logger.info(f"Token created for new user: {new_user.email}")
    
    return LoginOut(
        access_token=access_token,
        token_type="bearer"
    )

@router.post("/login", response_model=LoginOut)
async def login(
    credentials: LoginIn,
    request: Request,
    db: Session = Depends(get_db)
):
    """Authenticate user and return access token"""
    
    # Find user by email
    user = db.execute(
        select(User).where(User.email == credentials.email.lower())
    ).scalar_one_or_none()
    
    # Use new password_manager for verification
    if not user or not password_manager.verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated"
        )
    
    # Update last login
    user.last_login = datetime.utcnow()
    
    # Get user's school memberships for token
    memberships = db.execute(
        select(SchoolMember).where(SchoolMember.user_id == user.id)
    ).scalars().all()
    
    # If user has exactly one school, set it as active
    active_school_id = None
    if len(memberships) == 1:
        active_school_id = str(memberships[0].school_id)
    
    # Create access token using new token_manager with proper parameters
    additional_claims = {
        "email": user.email,
        "roles": user.roles,
        "active_school_id": active_school_id
    }
    
    access_token = token_manager.create_access_token(
        subject=str(user.id),
        additional_claims=additional_claims
    )
    
    try:
        db.commit()
        logger.info(f"User logged in: {user.email}, token created")
    except Exception as e:
        logger.error(f"Error updating last login: {e}")
        # Don't fail login for this
    
    return LoginOut(
        access_token=access_token,
        token_type="bearer",
        school_id=active_school_id
    )

@router.post("/activate-school", response_model=LoginOut)
async def activate_school(
    school_data: SwitchSchoolIn,
    ctx: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Switch/activate a school for multi-school users"""
    user = ctx["user"]
    
    # Verify user is a member of the school
    membership = db.execute(
        select(SchoolMember).where(
            SchoolMember.user_id == user.id,
            SchoolMember.school_id == school_data.school_id
        )
    ).scalar_one_or_none()
    
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this school"
        )
    
    # Create new token with active school using new token_manager
    additional_claims = {
        "email": user.email,
        "roles": user.roles,
        "active_school_id": school_data.school_id
    }
    
    access_token = token_manager.create_access_token(
        subject=str(user.id),
        additional_claims=additional_claims
    )
    
    return LoginOut(
        access_token=access_token,
        token_type="bearer",
        school_id=school_data.school_id
    )

@router.post("/refresh", response_model=LoginOut)
async def refresh_token(
    ctx: Dict[str, Any] = Depends(get_current_user)
):
    """Refresh access token"""
    user = ctx["user"]
    claims = ctx["claims"]
    
    logger.info(f"Refreshing token for user: {user.email}")
    
    # Create new access token with same claims using new token_manager
    additional_claims = {
        "email": user.email,
        "roles": user.roles,
        "active_school_id": claims.get("active_school_id")
    }
    
    access_token = token_manager.create_access_token(
        subject=str(user.id),
        additional_claims=additional_claims
    )
    
    return LoginOut(
        access_token=access_token,
        token_type="bearer",
        school_id=claims.get("active_school_id")
    )

@router.get("/me")
async def get_current_user_info(
    ctx: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user information and school memberships"""
    user = ctx["user"]
    claims = ctx["claims"]
    
    # Get user's school memberships
    memberships = db.execute(
        select(SchoolMember).where(SchoolMember.user_id == user.id)
    ).scalars().all()
    
    schools = []
    for membership in memberships:
        # Import School model here to avoid circular imports
        from app.models.school import School
        school = db.get(School, membership.school_id)
        if school:
            schools.append({
                "id": str(membership.school_id),
                "name": school.name,
                "role": membership.role
            })
    
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "roles": user.roles,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "last_login": user.last_login,
        "active_school_id": claims.get("active_school_id"),
        "schools": schools
    }

@router.post("/forgot-password", response_model=ForgotPasswordOut)
async def forgot_password(
    request_data: ForgotPasswordIn,
    request: Request,
    db: Session = Depends(get_db)
):
    """Initiate password reset process"""
    
    user = db.execute(
        select(User).where(User.email == request_data.email.lower())
    ).scalar_one_or_none()
    
    success_message = "If an account with this email exists, you will receive password reset instructions."
    
    if not user or not user.is_active:
        return ForgotPasswordOut(message=success_message)
    
    if user.get_active_reset_tokens_count() >= 3:
        logger.warning(f"Too many reset tokens for user: {user.email}")
        return ForgotPasswordOut(message=success_message)
    
    # Generate reset token using new reset_token_manager
    plain_token = reset_token_manager.generate_reset_token()
    hashed_token = reset_token_manager.hash_reset_token(plain_token)
    
    client_ip = getattr(request, "client", {}).get("host", "unknown")
    
    reset_token = PasswordResetToken(
        user_id=user.id,
        token=hashed_token,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        created_ip=client_ip
    )
    
    db.add(reset_token)
    
    try:
        db.commit()
        logger.info(f"Password reset token created for user: {user.email}")
        
        # TODO: Send email
        if request.app.state.env == "dev":
            logger.info(f"DEV: Reset token for {user.email}: {plain_token}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating reset token: {e}")
    
    return ForgotPasswordOut(message=success_message)

@router.post("/reset-password", response_model=ResetPasswordOut)
async def reset_password(
    reset_data: ResetPasswordIn,
    request: Request,
    db: Session = Depends(get_db)
):
    """Reset user password using valid reset token"""
    
    # Validate password strength using new password_manager
    validation_result = password_manager.validate_password_strength(reset_data.password)
    if not validation_result["valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="; ".join(validation_result["feedback"])
        )
    
    user = db.execute(
        select(User).where(User.email == reset_data.email.lower())
    ).scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token"
        )
    
    # Hash and verify token using new reset_token_manager
    hashed_token = reset_token_manager.hash_reset_token(reset_data.token)
    
    reset_token = db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.token == hashed_token
        )
    ).scalar_one_or_none()
    
    if not reset_token or not reset_token.is_valid():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    client_ip = getattr(request, "client", {}).get("host", "unknown")
    
    # Update password using new password_manager
    user.password_hash = password_manager.hash_password(reset_data.password)
    reset_token.mark_used(ip_address=client_ip)
    
    try:
        db.commit()
        logger.info(f"Password reset successful for user: {user.email}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error resetting password: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error resetting password"
        )
    
    return ResetPasswordOut(message="Password has been successfully reset")