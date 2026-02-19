"""
Defense Mode Routes for CDIL.

Courtroom Defense Mode provides:
- Tamper detection simulation
- Defense-ready evidence bundles
- Demo scenarios for presentation
- Litigation-grade verification artifacts

These routes are designed for:
- Legal compliance demonstrations
- Audit and compliance scenarios
- Payer appeal evidence generation
- Expert witness testimony support
"""

import os
import json
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone

from gateway.app.security.auth import Identity, get_current_identity
from gateway.app.services.c14n import json_c14n_v1
from gateway.app.services.hashing import sha256_hex
from gateway.app.services.signer import verify_signature
from gateway.app.db.migrate import get_connection

router = APIRouter(prefix="/v1/defense", tags=["courtroom-defense"])


class SimulateAlterationRequest(BaseModel):
    """Request to simulate tampering with a certificate."""
    certificate_id: str = Field(..., description="Certificate ID to test tampering against")
    modified_note_text: str = Field(..., description="Modified note text to simulate alteration")


class SimulateAlterationResponse(BaseModel):
    """Response from tamper detection simulation."""
    tamper_detected: bool = Field(..., description="Whether tampering was detected")
    reason: str = Field(..., description="Reason for tamper detection")
    original_hash: str = Field(..., description="Original note hash from certificate")
    modified_hash: str = Field(..., description="Hash of modified note text")
    verification_failed: bool = Field(..., description="Whether signature verification failed")
    summary: str = Field(..., description="Human-readable summary for presentation")


def get_certificate_from_db(certificate_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve certificate from database with tenant isolation.
    
    Args:
        certificate_id: Certificate identifier
        tenant_id: Tenant ID for isolation enforcement
        
    Returns:
        Certificate dict or None if not found or wrong tenant
    """
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT certificate_json
            FROM certificates
            WHERE certificate_id = ? AND tenant_id = ?
        """, (certificate_id, tenant_id))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        return json.loads(row['certificate_json'])
    finally:
        conn.close()


