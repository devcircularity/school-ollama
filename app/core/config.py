# app/core/config.py - Centralized settings management using Pydantic
from pydantic import Field, validator, EmailStr
from pydantic_settings import BaseSettings
from typing import List, Optional, Union
import os
import secrets
from pathlib import Path

class Settings(BaseSettings):
    """Application settings with validation and type safety"""
    
    # Application Environment
    ENV: str = Field(default="dev", description="Environment: dev, staging, prod")
    DEBUG: bool = Field(default=False, description="Debug mode")
    API_HOST: str = Field(default="0.0.0.0", description="API host")
    API_PORT: int = Field(default=8000, ge=1, le=65535, description="API port")
    API_TITLE: str = Field(default="School Assistant API", description="API title")
    API_VERSION: str = Field(default="1.0.0", description="API version")
    
    # Database Configuration
    DATABASE_URL: str = Field(..., description="Database connection URL")
    DATABASE_ECHO: bool = Field(default=False, description="Echo SQL queries")
    DATABASE_POOL_SIZE: int = Field(default=5, ge=1, le=100, description="Connection pool size")
    DATABASE_MAX_OVERFLOW: int = Field(default=10, ge=0, le=100, description="Max overflow connections")
    DATABASE_POOL_TIMEOUT: int = Field(default=30, ge=1, le=300, description="Pool timeout in seconds")
    DATABASE_POOL_RECYCLE: int = Field(default=3600, ge=300, description="Pool recycle time in seconds")
    
    # JWT Configuration
    JWT_SECRET: str = Field(..., min_length=32, description="JWT signing secret")
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=1, le=10080, description="Access token expiry")
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1, le=365, description="Refresh token expiry")
    JWT_ISSUER: str = Field(default="school-assistant", description="JWT issuer")
    JWT_AUDIENCE: str = Field(default="school-assistant-users", description="JWT audience")
    
    # CORS Configuration
    CORS_ORIGINS: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",  # Vite dev server
            "http://127.0.0.1:5173"
        ],
        description="CORS allowed origins"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, description="Allow CORS credentials")
    CORS_ALLOW_METHODS: List[str] = Field(default=["*"], description="Allowed HTTP methods")
    CORS_ALLOW_HEADERS: List[str] = Field(default=["*"], description="Allowed headers")
    
    # Rasa Configuration
    RASA_URL: str = Field(default="http://localhost:5005", description="Rasa server URL")
    RASA_TOKEN: Optional[str] = Field(default=None, description="Rasa authentication token")
    RASA_TIMEOUT_SECONDS: int = Field(default=30, ge=1, le=300, description="Rasa request timeout")
    RASA_MAX_RETRIES: int = Field(default=3, ge=0, le=10, description="Max retry attempts for Rasa")
    RASA_RETRY_DELAY: float = Field(default=1.0, ge=0.1, le=10.0, description="Retry delay in seconds")
    
    # WhatsApp Bridge Configuration
    WA_BRIDGE_URL: str = Field(default="http://localhost:3001", description="WhatsApp bridge URL")
    WA_BRIDGE_API_KEY: str = Field(default="dev-secret", description="WhatsApp bridge API key")
    WA_BRIDGE_TIMEOUT: int = Field(default=30, ge=1, le=300, description="WhatsApp bridge timeout")
    
    # File Upload & OCR Configuration
    OCR_ENDPOINT: str = Field(default="https://ocr.olaji.co/ocr", description="OCR service endpoint")
    OCR_TIMEOUT_SECONDS: int = Field(default=60, ge=1, le=300, description="OCR timeout")
    MAX_FILE_SIZE_MB: int = Field(default=10, ge=1, le=100, description="Max file size in MB")
    MAX_FILES_PER_MESSAGE: int = Field(default=5, ge=1, le=20, description="Max files per chat message")
    ALLOWED_FILE_TYPES: List[str] = Field(
        default=[".pdf", ".jpg", ".jpeg", ".png", ".txt", ".docx"],
        description="Allowed file extensions"
    )
    
    # Cloudinary Configuration
    CLOUDINARY_CLOUD_NAME: str = Field(..., description="Cloudinary cloud name")
    CLOUDINARY_API_KEY: str = Field(..., description="Cloudinary API key")
    CLOUDINARY_API_SECRET: str = Field(..., description="Cloudinary API secret")
    CLOUDINARY_UPLOAD_PRESET: str = Field(default="school_assistant", description="Cloudinary upload preset")
    CLOUDINARY_FOLDER: str = Field(default="school-assistant", description="Cloudinary folder")
    
    # Email Configuration (SMTP)
    SMTP_HOST: Optional[str] = Field(default=None, description="SMTP server host")
    SMTP_PORT: int = Field(default=587, ge=1, le=65535, description="SMTP server port")
    SMTP_USER: Optional[str] = Field(default=None, description="SMTP username")
    SMTP_PASSWORD: Optional[str] = Field(default=None, description="SMTP password")
    SMTP_FROM_EMAIL: Optional[EmailStr] = Field(default=None, description="From email address")
    SMTP_FROM_NAME: str = Field(default="School Assistant", description="From name")
    SMTP_USE_TLS: bool = Field(default=True, description="Use TLS for SMTP")
    SMTP_USE_SSL: bool = Field(default=False, description="Use SSL for SMTP")
    
    # Password Reset Configuration
    RESET_TOKEN_EXPIRE_HOURS: int = Field(default=24, ge=1, le=168, description="Reset token expiry hours")
    RESET_TOKEN_LENGTH: int = Field(default=32, ge=16, le=64, description="Reset token length")
    MAX_RESET_ATTEMPTS: int = Field(default=3, ge=1, le=10, description="Max reset attempts per user")
    
    # Rate Limiting Configuration
    CHAT_RATE_LIMIT_PER_MINUTE: int = Field(default=30, ge=1, le=1000, description="Chat rate limit")
    AUTH_RATE_LIMIT_PER_MINUTE: int = Field(default=5, ge=1, le=100, description="Auth rate limit")
    API_RATE_LIMIT_PER_MINUTE: int = Field(default=100, ge=1, le=10000, description="General API rate limit")
    
    # Security Configuration
    BCRYPT_ROUNDS: int = Field(default=12, ge=10, le=15, description="BCrypt rounds")
    SESSION_COOKIE_SECURE: bool = Field(default=True, description="Secure session cookies")
    SESSION_COOKIE_HTTPONLY: bool = Field(default=True, description="HttpOnly session cookies")
    SESSION_COOKIE_SAMESITE: str = Field(default="lax", description="SameSite cookie attribute")
    
    # Logging Configuration
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FORMAT: str = Field(default="detailed", description="Log format: simple, detailed, json")
    LOG_FILE_PATH: Optional[str] = Field(default=None, description="Log file path")
    LOG_MAX_SIZE: int = Field(default=10485760, description="Max log file size in bytes (10MB)")
    LOG_BACKUP_COUNT: int = Field(default=5, description="Number of log backup files")
    
    # Performance & Monitoring
    ENABLE_METRICS: bool = Field(default=False, description="Enable metrics collection")
    METRICS_PORT: int = Field(default=8001, ge=1, le=65535, description="Metrics server port")
    HEALTH_CHECK_INTERVAL: int = Field(default=30, ge=1, le=300, description="Health check interval")
    
    # Cache Configuration (Redis/Memory)
    CACHE_TYPE: str = Field(default="memory", description="Cache type: memory, redis")
    REDIS_URL: Optional[str] = Field(default=None, description="Redis connection URL")
    CACHE_DEFAULT_TIMEOUT: int = Field(default=300, ge=1, description="Default cache timeout")
    
    # Feature Flags
    ENABLE_REGISTRATION: bool = Field(default=True, description="Allow new user registration")
    ENABLE_PASSWORD_RESET: bool = Field(default=True, description="Enable password reset")
    ENABLE_FILE_UPLOAD: bool = Field(default=True, description="Enable file uploads")
    ENABLE_CHAT_RATING: bool = Field(default=True, description="Enable chat message rating")
    MAINTENANCE_MODE: bool = Field(default=False, description="Maintenance mode")
    
    # Development Settings
    DEV_AUTO_RELOAD: bool = Field(default=False, description="Auto-reload in development")
    DEV_SHOW_DOCS: bool = Field(default=True, description="Show API docs in development")
    DEV_LOG_SQL: bool = Field(default=False, description="Log SQL queries in development")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Ignore extra environment variables
    
    @validator("ENV")
    def validate_environment(cls, v):
        allowed_envs = ["dev", "development", "staging", "prod", "production"]
        if v.lower() not in allowed_envs:
            raise ValueError(f"ENV must be one of: {allowed_envs}")
        return v.lower()
    
    @validator("JWT_SECRET")
    def validate_jwt_secret(cls, v, values):
        if values.get("ENV") in ["prod", "production"] and v == "change_me_now":
            raise ValueError("JWT_SECRET must be changed in production")
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        return v
    
    @validator("DATABASE_URL")
    def validate_database_url(cls, v):
        # Accept postgresql, postgresql+psycopg2 (legacy), postgresql+psycopg (psycopg3), sqlite
        allowed_prefixes = (
            "postgresql://",
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
            "sqlite:///",
        )
        if not v.startswith(allowed_prefixes):
            raise ValueError("DATABASE_URL must be a valid database connection string (postgresql, postgresql+psycopg, postgresql+psycopg2, or sqlite)")
        return v
    
    @validator("LOG_LEVEL")
    def validate_log_level(cls, v):
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed_levels:
            raise ValueError(f"LOG_LEVEL must be one of: {allowed_levels}")
        return v.upper()
    
    @validator("CORS_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            # Handle comma-separated string
            if v.strip():
                return [origin.strip() for origin in v.split(",") if origin.strip()]
            else:
                # Return default if empty string
                return [
                    "http://localhost:3000",
                    "http://127.0.0.1:3000", 
                    "http://localhost:5173",
                    "http://127.0.0.1:5173"
                ]
        return v
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.ENV in ["dev", "development"]
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.ENV in ["prod", "production"]
    
    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL"""
        return self.DATABASE_URL.replace("+asyncpg", "").replace("+psycopg2", "")
    
    @property
    def max_file_size_bytes(self) -> int:
        """Get max file size in bytes"""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024
    
    def get_cors_config(self) -> dict:
        """Get CORS configuration for FastAPI"""
        return {
            "allow_origins": self.CORS_ORIGINS,
            "allow_credentials": self.CORS_ALLOW_CREDENTIALS,
            "allow_methods": self.CORS_ALLOW_METHODS,
            "allow_headers": self.CORS_ALLOW_HEADERS,
        }
    
    def generate_secret_key(self) -> str:
        """Generate a secure secret key"""
        return secrets.token_urlsafe(32)

# Create settings instance with validation
try:
    settings = Settings()
except Exception as e:
    print(f"Configuration error: {e}")
    print("Please check your .env file and environment variables")
    raise

# Validate critical settings on startup
def validate_critical_settings():
    """Validate critical settings that must be present"""
    critical_errors = []
    
    # Check database configuration
    if not settings.DATABASE_URL:
        critical_errors.append("DATABASE_URL is required")
    
    # Check JWT configuration
    if not settings.JWT_SECRET or settings.JWT_SECRET == "change_me_now":
        if settings.is_production:
            critical_errors.append("JWT_SECRET must be set to a secure value in production")
        elif not settings.JWT_SECRET:
            critical_errors.append("JWT_SECRET is required")
    
    # Check Cloudinary configuration
    if not all([settings.CLOUDINARY_CLOUD_NAME, settings.CLOUDINARY_API_KEY, settings.CLOUDINARY_API_SECRET]):
        critical_errors.append("Cloudinary configuration (CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET) is required")
    
    # Check SMTP configuration if password reset is enabled
    if settings.ENABLE_PASSWORD_RESET and not settings.SMTP_HOST:
        print("WARNING: Password reset is enabled but SMTP is not configured. Password reset emails will not be sent.")
    
    if critical_errors:
        error_msg = "Critical configuration errors:\n" + "\n".join(f"  - {error}" for error in critical_errors)
        raise ValueError(error_msg)

# Validate on import
validate_critical_settings()

# Export settings
__all__ = ["settings", "Settings"]