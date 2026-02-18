"""
Model governance endpoints for CDIL.

Handles tenant-level model authorization and allowlisting.

Phase 3: Vendor API Key System + "Allowed Model" Governance
- Allow/block models for tenants
- Get model authorization status

Security:
- Admin role required for allow/block operations
- Per-tenant isolation (admin can only manage their own tenant's allowlist)
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from slowapi import Limiter
from slowapi.util import get_remote_address

from gateway.app.security.auth import Identity, require_role
from gateway.app.db.migrate import get_connection

router = APIRouter(prefix="/v1/governance", tags=["model-governance"])

# Rate limiter instance
limiter = Limiter(key_func=get_remote_address)


class ModelAuthorizationRequest(BaseModel):
    """Request to allow or block a model for tenant."""
    model_id: str = Field(..., description="Model ID to authorize/block")
    allow_reason: Optional[str] = Field(default=None, description="Reason for allow/block decision")


@router.post("/models/allow")
@limiter.limit("20/hour")  # Rate limit: 20 allowlist changes per hour
async def allow_model(
    request: Request,
    req_body: ModelAuthorizationRequest,
    identity: Identity = Depends(require_role("admin"))
) -> Dict[str, Any]:
    """
    Allow a model for the authenticated tenant.
    
    SECURITY: Requires JWT authentication with 'admin' role.
    Tenant ID derived from JWT (admin can only manage their own tenant).
    
    Args:
        request: FastAPI request (for rate limiting)
        req_body: Model authorization details
        identity: Authenticated identity (admin only)
        
    Returns:
        Authorization status
        
    Raises:
        HTTPException: 403 if insufficient permissions
        HTTPException: 404 if model not found
    """
    tenant_id = identity.tenant_id
    updated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    conn = get_connection()
    try:
        # Verify model exists and is active
        cursor = conn.execute("""
            SELECT model_id, model_name, model_version 
            FROM ai_models 
            WHERE model_id = ? AND status = 'active'
        """, (req_body.model_id,))
        
        model = cursor.fetchone()
        if not model:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "model_not_found",
                    "message": f"Model ID '{req_body.model_id}' not found or inactive"
                }
            )
        
        # Check if already in allowlist
        cursor = conn.execute("""
            SELECT status FROM tenant_allowed_models
            WHERE tenant_id = ? AND model_id = ?
        """, (tenant_id, req_body.model_id))
        
        existing = cursor.fetchone()
        
        if existing:
            # Update existing entry
            conn.execute("""
                UPDATE tenant_allowed_models
                SET status = 'allowed', 
                    allowed_by = ?,
                    allow_reason = ?,
                    updated_at_utc = ?
                WHERE tenant_id = ? AND model_id = ?
            """, (identity.sub, req_body.allow_reason, updated_at, tenant_id, req_body.model_id))
        else:
            # Insert new entry
            conn.execute("""
                INSERT INTO tenant_allowed_models (
                    tenant_id, model_id, status, allowed_by, allow_reason,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                tenant_id, req_body.model_id, 'allowed', identity.sub,
                req_body.allow_reason, updated_at, updated_at
            ))
        
        conn.commit()
        
        return {
            "tenant_id": tenant_id,
            "model_id": req_body.model_id,
            "model_name": model['model_name'],
            "model_version": model['model_version'],
            "status": "allowed",
            "allowed_by": identity.sub,
            "allow_reason": req_body.allow_reason,
            "updated_at": updated_at
        }
    finally:
        conn.close()


