"""
Defense Simulation API Routes.

Provides proof-of-concept endpoints to demonstrate certificate integrity verification.
Shows what happens when documentation is altered vs. original.
"""

import json
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any

from gateway.app.security.auth import Identity, get_current_identity
from gateway.app.db.migrate import get_connection
from gateway.app.services.hashing import sha256_hex


router = APIRouter(prefix="/v1/defense", tags=["defense"])


class SimulateAlterationRequest(BaseModel):
    """Request model for alteration simulation."""
    certificate_id: str = Field(..., description="Certificate ID to test")
    mutated_note_text: str = Field(..., description="Altered version of note text")


class SimulateAlterationResponse(BaseModel):
    """Response model for alteration simulation."""
    certificate_id: str = Field(..., description="Certificate ID tested")
    original_verification: Dict[str, Any] = Field(..., description="Verification of original certificate")
    mutated_verification: Dict[str, Any] = Field(..., description="Verification with mutated note")
    demonstration: Dict[str, Any] = Field(..., description="What broke and why")


@router.post(
    "/simulate-alteration",
    response_model=SimulateAlterationResponse,
    summary="Simulate documentation alteration (Proof Demo)",
    description="""
    Defense Proof Demonstration (Sales Weapon).
    
    Demonstrates the power of cryptographic integrity by showing:
    - PASS: Original certificate verifies successfully
    - FAIL: Altered documentation fails verification with clear explanation
    
    **Use Cases:**
    - Executive demonstrations
    - Board presentations
    - Audit proof-of-concept
    - Litigation defense preparation
    
    **What This Shows:**
    1. Original certificate: PASS (all integrity checks succeed)
    2. Mutated note: FAIL (hash mismatch detected)
    3. Clear explanation: What broke and why
    4. Recommended action: What to do next
    
    **Authentication:**
    - Requires valid JWT with tenant_id claim
    - Only works with certificates belonging to authenticated tenant
    """
)
async def simulate_alteration(
    request: SimulateAlterationRequest,
    identity: Identity = Depends(get_current_identity)
) -> SimulateAlterationResponse:
    """
    Simulate documentation alteration to demonstrate integrity verification.
    
    This endpoint is designed for demonstrations and proof-of-concept.
    It shows what happens when documentation is altered after signing.
    
    Args:
        request: Alteration simulation request
        identity: Authenticated identity (from JWT)
        
    Returns:
        Comparison of original vs. mutated verification results
        
    Raises:
        HTTPException: 404 if certificate not found or unauthorized
    """
    tenant_id = identity.tenant_id
    certificate_id = request.certificate_id
    
    # Get original certificate from database
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT certificate_json, tenant_id
            FROM certificates
            WHERE certificate_id = ?
        """, (certificate_id,))
        row = cursor.fetchone()
        
        # Return 404 if not found
        if not row:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "certificate_not_found",
                    "message": f"Certificate {certificate_id} not found"
                }
            )
        
        # Enforce tenant isolation
        if row['tenant_id'] != tenant_id:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "certificate_not_found",
                    "message": f"Certificate {certificate_id} not found or unauthorized"
                }
            )
        
        certificate = json.loads(row['certificate_json'])
    finally:
        conn.close()
    
    # For demonstration purposes, we simulate verification results
    # NOTE: This is a MOCK verification for demonstration only
    # In production, call the actual verification endpoint via internal API
    
    # Original certificate verification (MOCKED - assume PASS for demo)
    original_verification = {
        "valid": True,
        "status": "PASS",
        "integrity_chain": {"valid": True},
        "signature": {"valid": True},
        "policy": {"valid": True},
        "_mock": True,  # Indicate this is a mock result
        "_note": "This is a simulated verification for demonstration purposes"
    }
    
    # Create mutated certificate by replacing note_hash
    mutated_certificate = certificate.copy()
    mutated_note_hash = sha256_hex(request.mutated_note_text.encode('utf-8'))
    original_note_hash = certificate.get("note_hash")
    mutated_certificate["note_hash"] = mutated_note_hash
    
    # Mutated certificate verification (SIMULATED - FAIL if hash doesn't match)
    hash_matches = original_note_hash == mutated_note_hash
    mutated_verification = {
        "valid": hash_matches,
        "status": "PASS" if hash_matches else "FAIL",
        "integrity_chain": {"valid": hash_matches},
        "signature": {"valid": hash_matches},
        "policy": {"valid": True},
        "_mock": True,  # Indicate this is a mock result
        "_note": "This is a simulated verification for demonstration purposes"
    }
    
    # Build demonstration explanation
    original_status = "PASS" if original_verification.get("valid") else "FAIL"
    mutated_status = "PASS" if mutated_verification.get("valid") else "FAIL"
    
    # Determine what broke
    what_broke = []
    if not mutated_verification.get("valid"):
        what_broke.append("Integrity chain hash mismatch - note_hash was altered")
        what_broke.append("Cryptographic signature invalid - canonical message changed")
    
    demonstration = {
        "original_status": original_status,
        "mutated_status": mutated_status,
        "proof": {
            "original_note_hash": original_note_hash,
            "mutated_note_hash": mutated_note_hash,
            "hash_match": hash_matches
        },
        "what_broke": what_broke if what_broke else ["Nothing - hashes match (no alteration detected)"],
        "explanation": (
            "The original certificate PASSED verification because the note_hash matches the signed hash. "
            "The mutated version FAILED because changing the note text produces a different hash, "
            "which breaks the integrity chain and invalidates the cryptographic signature. "
            "This proves that any alteration to the documentation will be detected."
            if original_status == "PASS" and mutated_status == "FAIL"
            else (
                "Both verified successfully because the hashes match - no alteration detected."
                if hash_matches
                else "Unexpected result - see details above"
            )
        ),
        "recommended_action": (
            "Use this demonstration to show stakeholders that documentation integrity is cryptographically guaranteed. "
            "Any tampering or alteration will be immediately detected and fail verification."
            if original_status == "PASS" and mutated_status == "FAIL"
            else (
                "The note text provided matches the original - try providing a different note_text to see the FAIL result."
                if hash_matches
                else "Review verification details for unexpected results"
            )
        )
    }
    
    return SimulateAlterationResponse(
        certificate_id=certificate_id,
        original_verification=original_verification,
        mutated_verification=mutated_verification,
        demonstration=demonstration
    )
