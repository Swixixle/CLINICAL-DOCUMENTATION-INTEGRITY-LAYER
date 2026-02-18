"""
Clinical documentation endpoints for CDIL.

Handles certificate issuance and verification for AI-generated clinical notes.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from datetime import datetime, timezone

from gateway.app.models.clinical import (
    ClinicalDocumentationRequest,
    DocumentationIntegrityCertificate,
    CertificateIssuanceResponse,
    IntegrityChain,
    SignatureBundle
)
from gateway.app.services.uuid7 import generate_uuid7
from gateway.app.services.hashing import sha256_hex
from gateway.app.services.signer import sign_generic_message, verify_signature
from gateway.app.services.verification_interpreter import interpret_verification
from gateway.app.routes.verify_utils import fail

router = APIRouter(prefix="/v1", tags=["clinical-documentation"])


def get_tenant_chain_head(tenant_id: str) -> str | None:
    """
    Get the current chain head hash for a tenant.
    
    Args:
        tenant_id: Tenant identifier
        
    Returns:
        Previous chain hash, or None if this is the first certificate for the tenant
    """
    from gateway.app.db.migrate import get_connection
    
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT chain_hash
            FROM certificates
            WHERE tenant_id = ?
            ORDER BY created_at_utc DESC
            LIMIT 1
        """, (tenant_id,))
        row = cursor.fetchone()
        return row['chain_hash'] if row else None
    finally:
        conn.close()


def store_certificate(certificate: Dict[str, Any]) -> None:
    """
    Store a certificate in the database.
    
    Args:
        certificate: Complete certificate dictionary
    """
    import json
    from gateway.app.db.migrate import get_connection
    
    # Extract fields for indexing
    certificate_id = certificate["certificate_id"]
    tenant_id = certificate["tenant_id"]
    timestamp = certificate["timestamp"]
    note_hash = certificate["note_hash"]
    chain_hash = certificate["integrity_chain"]["chain_hash"]
    
    # Serialize full certificate as JSON
    certificate_json = json.dumps(certificate, sort_keys=True)
    
    # Current timestamp for created_at
    created_at_utc = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    # Insert into database
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO certificates (
                certificate_id,
                tenant_id,
                timestamp,
                note_hash,
                chain_hash,
                certificate_json,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            certificate_id,
            tenant_id,
            timestamp,
            note_hash,
            chain_hash,
            certificate_json,
            created_at_utc
        ))
        conn.commit()
    finally:
        conn.close()


def compute_chain_hash(certificate_data: Dict[str, Any], previous_hash: str | None) -> str:
    """
    Compute the integrity chain hash for a certificate.
    
    Args:
        certificate_data: Core certificate fields
        previous_hash: Hash of previous certificate in chain (or None for first)
        
    Returns:
        Chain hash as hex string
    """
    from gateway.app.services.hashing import hash_c14n
    
    chain_payload = {
        "previous_hash": previous_hash,
        "certificate_id": certificate_data["certificate_id"],
        "tenant_id": certificate_data["tenant_id"],
        "timestamp": certificate_data["timestamp"],
        "note_hash": certificate_data["note_hash"],
        "model_version": certificate_data["model_version"],
        "governance_policy_version": certificate_data["governance_policy_version"]
    }
    
    # Remove sha256: prefix from hash_c14n result
    full_hash = hash_c14n(chain_payload)
    return full_hash.replace("sha256:", "")


