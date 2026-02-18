"""
Vendor registry endpoints for CDIL.

Handles AI vendor and model registration, key management, and governance.

Phase 2: Multi-Model Governance
- Register AI vendors
- Register AI models
- Rotate vendor model keys
- List models

Security:
- Admin role required for all operations
- Per-tenant isolation for model allowlists
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from slowapi import Limiter
from slowapi.util import get_remote_address

from gateway.app.security.auth import Identity, require_role
from gateway.app.services.uuid7 import generate_uuid7
from gateway.app.db.migrate import get_connection

router = APIRouter(prefix="/v1", tags=["vendor-registry"])

# Rate limiter instance
limiter = Limiter(key_func=get_remote_address)


class VendorRegistrationRequest(BaseModel):
    """Request to register a new AI vendor."""
    vendor_name: str = Field(..., description="Vendor name (e.g., 'OpenAI', 'Anthropic')")


class ModelRegistrationRequest(BaseModel):
    """Request to register a new AI model."""
    vendor_id: str = Field(..., description="Vendor ID")
    model_name: str = Field(..., description="Model name (e.g., 'GPT-4-Turbo')")
    model_version: str = Field(..., description="Model version (e.g., '2024-11')")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")
    public_jwk: Optional[Dict[str, str]] = Field(default=None, description="Vendor public key (JWK format)")


class KeyRotationRequest(BaseModel):
    """Request to rotate a model's key."""
    model_id: str = Field(..., description="Model ID")
    new_public_jwk: Dict[str, str] = Field(..., description="New public key (JWK format)")


@router.post("/vendors/register")
@limiter.limit("10/hour")  # Rate limit: 10 vendor registrations per hour
async def register_vendor(
    request: Request,
    req_body: VendorRegistrationRequest,
    identity: Identity = Depends(require_role("admin"))
) -> Dict[str, Any]:
    """
    Register a new AI vendor.
    
    SECURITY: Requires JWT authentication with 'admin' role.
    
    Args:
        request: FastAPI request (for rate limiting)
        req_body: Vendor registration details
        identity: Authenticated identity (admin only)
        
    Returns:
        Vendor registration response with vendor_id
        
    Raises:
        HTTPException: 403 if insufficient permissions
        HTTPException: 400 if vendor already exists
    """
    vendor_id = generate_uuid7()
    created_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    conn = get_connection()
    try:
        # Check if vendor name already exists
        cursor = conn.execute("""
            SELECT vendor_id FROM ai_vendors WHERE vendor_name = ?
        """, (req_body.vendor_name,))
        
        if cursor.fetchone():
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "vendor_already_exists",
                    "message": f"Vendor '{req_body.vendor_name}' is already registered"
                }
            )
        
        # Insert vendor
        conn.execute("""
            INSERT INTO ai_vendors (
                vendor_id, vendor_name, status, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?)
        """, (vendor_id, req_body.vendor_name, "active", created_at, created_at))
        conn.commit()
        
        return {
            "vendor_id": vendor_id,
            "vendor_name": req_body.vendor_name,
            "status": "active",
            "created_at": created_at
        }
    finally:
        conn.close()


