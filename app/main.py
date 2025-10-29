# app/main.py - Fixed CORS configuration with detailed logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import traceback
import time

from app.core.config import settings
from app.core.db import get_engine
from app.models.base import Base
from app.api.routers import auth, schools, chat, students, classes, academic
from app.api.routers import fees, invoices, payments
from app.api.routers import guardians
from app.api.routers import notifications
from app.api.routers import enrollments


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    logger.info("Starting School Assistant API...")
    logger.info(f"Environment: {settings.ENV}")
    logger.info(f"Database URL: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'local'}")
    
    # Get the database engine
    engine = get_engine()
    
    # Create tables if they don't exist (for development)
    if settings.ENV == "dev":
        logger.info("Creating database tables...")
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
    
    yield
    
    logger.info("Shutting down School Assistant API...")

# Create FastAPI app
app = FastAPI(
    title="School Assistant API",
    description="AI-powered school management system with chat interface",
    version="1.0.0",
    docs_url="/docs" if settings.ENV == "dev" else None,
    redoc_url="/redoc" if settings.ENV == "dev" else None,
    lifespan=lifespan
)

# Log CORS origins for debugging
logger.info(f"CORS Origins configured: {settings.CORS_ORIGINS}")

# Request logging middleware - BEFORE CORS
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests with details"""
    start_time = time.time()
    
    # Log request details
    logger.info(f"⬇️  Incoming {request.method} {request.url.path}")
    logger.info(f"   Origin: {request.headers.get('origin', 'No Origin header')}")
    logger.info(f"   Host: {request.headers.get('host', 'No Host header')}")
    logger.info(f"   User-Agent: {request.headers.get('user-agent', 'No User-Agent')[:50]}...")
    logger.info(f"   Content-Type: {request.headers.get('content-type', 'No Content-Type')}")
    
    # Log all headers for OPTIONS requests
    if request.method == "OPTIONS":
        logger.info("   📋 All headers:")
        for key, value in request.headers.items():
            logger.info(f"      {key}: {value}")
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Log response details
        logger.info(f"⬆️  Response {response.status_code} for {request.method} {request.url.path}")
        logger.info(f"   Process time: {process_time:.3f}s")
        
        # Log response headers for OPTIONS
        if request.method == "OPTIONS":
            logger.info("   📋 Response headers:")
            for key, value in response.headers.items():
                logger.info(f"      {key}: {value}")
        
        return response
    except Exception as e:
        logger.error(f"❌ Error processing {request.method} {request.url.path}: {str(e)}")
        logger.error(traceback.format_exc())
        raise

# CORS middleware - MUST be added after logging middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "Accept",
        "Origin",
        "User-Agent",
        "DNT",
        "Cache-Control",
        "X-Mx-ReqToken",
        "Keep-Alive",
        "X-Requested-With",
        "If-Modified-Since",
        "X-School-ID",
    ],
    expose_headers=["*"],
    max_age=3600,
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions"""
    logger.error(f"❌ Unhandled exception on {request.method} {request.url.path}")
    logger.error(f"   Exception: {str(exc)}")
    
    if settings.ENV == "dev":
        logger.error(f"   Traceback:\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "traceback": traceback.format_exc()
            }
        )
    else:
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.ENV,
        "version": "1.0.0",
        "cors_origins": settings.CORS_ORIGINS
    }

# Debug endpoint to test CORS
@app.options("/api/test-cors")
@app.get("/api/test-cors")
async def test_cors(request: Request):
    """Test endpoint to verify CORS is working"""
    return {
        "message": "CORS is working!",
        "origin": request.headers.get("origin"),
        "method": request.method
    }

# Include routers
logger.info("Registering API routers...")
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(schools.router, prefix="/api/schools", tags=["Schools"])  
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(students.router, prefix="/api/students", tags=["Students"])
app.include_router(classes.router, prefix="/api/classes", tags=["Classes"])
app.include_router(academic.router, prefix="/api/academic", tags=["Academic Management"])
app.include_router(fees.router, prefix="/api/fees", tags=["Fees"])
app.include_router(invoices.router, prefix="/api/invoices", tags=["Invoices"])
app.include_router(payments.router, prefix="/api/payments", tags=["Payments"])
app.include_router(guardians.router, prefix="/api/guardians", tags=["Guardians"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(enrollments.router, prefix="/api/enrollments", tags=["Enrollments"])
logger.info("All routers registered successfully")

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "School Assistant API",
        "version": "1.0.0",
        "docs_url": "/docs" if settings.ENV == "dev" else "Documentation disabled in production",
        "cors_origins": settings.CORS_ORIGINS
    }