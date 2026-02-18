"""
Clinical Documentation Integrity Layer (CDIL) - FastAPI Application

This is the main entry point for the CDIL Gateway API.
"""

from fastapi import FastAPI
from contextlib import asynccontextmanager

from gateway.app.routes import health, keys, transactions, ai, clinical
from gateway.app.db.migrate import ensure_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle management for the FastAPI app.
    
    On startup:
    - Ensure database schema exists
    - Bootstrap dev keys into database
    """
    # Initialize database
    ensure_schema()
    
    # Bootstrap dev keys
    from gateway.app.services.storage import bootstrap_dev_keys
    bootstrap_dev_keys()
    
    yield
    
    # Cleanup (if needed)


# Create FastAPI application
app = FastAPI(
    title="Clinical Documentation Integrity Layer",
    description="Cryptographically signed integrity certificates for AI-generated clinical documentation",
    version="0.1.0",
    lifespan=lifespan
)

# Register routers
app.include_router(health.router)
app.include_router(keys.router)
app.include_router(transactions.router)
app.include_router(ai.router)
app.include_router(clinical.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Clinical Documentation Integrity Layer",
        "version": "0.1.0",
        "status": "operational"
    }