@router.post("/vendors/register-model")
@limiter.limit("20/hour")  # Rate limit: 20 model registrations per hour
async def register_model(
    request: Request,
    req_body: ModelRegistrationRequest,
    identity: Identity = Depends(require_role("admin"))
) -> Dict[str, Any]:
    """
    Register a new AI model with optional vendor public key.
    
    SECURITY: Requires JWT authentication with 'admin' role.
    
    Args:
        request: FastAPI request (for rate limiting)
        req_body: Model registration details
        identity: Authenticated identity (admin only)
        
    Returns:
        Model registration response with model_id
        
    Raises:
        HTTPException: 403 if insufficient permissions
        HTTPException: 400 if vendor not found or model already exists
    """
    import json
    
    model_id = generate_uuid7()
    created_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    conn = get_connection()
    try:
        # Verify vendor exists
        cursor = conn.execute("""
            SELECT vendor_id FROM ai_vendors WHERE vendor_id = ? AND status = 'active'
        """, (req_body.vendor_id,))
        
        if not cursor.fetchone():
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "vendor_not_found",
                    "message": f"Vendor ID '{req_body.vendor_id}' not found or inactive"
                }
            )
        
        # Check if model already exists
        cursor = conn.execute("""
            SELECT model_id FROM ai_models 
            WHERE vendor_id = ? AND model_name = ? AND model_version = ?
        """, (req_body.vendor_id, req_body.model_name, req_body.model_version))
        
        if cursor.fetchone():
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "model_already_exists",
                    "message": f"Model '{req_body.model_name}' version '{req_body.model_version}' already registered"
                }
            )
        
        # Serialize metadata
        metadata_json = json.dumps(req_body.metadata) if req_body.metadata else None
        
        # Insert model
        conn.execute("""
            INSERT INTO ai_models (
                model_id, vendor_id, model_name, model_version, 
                status, metadata_json, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            model_id, req_body.vendor_id, req_body.model_name, 
            req_body.model_version, "active", metadata_json, created_at, created_at
        ))
        
        # Register vendor public key if provided
        key_id = None
        if req_body.public_jwk:
            key_id = generate_uuid7()
            jwk_json = json.dumps(req_body.public_jwk)
            
            conn.execute("""
                INSERT INTO vendor_model_keys (
                    key_id, model_id, public_jwk_json, status, created_at_utc
                ) VALUES (?, ?, ?, ?, ?)
            """, (key_id, model_id, jwk_json, "active", created_at))
        
        conn.commit()
        
        return {
            "model_id": model_id,
            "vendor_id": req_body.vendor_id,
            "model_name": req_body.model_name,
            "model_version": req_body.model_version,
            "status": "active",
            "key_id": key_id,
            "created_at": created_at
        }
    finally:
        conn.close()


@router.post("/vendors/rotate-model-key")
@limiter.limit("10/hour")  # Rate limit: 10 key rotations per hour
async def rotate_model_key(
    request: Request,
    req_body: KeyRotationRequest,
    identity: Identity = Depends(require_role("admin"))
) -> Dict[str, Any]:
    """
    Rotate a model's public key (mark old key as rotated, add new key).
    
    SECURITY: Requires JWT authentication with 'admin' role.
    Old keys are preserved for verifying historical certificates.
    
    Args:
        request: FastAPI request (for rate limiting)
        req_body: Key rotation details
        identity: Authenticated identity (admin only)
        
    Returns:
        Key rotation response with new key_id
        
    Raises:
        HTTPException: 403 if insufficient permissions
        HTTPException: 404 if model not found
    """
    import json
    
    rotated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    conn = get_connection()
    try:
        # Verify model exists
        cursor = conn.execute("""
            SELECT model_id FROM ai_models WHERE model_id = ?
        """, (req_body.model_id,))
        
        if not cursor.fetchone():
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "model_not_found",
                    "message": f"Model ID '{req_body.model_id}' not found"
                }
            )
        
        # Mark old key(s) as rotated
        conn.execute("""
            UPDATE vendor_model_keys
            SET status = 'rotated', rotated_at_utc = ?
            WHERE model_id = ? AND status = 'active'
        """, (rotated_at, req_body.model_id))
        
        # Insert new key
        new_key_id = generate_uuid7()
        jwk_json = json.dumps(req_body.new_public_jwk)
        
        conn.execute("""
            INSERT INTO vendor_model_keys (
                key_id, model_id, public_jwk_json, status, created_at_utc
            ) VALUES (?, ?, ?, ?, ?)
        """, (new_key_id, req_body.model_id, jwk_json, "active", rotated_at))
        
        conn.commit()
        
        return {
            "model_id": req_body.model_id,
            "new_key_id": new_key_id,
            "rotated_at": rotated_at,
            "message": "Key rotated successfully. Old keys preserved for historical verification."
        }
    finally:
        conn.close()


@router.get("/vendors/models")
@limiter.limit("100/minute")  # Rate limit: 100 model list requests per minute
async def list_models(
    request: Request,
    identity: Identity = Depends(require_role("admin")),
    vendor_id: Optional[str] = None,
    status: Optional[str] = None
) -> Dict[str, Any]:
    """
    List all registered AI models (admin only).
    
    SECURITY: Requires JWT authentication with 'admin' role.
    
    Args:
        request: FastAPI request (for rate limiting)
        identity: Authenticated identity (admin only)
        vendor_id: Optional filter by vendor
        status: Optional filter by status ('active', 'deprecated', 'blocked')
        
    Returns:
        List of models with metadata
        
    Raises:
        HTTPException: 403 if insufficient permissions
    """
    import json
    
    conn = get_connection()
    try:
        # Build query
        query = """
            SELECT m.model_id, m.vendor_id, v.vendor_name, m.model_name, 
                   m.model_version, m.status, m.metadata_json, m.created_at_utc
            FROM ai_models m
            JOIN ai_vendors v ON m.vendor_id = v.vendor_id
            WHERE 1=1
        """
        params = []
        
        if vendor_id:
            query += " AND m.vendor_id = ?"
            params.append(vendor_id)
        
        if status:
            query += " AND m.status = ?"
            params.append(status)
        
        query += " ORDER BY m.created_at_utc DESC"
        
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        
        models = []
        for row in rows:
            metadata = json.loads(row['metadata_json']) if row['metadata_json'] else {}
            
            models.append({
                "model_id": row['model_id'],
                "vendor_id": row['vendor_id'],
                "vendor_name": row['vendor_name'],
                "model_name": row['model_name'],
                "model_version": row['model_version'],
                "status": row['status'],
                "metadata": metadata,
                "created_at": row['created_at_utc']
            })
        
        return {
            "total_count": len(models),
            "models": models
        }
    finally:
        conn.close()


@router.get("/allowed-models")
@limiter.limit("100/minute")  # Rate limit: 100 allowlist queries per minute
async def get_allowed_models(
    request: Request,
    identity: Identity = Depends(require_role("admin"))
) -> Dict[str, Any]:
    """
    Get allowed models for the authenticated tenant.
    
    SECURITY: Requires JWT authentication.
    Returns only models allowed for the requesting tenant.
    Tenant ID derived from JWT (no cross-tenant access).
    
    Args:
        request: FastAPI request (for rate limiting)
        identity: Authenticated identity
        
    Returns:
        List of allowed models for tenant
        
    Raises:
        HTTPException: 401 if not authenticated
    """
    import json
    
    tenant_id = identity.tenant_id
    
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT m.model_id, m.vendor_id, v.vendor_name, m.model_name, 
                   m.model_version, m.status, tam.status as allowlist_status,
                   tam.allow_reason, tam.updated_at_utc
            FROM tenant_allowed_models tam
            JOIN ai_models m ON tam.model_id = m.model_id
            JOIN ai_vendors v ON m.vendor_id = v.vendor_id
            WHERE tam.tenant_id = ? AND tam.status = 'allowed'
            ORDER BY tam.updated_at_utc DESC
        """, (tenant_id,))
        
        rows = cursor.fetchall()
        
        models = []
        for row in rows:
            models.append({
                "model_id": row['model_id'],
                "vendor_id": row['vendor_id'],
                "vendor_name": row['vendor_name'],
                "model_name": row['model_name'],
                "model_version": row['model_version'],
                "model_status": row['status'],
                "allow_reason": row['allow_reason'],
                "approved_at": row['updated_at_utc']
            })
        
        return {
            "tenant_id": tenant_id,
            "total_count": len(models),
            "allowed_models": models
        }
    finally:
        conn.close()