@router.post("/clinical/documentation", response_model=CertificateIssuanceResponse)
async def issue_certificate(request: ClinicalDocumentationRequest) -> CertificateIssuanceResponse:
    """
    Issue an integrity certificate for finalized clinical documentation.
    
    This endpoint is called when a clinical note is finalized and ready for
    commitment to the EHR. It:
    
    1. Hashes note content and PHI fields
    2. Retrieves tenant's chain head
    3. Computes new chain hash
    4. Signs the certificate
    5. Stores the certificate
    6. Returns certificate and verification URL
    
    Args:
        request: Clinical documentation details
        
    Returns:
        Certificate issuance response with certificate_id and full certificate
    """
    # Step 1: Generate certificate ID and timestamp
    certificate_id = generate_uuid7()
    timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    finalized_at = timestamp  # Server sets finalization time, never client
    
    # Step 2: Hash PHI fields (note_text, patient_reference, reviewer_id)
    note_hash = sha256_hex(request.note_text.encode('utf-8'))
    
    patient_hash = None
    if request.patient_reference:
        patient_hash = sha256_hex(request.patient_reference.encode('utf-8'))
    
    reviewer_hash = None
    if request.human_reviewer_id:
        reviewer_hash = sha256_hex(request.human_reviewer_id.encode('utf-8'))
    
    # Step 3: Compute policy hash and generate governance summary
    policy_hash = sha256_hex(request.governance_policy_version.encode('utf-8'))
    governance_summary = f"Governance policy {request.governance_policy_version} applied. Model: {request.model_version}. Human reviewed: {request.human_reviewed}."
    
    # Step 3: Get tenant's current chain head
    previous_hash = get_tenant_chain_head(request.tenant_id)
    
    # Step 4: Build certificate data for chain hash computation
    certificate_data = {
        "certificate_id": certificate_id,
        "tenant_id": request.tenant_id,
        "timestamp": timestamp,
        "note_hash": note_hash,
        "model_version": request.model_version,
        "governance_policy_version": request.governance_policy_version
    }
    
    # Step 5: Compute chain hash
    chain_hash = compute_chain_hash(certificate_data, previous_hash)
    
    # Step 6: Build canonical message for signing
    canonical_message = {
        "certificate_id": certificate_id,
        "tenant_id": request.tenant_id,
        "timestamp": timestamp,
        "chain_hash": chain_hash,
        "note_hash": note_hash,
        "governance_policy_version": request.governance_policy_version
    }
    
    # Step 7: Sign the certificate
    signature_bundle = sign_generic_message(canonical_message)
    
    # Step 8: Assemble complete certificate
    certificate_dict = {
        "certificate_id": certificate_id,
        "tenant_id": request.tenant_id,
        "timestamp": timestamp,
        "finalized_at": finalized_at,
        "ehr_referenced_at": None,  # Can be set later
        "ehr_commit_id": None,  # Can be set later
        "model_version": request.model_version,
        "prompt_version": request.prompt_version,
        "governance_policy_version": request.governance_policy_version,
        "policy_hash": policy_hash,
        "governance_summary": governance_summary,
        "note_hash": note_hash,
        "patient_hash": patient_hash,
        "reviewer_hash": reviewer_hash,
        "encounter_id": request.encounter_id,
        "human_reviewed": request.human_reviewed,
        "integrity_chain": {
            "previous_hash": previous_hash,
            "chain_hash": chain_hash
        },
        "signature": {
            "key_id": signature_bundle["key_id"],
            "algorithm": signature_bundle["algorithm"],
            "signature": signature_bundle["signature"]
        }
    }
    
    # Step 9: Store certificate
    store_certificate(certificate_dict)
    
    # Step 10: Build response
    certificate = DocumentationIntegrityCertificate(**certificate_dict)
    
    return CertificateIssuanceResponse(
        certificate_id=certificate_id,
        certificate=certificate,
        verify_url=f"/v1/certificates/{certificate_id}/verify"
    )


