# app/core/security.py - Authentication utilities (JWT, password hashing, reset tokens)
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Union, List
import secrets
import hashlib
import hmac
import re
from urllib.parse import urlparse

import jwt
from passlib.context import CryptContext
from passlib.hash import bcrypt
from fastapi import HTTPException, status
from email.utils import parseaddr

from app.core.config import settings

# Password hashing context with multiple schemes and security settings
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.BCRYPT_ROUNDS,
    bcrypt__ident="2b"  # Use the latest bcrypt variant
)

class SecurityError(Exception):
    """Custom exception for security-related errors"""
    pass

class TokenManager:
    """Manages JWT token creation, validation, and refresh"""
    
    def __init__(self):
        self.secret_key = settings.JWT_SECRET
        self.algorithm = settings.JWT_ALGORITHM
        self.issuer = settings.JWT_ISSUER
        self.audience = settings.JWT_AUDIENCE
        self.access_token_expire_minutes = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    
    def create_access_token(
        self,
        subject: Union[str, Any],
        expires_delta: Optional[timedelta] = None,
        additional_claims: Optional[Dict[str, Any]] = None,
        scopes: Optional[List[str]] = None
    ) -> str:
        """
        Create a JWT access token.
        
        Args:
            subject: Token subject (usually user ID)
            expires_delta: Custom expiration time
            additional_claims: Additional JWT claims
            scopes: Token scopes/permissions
            
        Returns:
            Encoded JWT token string
            
        Raises:
            SecurityError: If token creation fails
        """
        try:
            now = datetime.now(timezone.utc)
            
            if expires_delta:
                expire = now + expires_delta
            else:
                expire = now + timedelta(minutes=self.access_token_expire_minutes)
            
            # Build JWT payload
            payload = {
                "sub": str(subject),
                "iat": now,
                "exp": expire,
                "iss": self.issuer,
                "aud": self.audience,
                "type": "access",
                "jti": secrets.token_hex(16),  # JWT ID for tracking
            }
            
            # Add scopes if provided
            if scopes:
                payload["scope"] = " ".join(scopes)
            
            # Add additional claims
            if additional_claims:
                # Validate additional claims don't override reserved claims
                reserved_claims = {"sub", "iat", "exp", "iss", "aud", "type", "jti", "scope"}
                for claim in additional_claims:
                    if claim in reserved_claims:
                        raise SecurityError(f"Cannot override reserved JWT claim: {claim}")
                payload.update(additional_claims)
            
            # Encode token
            token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
            return token
            
        except jwt.PyJWTError as e:
            raise SecurityError(f"Failed to create access token: {e}")
        except Exception as e:
            raise SecurityError(f"Unexpected error creating token: {e}")
    
    def create_refresh_token(
        self,
        subject: Union[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create a JWT refresh token with longer expiration.
        
        Args:
            subject: Token subject (usually user ID)
            expires_delta: Custom expiration time
            
        Returns:
            Encoded JWT refresh token string
        """
        now = datetime.now(timezone.utc)
        
        if expires_delta:
            expire = now + expires_delta
        else:
            expire = now + timedelta(days=self.refresh_token_expire_days)
        
        payload = {
            "sub": str(subject),
            "iat": now,
            "exp": expire,
            "iss": self.issuer,
            "aud": self.audience,
            "type": "refresh",
            "jti": secrets.token_hex(16),
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def decode_token(
        self,
        token: str,
        expected_type: str = "access",
        verify_exp: bool = True
    ) -> Dict[str, Any]:
        """
        Decode and validate a JWT token.
        
        Args:
            token: JWT token string
            expected_type: Expected token type ("access" or "refresh")
            verify_exp: Whether to verify expiration
            
        Returns:
            Dictionary containing token claims
            
        Raises:
            HTTPException: If token is invalid or expired
        """
        try:
            # Decode token
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                audience=self.audience,
                issuer=self.issuer,
                options={"verify_exp": verify_exp}
            )
            
            # Verify token type
            if payload.get("type") != expected_type:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid token type. Expected {expected_type}",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            return payload
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    def refresh_access_token(self, refresh_token: str) -> str:
        """
        Create a new access token from a valid refresh token.
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            New access token
        """
        # Decode refresh token
        payload = self.decode_token(refresh_token, expected_type="refresh")
        
        # Create new access token with same subject
        return self.create_access_token(subject=payload["sub"])
    
    def get_token_subject(self, token: str) -> str:
        """
        Extract subject from token without full validation.
        Useful for logging/debugging.
        
        Args:
            token: JWT token string
            
        Returns:
            Token subject
        """
        try:
            payload = jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": False}
            )
            return payload.get("sub", "unknown")
        except Exception:
            return "invalid"

class PasswordManager:
    """Manages password hashing, verification, and strength validation"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using bcrypt.
        
        Args:
            password: Plain text password
            
        Returns:
            Hashed password string
        """
        if not password:
            raise SecurityError("Password cannot be empty")
        
        return pwd_context.hash(password)
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash.
        
        Args:
            plain_password: Plain text password
            hashed_password: Previously hashed password
            
        Returns:
            True if password matches, False otherwise
        """
        if not plain_password or not hashed_password:
            return False
        
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception:
            return False
    
    @staticmethod
    def needs_update(hashed_password: str) -> bool:
        """
        Check if password hash needs updating (e.g., due to changed rounds).
        
        Args:
            hashed_password: Previously hashed password
            
        Returns:
            True if hash should be updated
        """
        return pwd_context.needs_update(hashed_password)
    
    @staticmethod
    def validate_password_strength(password: str) -> Dict[str, Any]:
        """
        Validate password strength with detailed feedback.
        
        Args:
            password: Password to validate
            
        Returns:
            Dictionary with validation results
        """
        if not password:
            return {
                "valid": False,
                "score": 0,
                "feedback": ["Password cannot be empty"],
                "requirements": {
                    "min_length": False,
                    "has_uppercase": False,
                    "has_lowercase": False,
                    "has_digit": False,
                    "has_special": False,
                    "no_common_patterns": False
                }
            }
        
        feedback = []
        requirements = {
            "min_length": len(password) >= 8,
            "has_uppercase": bool(re.search(r'[A-Z]', password)),
            "has_lowercase": bool(re.search(r'[a-z]', password)),
            "has_digit": bool(re.search(r'\d', password)),
            "has_special": bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password)),
            "no_common_patterns": True  # Will be updated below
        }
        
        # Check minimum length
        if not requirements["min_length"]:
            feedback.append("Password must be at least 8 characters long")
        
        # Check character types
        if not requirements["has_uppercase"]:
            feedback.append("Password must contain at least one uppercase letter")
        if not requirements["has_lowercase"]:
            feedback.append("Password must contain at least one lowercase letter")
        if not requirements["has_digit"]:
            feedback.append("Password must contain at least one digit")
        if not requirements["has_special"]:
            feedback.append("Password must contain at least one special character")
        
        # Check for common patterns
        common_patterns = [
            r'(.)\1{2,}',  # Repeated characters (aaa, 111)
            r'(012|123|234|345|456|567|678|789|890)',  # Sequential numbers
            r'(abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)',  # Sequential letters
            r'(qwert|asdf|zxcv)',  # Keyboard patterns
        ]
        
        for pattern in common_patterns:
            if re.search(pattern, password.lower()):
                requirements["no_common_patterns"] = False
                feedback.append("Password should not contain common patterns or sequences")
                break
        
        # Check against common passwords
        if password.lower() in [
            "password", "123456", "password123", "admin", "letmein",
            "welcome", "monkey", "1234567890", "qwerty", "abc123"
        ]:
            requirements["no_common_patterns"] = False
            feedback.append("Password is too common")
        
        # Calculate score
        score = sum(requirements.values())
        valid = score == len(requirements)
        
        return {
            "valid": valid,
            "score": score,
            "max_score": len(requirements),
            "feedback": feedback if feedback else ["Password meets all requirements"],
            "requirements": requirements
        }
    
    @staticmethod
    def get_password_strength_message() -> str:
        """Get password requirements message"""
        return (
            "Password must be at least 8 characters long and contain "
            "at least one uppercase letter, one lowercase letter, one digit, "
            "and one special character. Avoid common patterns and sequences."
        )

