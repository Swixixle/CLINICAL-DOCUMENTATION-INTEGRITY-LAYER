"""
EHR Gatekeeper endpoints for CDIL.

Provides "gatekeeper mode" for EHR vendors to enforce that only
verified notes are committed to the medical record.

Phase 4: EHR Gatekeeper Mode
- Verify certificate and issue commit token
- Commit token is short-lived JWT binding certificate to EHR commit

Security:
- ehr_gateway role required
- Commit tokens expire in 5 minutes
- One-time use via nonce tracking
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from slowapi import Limiter
from slowapi.util import get_remote_address
import jwt
import json

from gateway.app.security.auth import Identity, require_role
from gateway.app.db.migrate import get_connection
from gateway.app.services.uuid7 import generate_uuid7

router = APIRouter(prefix="/v1/gatekeeper", tags=["ehr-gatekeeper"])

# Rate limiter instance
limiter = Limiter(key_func=get_remote_address)

# Secret for signing commit tokens (in production, use environment variable)
# This is separate from tenant signing keys
COMMIT_TOKEN_SECRET = "gatekeeper-commit-token-secret-change-in-production"


class GatekeeperVerifyRequest(BaseModel):
    """Request to verify a certificate and authorize EHR commit."""
    certificate_id: str = Field(..., description="Certificate ID to verify")
    ehr_commit_id: Optional[str] = Field(default=None, description="Opaque EHR commit reference (no PHI)")


@router.post("/verify-and-authorize")
@limiter.limit("100/minute")  # Rate limit: 100 gatekeeper verifications per minute
async def verify_and_authorize(
    request: Request,
    req_body: GatekeeperVerifyRequest,
    identity: Identity = Depends(require_role("ehr_gateway"))
) -> Dict[str, Any]:
    """
    Verify certificate and issue commit authorization token.
    
    SECURITY: Requires JWT authentication with 'ehr_gateway' role.
    This is the gatekeeper that ensures only verified notes reach the EHR.
    
    Workflow:
    1. Verify certificate exists and passes integrity checks
    2. Enforce tenant boundary (certificate must belong to requesting tenant)
    3. Generate short-lived commit token (5 minute expiration)
    4. Commit token binds: tenant_id, certificate_id, ehr_commit_id, timestamp
    
    EHR can use commit token as proof that note was verified before commit.
    
    Args:
        request: FastAPI request (for rate limiting)
        req_body: Verification request details
        identity: Authenticated identity (ehr_gateway role required)
        
    Returns:
        Verification result with commit token if authorized
        
    Raises:
        HTTPException: 403 if insufficient permissions
        HTTPException: 404 if certificate not found or cross-tenant access
        HTTPException: 400 if verification fails
    """
    tenant_id = identity.tenant_id
    certificate_id = req_body.certificate_id
    
    conn = get_connection()
    try:
        # Load certificate
        cursor = conn.execute("""
            SELECT certificate_json, tenant_id
            FROM certificates
            WHERE certificate_id = ?
        """, (certificate_id,))
        
        row = cursor.fetchone()
        
        # Return 404 if not found (don't reveal existence)
        if not row:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "certificate_not_found",
                    "message": "Certificate not found"
                }
            )
        
        # Enforce tenant boundary (cross-tenant returns 404)
        if row['tenant_id'] != tenant_id:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "certificate_not_found",
                    "message": "Certificate not found"
                }
            )
        
        certificate = json.loads(row['certificate_json'])
    finally:
        conn.close()
    
    # Perform verification checks (simplified from full verification endpoint)
    verification_failures = []
    
    # Check 1: Timing integrity (if ehr_referenced_at is set)
    finalized_at_str = certificate.get("finalized_at")
    ehr_referenced_at_str = certificate.get("ehr_referenced_at")
    
    if finalized_at_str and ehr_referenced_at_str:
        try:
            finalized_at = datetime.fromisoformat(finalized_at_str.replace('Z', '+00:00'))
            ehr_referenced_at = datetime.fromisoformat(ehr_referenced_at_str.replace('Z', '+00:00'))
            
            if finalized_at > ehr_referenced_at:
                verification_failures.append({
                    "check": "timing_integrity",
                    "error": "finalized_after_ehr_reference",
                    "message": "Certificate may have been backdated"
                })
        except Exception:
            verification_failures.append({
                "check": "timing_integrity",
                "error": "timestamp_parse_error"
            })
    
    # Check 2: Signature exists
    if not certificate.get("signature"):
        verification_failures.append({
            "check": "signature",
            "error": "missing_signature"
        })
    
    # Check 3: Integrity chain exists
    if not certificate.get("integrity_chain"):
        verification_failures.append({
            "check": "integrity_chain",
            "error": "missing_chain"
        })
    
    # Determine if authorized
    authorized = len(verification_failures) == 0
    
    commit_token = None
    if authorized:
        # Generate commit token
        commit_token = generate_commit_token(
            tenant_id=tenant_id,
            certificate_id=certificate_id,
            ehr_commit_id=req_body.ehr_commit_id
        )
    
    return {
        "certificate_id": certificate_id,
        "tenant_id": tenant_id,
        "authorized": authorized,
        "verification_passed": authorized,
        "verification_failures": verification_failures,
        "commit_token": commit_token,
        "ehr_commit_id": req_body.ehr_commit_id,
        "verified_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    }


def generate_commit_token(
    tenant_id: str,
    certificate_id: str,
    ehr_commit_id: Optional[str] = None
) -> str:
    """
    Generate a short-lived commit authorization token.
    
    Token is a JWT containing:
    - token_type: "cdil_commit_authorization"
    - tenant_id: Tenant identifier
    - certificate_id: Certificate that was verified
    - ehr_commit_id: Optional EHR commit reference
    - nonce: One-time use nonce
    - iat: Issued at timestamp
    - exp: Expiration timestamp (5 minutes)
    
    Args:
        tenant_id: Tenant identifier
        certificate_id: Certificate ID
        ehr_commit_id: Optional EHR commit reference
        
    Returns:
        JWT commit token (base64-encoded)
    """
    now = datetime.now(timezone.utc)
    expiration = now + timedelta(minutes=5)
    
    payload = {
        "token_type": "cdil_commit_authorization",
        "tenant_id": tenant_id,
        "certificate_id": certificate_id,
        "ehr_commit_id": ehr_commit_id,
        "nonce": generate_uuid7(),
        "iat": int(now.timestamp()),
        "exp": int(expiration.timestamp())
    }
    
    # Sign token with commit token secret
    token = jwt.encode(payload, COMMIT_TOKEN_SECRET, algorithm="HS256")
    
    return token


@router.post("/verify-commit-token")
@limiter.limit("200/minute")  # Rate limit: 200 token verifications per minute
async def verify_commit_token(
    request: Request,
    commit_token: str,
    identity: Identity = Depends(require_role("ehr_gateway"))
) -> Dict[str, Any]:
    """
    Verify a commit authorization token.
    
    SECURITY: Requires JWT authentication with 'ehr_gateway' role.
    Validates token signature, expiration, and tenant match.
    
    Args:
        request: FastAPI request (for rate limiting)
        commit_token: Commit token to verify
        identity: Authenticated identity (ehr_gateway role required)
        
    Returns:
        Token validation result
        
    Raises:
        HTTPException: 403 if insufficient permissions
        HTTPException: 400 if token invalid or expired
    """
    tenant_id = identity.tenant_id
    
    try:
        # Decode and verify token
        payload = jwt.decode(commit_token, COMMIT_TOKEN_SECRET, algorithms=["HS256"])
        
        # Validate token type
        if payload.get("token_type") != "cdil_commit_authorization":
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_token_type",
                    "message": "Token is not a commit authorization token"
                }
            )
        
        # Enforce tenant boundary
        if payload.get("tenant_id") != tenant_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "tenant_mismatch",
                    "message": "Token tenant does not match authenticated tenant"
                }
            )
        
        # Check nonce (one-time use)
        nonce = payload.get("nonce")
        if nonce:
            # Check if nonce already used
            from gateway.app.services.signer import check_and_record_nonce
            
            # Note: This records the nonce, so second verification will fail
            if not check_and_record_nonce(tenant_id, nonce):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "nonce_already_used",
                        "message": "Commit token has already been used (replay detected)"
                    }
                )
        
        return {
            "valid": True,
            "certificate_id": payload.get("certificate_id"),
            "tenant_id": payload.get("tenant_id"),
            "ehr_commit_id": payload.get("ehr_commit_id"),
            "issued_at": datetime.fromtimestamp(payload.get("iat"), tz=timezone.utc).isoformat().replace('+00:00', 'Z'),
            "expires_at": datetime.fromtimestamp(payload.get("exp"), tz=timezone.utc).isoformat().replace('+00:00', 'Z')
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "token_expired",
                "message": "Commit token has expired (5 minute lifetime)"
            }
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_token",
                "message": f"Token validation failed: {str(e)}"
            }
        )