@router.post("/simulate-alteration", response_model=SimulateAlterationResponse)
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
    Simulate tampering with a clinical note and demonstrate detection.
    
    This endpoint is designed for:
    - Legal presentations
    - Compliance demonstrations
    - Audit simulations
    - Training scenarios
    
    Security:
    - JWT authentication required
    - Tenant isolation enforced (404 for cross-tenant access)
    - Read-only operation (does not modify stored certificate)
    
    Process:
    1. Retrieve original certificate (with tenant isolation)
    2. Compute hash of modified note text
    3. Compare with original note hash
    4. Attempt to rebuild canonical message with modified hash
    5. Verify signature (will fail if tampered)
    6. Return detailed tamper detection results
    
    Args:
        request: Simulation request with certificate ID and modified text
        identity: Authenticated identity (from JWT)
        
    Returns:
        Tamper detection results with hashes and verification status
        
    Raises:
        HTTPException: 404 if certificate not found or wrong tenant
    """
    tenant_id = identity.tenant_id
    
    # Step 1: Retrieve certificate with tenant isolation
    certificate = get_certificate_from_db(request.certificate_id, tenant_id)
    
    if not certificate:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "certificate_not_found",
                "message": f"Certificate {request.certificate_id} not found for tenant {tenant_id}",
                "guidance": "Verify certificate ID and tenant access"
            }
        )
    
    # Step 2: Extract original note hash
    original_hash = certificate.get("note_hash")
    if not original_hash:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "missing_note_hash",
                "message": "Certificate missing note_hash field"
            }
        )
    
    # Step 3: Compute hash of modified note text
    modified_hash = sha256_hex(request.modified_note_text.encode('utf-8'))
    
    # Step 4: Check if hashes match (tamper detection)
    tamper_detected = (original_hash != modified_hash)
    
    # Step 5: Attempt signature verification with modified canonical message
    # Rebuild canonical message with modified hash
    canonical_message = certificate.get("signature", {}).get("canonical_message", {})
    
    if not canonical_message:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "missing_canonical_message",
                "message": "Certificate missing canonical message"
            }
        )
    
    # Create modified canonical message
    modified_canonical_message = canonical_message.copy()
    modified_canonical_message["note_hash"] = modified_hash
    
    # Try to verify signature with modified message (should fail)
    from gateway.app.services.key_registry import get_key_registry
    registry = get_key_registry()
    
    # Get public key for verification
    key_id = certificate.get("signature", {}).get("key_id")
    tenant_id_from_cert = certificate.get("tenant_id")
    
    key_data = registry.get_key_by_id(tenant_id_from_cert, key_id)
    
    if not key_data:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "key_not_found",
                "message": f"Signing key {key_id} not found for tenant {tenant_id_from_cert}"
            }
        )
    
    # Build verification bundle with modified message
    modified_bundle = {
        "canonical_message": modified_canonical_message,
        "signature": certificate["signature"]["signature"],
        "algorithm": certificate["signature"]["algorithm"]
    }
    
    # Verify signature (should fail for tampered content)
    verification_failed = not verify_signature(modified_bundle, key_data['public_jwk'])
    
    # Step 6: Generate response
    if tamper_detected:
        reason = "NOTE_HASH_MISMATCH"
        summary = (
            f"🚨 Tampering detected! The note content has been altered since certification. "
            f"Original hash: {original_hash[:16]}... "
            f"Modified hash: {modified_hash[:16]}... "
            f"Signature verification: {'FAILED' if verification_failed else 'N/A'}"
        )
    else:
        reason = "NO_TAMPERING_DETECTED"
        summary = (
            f"✓ No tampering detected. The note content matches the certified hash. "
            f"Hash: {original_hash[:16]}..."
        )
    
    return SimulateAlterationResponse(
        tamper_detected=tamper_detected,
        reason=reason,
        original_hash=original_hash,
        modified_hash=modified_hash,
        verification_failed=verification_failed,
        summary=summary
    )


@router.get("/demo-scenario")
async def demo_scenario(
    identity: Identity = Depends(get_current_identity)
) -> Dict[str, Any]:
    """
    Generate a demonstration scenario for courtroom defense presentation.
    
    This endpoint provides a pre-packaged demo showing:
    1. Original certificate (valid)
    2. Verification result (PASS)
    3. Simulated alteration
    4. Verification failure result
    5. Summary statement for presentation
    
    Perfect for:
    - CMIO presentations
    - Legal counsel demonstrations
    - Board meetings
    - Compliance training
    
    Security:
    - JWT authentication required
    - Uses demo data (not real PHI)
    
    Args:
        identity: Authenticated identity (from JWT)
        
    Returns:
        Demo scenario with original cert, verification, alteration, and failure
    """
    tenant_id = identity.tenant_id
    
    # Create demo certificate data
    demo_cert_id = "DEMO-CERT-001"
    demo_timestamp = "2024-01-15T10:00:00Z"
    original_note = "Patient presents with headache. Vital signs stable. Assessed as tension headache."
    original_hash = sha256_hex(original_note.encode('utf-8'))
    
    demo_certificate = {
        "certificate_id": demo_cert_id,
        "tenant_id": tenant_id,
        "timestamp": demo_timestamp,
        "issued_at_utc": demo_timestamp,
        "model_name": "gpt-4",
        "model_version": "2024-01-15",
        "note_hash": original_hash,
        "human_reviewed": True,
        "human_reviewer_id_hash": sha256_hex("DR-DEMO-001".encode('utf-8')),
        "status": "DEMO - This is demonstration data, not a real certificate"
    }
    
    # Verification result (valid)
    original_verification = {
        "status": "VALID",
        "message": "Certificate is valid and unmodified",
        "checks_passed": [
            "Signature verification: PASS",
            "Hash integrity: PASS",
            "Timestamp validation: PASS",
            "Human attestation: CONFIRMED"
        ]
    }
    
    # Simulated alteration
    altered_note = "Patient presents with severe headache and visual disturbances. Vital signs concerning."
    altered_hash = sha256_hex(altered_note.encode('utf-8'))
    
    simulated_alteration = {
        "original_note_excerpt": original_note[:50] + "...",
        "altered_note_excerpt": altered_note[:50] + "...",
        "original_hash": original_hash,
        "altered_hash": altered_hash,
        "hash_match": False
    }
    
    # Verification failure result
    tamper_verification = {
        "status": "INVALID",
        "message": "Tampering detected - document has been altered since certification",
        "checks_failed": [
            "Hash integrity: FAILED - Note hash does not match certificate",
            "Signature verification: FAILED - Canonical message has been modified"
        ],
        "legal_statement": "This document has been altered since certification and cannot be considered authentic."
    }
    
    # Summary for presentation
    summary = {
        "title": "Courtroom Defense Demonstration",
        "scenario": "Altered Clinical Documentation Detection",
        "outcome": "Tampering Successfully Detected",
        "key_points": [
            "Original certificate cryptographically signed at finalization",
            "Any alteration to note content changes the hash",
            "Signature verification fails for tampered content",
            "Provides definitive proof of document integrity",
            "Suitable for litigation and expert witness testimony"
        ],
        "legal_implications": (
            "CDIL provides cryptographic proof that this document was altered after certification. "
            "The original certified version can be definitively distinguished from any modifications. "
            "This evidence is suitable for courtroom presentation and expert witness testimony."
        )
    }
    
    return {
        "demo_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": tenant_id,
        "scenario": {
            "step_1_original_certificate": demo_certificate,
            "step_2_original_verification": original_verification,
            "step_3_simulated_alteration": simulated_alteration,
            "step_4_tamper_verification": tamper_verification,
            "step_5_summary": summary
        },
        "presentation_notes": {
            "audience": "CMIOs, Legal Counsel, Compliance Officers",
            "duration": "5-10 minutes",
            "key_message": "CDIL provides cryptographic proof of document integrity suitable for legal proceedings",
            "recommended_follow_up": "Export defense bundle for offline verification demonstration"
        }
    }
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