class ResetTokenManager:
    """Manages password reset tokens with security features"""
    
    @staticmethod
    def generate_reset_token(length: int = None) -> str:
        """
        Generate a cryptographically secure reset token.
        
        Args:
            length: Token length in bytes (default from settings)
            
        Returns:
            URL-safe random token string
        """
        if length is None:
            length = settings.RESET_TOKEN_LENGTH
        
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def hash_reset_token(token: str) -> str:
        """
        Hash a reset token for secure storage using SHA-256.
        
        Args:
            token: Plain reset token
            
        Returns:
            Hashed token string (hex encoded)
        """
        if not token:
            raise SecurityError("Reset token cannot be empty")
        
        # Use HMAC-SHA256 with secret for additional security
        return hmac.new(
            settings.JWT_SECRET.encode(),
            token.encode(),
            hashlib.sha256
        ).hexdigest()
    
    @staticmethod
    def verify_reset_token(plain_token: str, hashed_token: str) -> bool:
        """
        Verify a reset token against its hash using timing-safe comparison.
        
        Args:
            plain_token: Plain reset token from user
            hashed_token: Stored hashed token
            
        Returns:
            True if tokens match, False otherwise
        """
        if not plain_token or not hashed_token:
            return False
        
        try:
            computed_hash = ResetTokenManager.hash_reset_token(plain_token)
            # Use timing-safe comparison to prevent timing attacks
            return secrets.compare_digest(computed_hash, hashed_token)
        except Exception:
            return False