@router.get("/certificates/{certificate_id}")
async def get_certificate(certificate_id: str) -> DocumentationIntegrityCertificate:
    """
    Retrieve a certificate by its ID.
    
    Returns the stored certificate with no plaintext PHI.
    
    Args:
        certificate_id: Certificate identifier
        
    Returns:
        Complete certificate
        
    Raises:
        HTTPException: 404 if certificate not found
    """
    import json
    from gateway.app.db.migrate import get_connection
    
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT certificate_json
            FROM certificates
            WHERE certificate_id = ?
        """, (certificate_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail=f"Certificate not found: {certificate_id}")
        
        certificate_dict = json.loads(row['certificate_json'])
        return DocumentationIntegrityCertificate(**certificate_dict)
    finally:
        conn.close()


@router.post("/certificates/{certificate_id}/verify")
async def verify_certificate(certificate_id: str) -> Dict[str, Any]:
    """
    Verify the cryptographic integrity of a certificate.
    
    Verifies:
    1. Certificate exists
    2. Chain hash is valid (recomputes from stored fields)
    3. Signature is valid
    
    Args:
        certificate_id: Certificate identifier
        
    Returns:
        Verification result with:
        - certificate_id: str
        - valid: bool
        - failures: list of failure details (empty if valid)
        
    Each failure includes:
        - check: str (what was being checked)
        - error: str (error code/message)
        - debug: dict (optional debug info, no sensitive data)
    """
    import json
    from gateway.app.db.migrate import get_connection
    from gateway.app.services.signer import verify_signature
    from gateway.app.services.storage import get_key
    
    # Load certificate
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT certificate_json
            FROM certificates
            WHERE certificate_id = ?
        """, (certificate_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail=f"Certificate not found: {certificate_id}")
        
        certificate = json.loads(row['certificate_json'])
    finally:
        conn.close()
    
    failures = []
    
    # Verify timing integrity
    finalized_at_str = certificate.get("finalized_at")
    ehr_referenced_at_str = certificate.get("ehr_referenced_at")
    
    if finalized_at_str and ehr_referenced_at_str:
        try:
            from datetime import datetime
            finalized_at = datetime.fromisoformat(finalized_at_str.replace('Z', '+00:00'))
            ehr_referenced_at = datetime.fromisoformat(ehr_referenced_at_str.replace('Z', '+00:00'))
            
            if finalized_at > ehr_referenced_at:
                debug_info = {
                    "finalized_at": finalized_at_str,
                    "ehr_referenced_at": ehr_referenced_at_str
                }
                failures.append(fail("timing", "finalized_after_ehr_reference", debug_info))
        except Exception as e:
            failures.append(fail("timing", "timestamp_parse_error", {"exception": type(e).__name__}))
    
    # Verify chain hash
    try:
        # Recompute chain hash from certificate fields
        certificate_data = {
            "certificate_id": certificate["certificate_id"],
            "tenant_id": certificate["tenant_id"],
            "timestamp": certificate["timestamp"],
            "note_hash": certificate["note_hash"],
            "model_version": certificate["model_version"],
            "governance_policy_version": certificate["governance_policy_version"]
        }
        
        previous_hash = certificate["integrity_chain"]["previous_hash"]
        recomputed_chain_hash = compute_chain_hash(certificate_data, previous_hash)
        stored_chain_hash = certificate["integrity_chain"]["chain_hash"]
        
        if recomputed_chain_hash != stored_chain_hash:
            debug_info = None
            if recomputed_chain_hash and stored_chain_hash:
                debug_info = {
                    "stored_prefix": stored_chain_hash[:16],
                    "recomputed_prefix": recomputed_chain_hash[:16]
                }
            failures.append(fail("integrity_chain", "chain_hash_mismatch", debug_info))
    except Exception as e:
        failures.append(fail("integrity_chain", "recomputation_failed", {"exception": type(e).__name__}))
    
    # Verify signature
    signature_bundle = certificate.get("signature", {})
    key_id = signature_bundle.get("key_id")
    
    if not key_id:
        failures.append(fail("signature", "missing_key_id"))
    else:
        # Look up key in database
        key = get_key(key_id)
        
        if not key:
            # Fallback to dev JWK
            from pathlib import Path
            jwk_path = Path(__file__).parent.parent / "dev_keys" / "dev_public.jwk.json"
            try:
                with open(jwk_path, 'r') as f:
                    jwk = json.load(f)
            except Exception:
                failures.append(fail("signature", "key_not_found_and_fallback_failed"))
                jwk = None
        else:
            jwk = key.get("jwk")
        
        if jwk:
            try:
                # Reconstruct canonical message for verification
                canonical_message = {
                    "certificate_id": certificate["certificate_id"],
                    "tenant_id": certificate["tenant_id"],
                    "timestamp": certificate["timestamp"],
                    "chain_hash": certificate["integrity_chain"]["chain_hash"],
                    "note_hash": certificate["note_hash"],
                    "governance_policy_version": certificate["governance_policy_version"]
                }
                
                # Build signature bundle for verification
                sig_bundle = {
                    "key_id": signature_bundle["key_id"],
                    "algorithm": signature_bundle["algorithm"],
                    "signature": signature_bundle["signature"],
                    "canonical_message": canonical_message
                }
                
                signature_valid = verify_signature(sig_bundle, jwk)
                if not signature_valid:
                    failures.append(fail("signature", "invalid_signature"))
            except Exception as e:
                failures.append(fail("signature", "verification_failed", {"exception": type(e).__name__}))
    
    valid = len(failures) == 0
    
    # Generate human-friendly interpretation
    human_friendly_report = interpret_verification(
        failures=failures,
        valid=valid,
        certificate_id=certificate_id,
        timestamp=certificate.get("timestamp")
    )
    
    return {
        "certificate_id": certificate_id,
        "valid": valid,
        "failures": failures,
        "human_friendly_report": human_friendly_report
    }
