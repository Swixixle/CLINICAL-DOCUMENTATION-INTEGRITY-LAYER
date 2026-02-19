"""
Health check endpoint.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def health_check():
    """Basic health check endpoint."""
    return {"ok": True}


@router.get("/v1/health/status")
async def health_status():
    """Health status endpoint (v1 API)."""
    return {"status": "healthy", "service": "cdil-gateway"}
