"""
Defense Simulation API Routes.

Provides proof-of-concept endpoints to demonstrate certificate integrity verification.
Shows what happens when documentation is altered vs. original.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any

from gateway.app.security.auth import Identity, get_current_identity
from gateway.app.services.storage import get_certificate
from gateway.app.services.hashing import sha256_hex
from gateway.app.services.verification_interpreter import verify_certificate


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
    
    # Get original certificate
    certificate = get_certificate(certificate_id, tenant_id)
    
    if not certificate:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "certificate_not_found",
                "message": f"Certificate {certificate_id} not found or unauthorized"
            }
        )
    
    # Verify original certificate
    original_verification = verify_certificate(certificate)
    
    # Create mutated certificate by replacing note_hash
    mutated_certificate = certificate.copy()
    mutated_note_hash = sha256_hex(request.mutated_note_text.encode('utf-8'))
    mutated_certificate["note_hash"] = mutated_note_hash
    
    # Verify mutated certificate
    mutated_verification = verify_certificate(mutated_certificate)
    
    # Build demonstration explanation
    original_status = "PASS" if original_verification.get("valid") else "FAIL"
    mutated_status = "PASS" if mutated_verification.get("valid") else "FAIL"
    
    # Determine what broke
    what_broke = []
    if not mutated_verification.get("valid"):
        if not mutated_verification.get("integrity_chain", {}).get("valid"):
            what_broke.append("Integrity chain hash mismatch - note_hash was altered")
        if not mutated_verification.get("signature", {}).get("valid"):
            what_broke.append("Cryptographic signature invalid - canonical message changed")
    
    demonstration = {
        "original_status": original_status,
        "mutated_status": mutated_status,
        "proof": {
            "original_note_hash": certificate.get("note_hash"),
            "mutated_note_hash": mutated_note_hash,
            "hash_match": certificate.get("note_hash") == mutated_note_hash
        },
        "what_broke": what_broke if what_broke else ["Nothing - both verified successfully (unexpected)"],
        "explanation": (
            "The original certificate PASSED verification because the note_hash matches the signed hash. "
            "The mutated version FAILED because changing the note text produces a different hash, "
            "which breaks the integrity chain and invalidates the cryptographic signature. "
            "This proves that any alteration to the documentation will be detected."
            if original_status == "PASS" and mutated_status == "FAIL"
            else "Unexpected result - see details above"
        ),
        "recommended_action": (
            "Use this demonstration to show stakeholders that documentation integrity is cryptographically guaranteed. "
            "Any tampering or alteration will be immediately detected and fail verification."
            if original_status == "PASS" and mutated_status == "FAIL"
            else "Review verification details for unexpected results"
        )
    }
    
    return SimulateAlterationResponse(
        certificate_id=certificate_id,
        original_verification=original_verification,
        mutated_verification=mutated_verification,
        demonstration=demonstration
    )
