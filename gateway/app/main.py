"""
Clinical Documentation Integrity Layer (CDIL) - FastAPI Application

This is the main entry point for the CDIL Gateway API.

Security Hardening:
- JWT-based authentication required for all protected endpoints
- Rate limiting to prevent abuse (can be disabled in test mode)
- Custom exception handling to prevent PHI leakage
- Database security validation on startup
"""

import os
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from gateway.app.routes import health, keys, transactions, ai, clinical, mock, analytics
from gateway.app.db.migrate import ensure_schema, check_db_security


# Initialize rate limiter with test mode bypass
def get_limiter():
    """
    Create rate limiter that can be disabled in test mode.
    
    Set ENV=TEST or DISABLE_RATE_LIMITS=1 to disable rate limiting.
    This allows tests to run cleanly in CI without rate limit failures.
    """
    disable_limits = (
        os.environ.get("ENV") == "TEST" or
        os.environ.get("DISABLE_RATE_LIMITS") == "1"
    )
    
    if disable_limits:
        # Return a limiter with effectively unlimited rate
        return Limiter(key_func=get_remote_address, default_limits=["1000000/minute"])
    else:
        return Limiter(key_func=get_remote_address)

limiter = get_limiter()


def sanitize_error_detail(detail: any) -> dict:
    """
    Sanitize error details to prevent PHI leakage.
    
    Removes any potential PHI from error messages before returning to client.
    
    Args:
        detail: Error detail from exception
        
    Returns:
        Sanitized error detail safe for client consumption
    """
    # If detail is a dict, return as-is (assumed pre-sanitized by our code)
    if isinstance(detail, dict):
        return detail
    
    # Otherwise, return generic message
    return {
        "error": "internal_error",
        "message": "An error occurred processing your request"
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle management for the FastAPI app.
    
    On startup:
    - Ensure database schema exists
    - Enable database security hardening (WAL mode, permissions)
    - Validate database security configuration
    - Bootstrap dev keys into database (dev only)
    """
    # Initialize database
    ensure_schema()
    
    # Check database security
    security_status = check_db_security()
    
    # Warn if security is not optimal (but don't fail startup)
    if not security_status.get("wal_enabled"):
        print("WARNING: Database WAL mode not enabled")
    
    if not security_status.get("permissions_secure"):
        print("WARNING: Database file permissions may not be secure")
    
    # Bootstrap dev keys (for development/testing only)
    from gateway.app.services.storage import bootstrap_dev_keys
    bootstrap_dev_keys()
    
    yield
    
    # Cleanup (if needed)


# Create FastAPI application
app = FastAPI(
    title="Clinical Documentation Integrity Layer (CDIL)",
    description="Cryptographically signed integrity certificates for AI-generated clinical documentation",
    version="0.1.0",
    lifespan=lifespan,
    # Disable debug mode in production
    debug=False
)

# Register rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Custom exception handlers to prevent PHI leakage
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions without leaking PHI."""
    return JSONResponse(
        status_code=exc.status_code,
        content=sanitize_error_detail(exc.detail)
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle validation errors without leaking request body.
    
    Pydantic validation errors can include parts of the request body,
    which might contain PHI. We sanitize this to only show field names.
    """
    # Extract field names only, not values
    errors = []
    for error in exc.errors():
        field_path = " -> ".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field_path,
            "type": error["type"],
            "message": error["msg"]
        })
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "details": errors
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Catch-all exception handler to prevent stack traces with PHI.
    
    In production, this prevents any unhandled exceptions from leaking
    request data or internal state that might contain PHI.
    """
    # Log the full exception server-side (with appropriate PHI controls)
    # In production, use structured logging with PHI redaction
    print(f"Unhandled exception: {type(exc).__name__}")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred"
        }
    )


# Register routers
app.include_router(health.router)
app.include_router(keys.router)
app.include_router(transactions.router)
app.include_router(ai.router)
app.include_router(clinical.router)
app.include_router(mock.router)
app.include_router(analytics.router)
# Phase 2-4 routes (vendors, governance, gatekeeper) moved to separate PRs


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Clinical Documentation Integrity Layer (CDIL)",
        "version": "0.1.0",
        "status": "operational"
    }