class SecurityUtils:
    """Utility functions for security operations"""
    
    @staticmethod
    def generate_api_key(prefix: str = "sk", length: int = 32) -> str:
        """
        Generate a secure API key with prefix.
        
        Args:
            prefix: Key prefix
            length: Key length in bytes
            
        Returns:
            API key string
        """
        key = secrets.token_urlsafe(length)
        return f"{prefix}_{key}"
    
    @staticmethod
    def validate_email_format(email: str) -> bool:
        """
        Validate email format using RFC-compliant parsing.
        
        Args:
            email: Email address to validate
            
        Returns:
            True if email format is valid
        """
        if not email:
            return False
        
        try:
            # Use email.utils.parseaddr which follows RFC standards
            name, addr = parseaddr(email)
            return "@" in addr and "." in addr.split("@")[1]
        except Exception:
            return False
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize filename for safe storage.
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename
        """
        if not filename:
            return "unnamed_file"
        
        # Remove directory traversal attempts
        filename = filename.replace("/", "_").replace("\\", "_")
        # Remove null bytes and control characters
        filename = "".join(c for c in filename if ord(c) > 31)
        # Limit length
        if len(filename) > 255:
            name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
            filename = name[:250] + ("." + ext if ext else "")
        
        return filename or "unnamed_file"
    
    @staticmethod
    def validate_url(url: str, allowed_schemes: List[str] = None) -> bool:
        """
        Validate URL format and scheme.
        
        Args:
            url: URL to validate
            allowed_schemes: List of allowed URL schemes
            
        Returns:
            True if URL is valid and safe
        """
        if not url:
            return False
        
        if allowed_schemes is None:
            allowed_schemes = ["http", "https"]
        
        try:
            parsed = urlparse(url)
            return (
                parsed.scheme in allowed_schemes and
                parsed.netloc and
                not parsed.netloc.startswith("localhost") or settings.is_development
            )
        except Exception:
            return False
    
    @staticmethod
    def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
        """
        Mask sensitive data for logging (e.g., API keys, tokens).
        
        Args:
            data: Sensitive data to mask
            visible_chars: Number of characters to show at the end
            
        Returns:
            Masked string
        """
        if not data or len(data) <= visible_chars:
            return "*" * len(data) if data else ""
        
        return "*" * (len(data) - visible_chars) + data[-visible_chars:]

# Create global instances
token_manager = TokenManager()
password_manager = PasswordManager()
reset_token_manager = ResetTokenManager()
security_utils = SecurityUtils()

# Convenience functions for backward compatibility
def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create access token (backward compatibility)"""
    subject = data.get("sub")
    if not subject:
        raise SecurityError("Token data must include 'sub' (subject)")
    
    additional_claims = {k: v for k, v in data.items() if k != "sub"}
    return token_manager.create_access_token(subject, expires_delta, additional_claims)

def decode_token(token: str) -> Dict[str, Any]:
    """Decode token (backward compatibility)"""
    return token_manager.decode_token(token)

def hash_password(password: str) -> str:
    """Hash password (backward compatibility)"""
    return password_manager.hash_password(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password (backward compatibility)"""
    return password_manager.verify_password(plain_password, hashed_password)

def validate_password_strength(password: str) -> bool:
    """Validate password strength (backward compatibility - returns boolean)"""
    return password_manager.validate_password_strength(password)["valid"]

def get_password_strength_message() -> str:
    """Get password requirements message (backward compatibility)"""
    return password_manager.get_password_strength_message()

def generate_reset_token(length: int = None) -> str:
    """Generate reset token (backward compatibility)"""
    return reset_token_manager.generate_reset_token(length)

def hash_reset_token(token: str) -> str:
    """Hash reset token (backward compatibility)"""
    return reset_token_manager.hash_reset_token(token)

def verify_reset_token(plain_token: str, hashed_token: str) -> bool:
    """Verify reset token (backward compatibility)"""
    return reset_token_manager.verify_reset_token(plain_token, hashed_token)

# Export all public functions and classes
__all__ = [
    "TokenManager", "PasswordManager", "ResetTokenManager", "SecurityUtils",
    "token_manager", "password_manager", "reset_token_manager", "security_utils",
    "create_access_token", "decode_token", "hash_password", "verify_password",
    "validate_password_strength", "get_password_strength_message",
    "generate_reset_token", "hash_reset_token", "verify_reset_token",
    "SecurityError"
]