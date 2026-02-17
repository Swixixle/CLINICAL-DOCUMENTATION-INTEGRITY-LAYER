"""
Health check endpoint.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def health_check():
    """Basic health check endpoint."""
    return {"ok": True}