@router.post("/models/block")
@limiter.limit("20/hour")  # Rate limit: 20 allowlist changes per hour
async def block_model(
    request: Request,
    req_body: ModelAuthorizationRequest,
    identity: Identity = Depends(require_role("admin"))
) -> Dict[str, Any]:
    """
    Block a model for the authenticated tenant.
    
    SECURITY: Requires JWT authentication with 'admin' role.
    Tenant ID derived from JWT (admin can only manage their own tenant).
    Blocking a model prevents certificate issuance using that model.
    
    Args:
        request: FastAPI request (for rate limiting)
        req_body: Model authorization details
        identity: Authenticated identity (admin only)
        
    Returns:
        Authorization status
        
    Raises:
        HTTPException: 403 if insufficient permissions
        HTTPException: 404 if model not found
    """
    tenant_id = identity.tenant_id
    updated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    conn = get_connection()
    try:
        # Verify model exists
        cursor = conn.execute("""
            SELECT model_id, model_name, model_version 
            FROM ai_models 
            WHERE model_id = ?
        """, (req_body.model_id,))
        
        model = cursor.fetchone()
        if not model:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "model_not_found",
                    "message": f"Model ID '{req_body.model_id}' not found"
                }
            )
        
        # Check if in allowlist
        cursor = conn.execute("""
            SELECT status FROM tenant_allowed_models
            WHERE tenant_id = ? AND model_id = ?
        """, (tenant_id, req_body.model_id))
        
        existing = cursor.fetchone()
        
        if existing:
            # Update existing entry
            conn.execute("""
                UPDATE tenant_allowed_models
                SET status = 'blocked',
                    allowed_by = ?,
                    allow_reason = ?,
                    updated_at_utc = ?
                WHERE tenant_id = ? AND model_id = ?
            """, (identity.sub, req_body.allow_reason, updated_at, tenant_id, req_body.model_id))
        else:
            # Insert new entry as blocked
            conn.execute("""
                INSERT INTO tenant_allowed_models (
                    tenant_id, model_id, status, allowed_by, allow_reason,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                tenant_id, req_body.model_id, 'blocked', identity.sub,
                req_body.allow_reason, updated_at, updated_at
            ))
        
        conn.commit()
        
        return {
            "tenant_id": tenant_id,
            "model_id": req_body.model_id,
            "model_name": model['model_name'],
            "model_version": model['model_version'],
            "status": "blocked",
            "blocked_by": identity.sub,
            "block_reason": req_body.allow_reason,
            "updated_at": updated_at
        }
    finally:
        conn.close()


@router.get("/models/status")
@limiter.limit("100/minute")  # Rate limit: 100 status queries per minute
async def get_model_status(
    request: Request,
    model_id: str,
    identity: Identity = Depends(require_role("admin"))
) -> Dict[str, Any]:
    """
    Get authorization status of a model for the authenticated tenant.
    
    SECURITY: Requires JWT authentication with 'admin' role.
    Tenant ID derived from JWT (returns status only for requesting tenant).
    
    Args:
        request: FastAPI request (for rate limiting)
        model_id: Model ID to check
        identity: Authenticated identity (admin only)
        
    Returns:
        Model authorization status for tenant
        
    Raises:
        HTTPException: 403 if insufficient permissions
        HTTPException: 404 if model not found
    """
    tenant_id = identity.tenant_id
    
    conn = get_connection()
    try:
        # Get model info
        cursor = conn.execute("""
            SELECT model_id, model_name, model_version, status
            FROM ai_models
            WHERE model_id = ?
        """, (model_id,))
        
        model = cursor.fetchone()
        if not model:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "model_not_found",
                    "message": f"Model ID '{model_id}' not found"
                }
            )
        
        # Check tenant allowlist
        cursor = conn.execute("""
            SELECT status, allowed_by, allow_reason, updated_at_utc
            FROM tenant_allowed_models
            WHERE tenant_id = ? AND model_id = ?
        """, (tenant_id, model_id))
        
        allowlist_entry = cursor.fetchone()
        
        if allowlist_entry:
            authorization_status = allowlist_entry['status']
            allowed_by = allowlist_entry['allowed_by']
            reason = allowlist_entry['allow_reason']
            updated_at = allowlist_entry['updated_at_utc']
        else:
            # Not in allowlist = not explicitly allowed
            authorization_status = "not_configured"
            allowed_by = None
            reason = None
            updated_at = None
        
        return {
            "tenant_id": tenant_id,
            "model_id": model['model_id'],
            "model_name": model['model_name'],
            "model_version": model['model_version'],
            "model_status": model['status'],
            "authorization_status": authorization_status,
            "allowed_by": allowed_by,
            "reason": reason,
            "updated_at": updated_at,
            "can_issue_certificates": (
                authorization_status == "allowed" and 
                model['status'] == "active"
            )
        }
    finally:
        conn.close()
