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
    SignatureBundle,
    ClinicalDocRequest,
    ClinicalDocResponse,
    ClinicalDocumentationCertificate
)
from gateway.app.services.uuid7 import generate_uuid7
from gateway.app.services.hashing import sha256_hex
from gateway.app.services.signer import sign_generic_message, verify_signature
from gateway.app.services.packet_builder import build_accountability_packet
from gateway.app.services.storage import store_transaction
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
    
    # Step 2: Hash PHI fields (note_text, patient_reference, reviewer_id)
    note_hash = sha256_hex(request.note_text.encode('utf-8'))
    
    patient_hash = None
    if request.patient_reference:
        patient_hash = sha256_hex(request.patient_reference.encode('utf-8'))
    
    reviewer_hash = None
    if request.human_reviewer_id:
        reviewer_hash = sha256_hex(request.human_reviewer_id.encode('utf-8'))
    
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
        "model_version": request.model_version,
        "prompt_version": request.prompt_version,
        "governance_policy_version": request.governance_policy_version,
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
    
    return {
        "certificate_id": certificate_id,
        "valid": valid,
        "failures": failures
    }


# Healthcare-specific clinical documentation router

router2 = APIRouter(prefix="/v1/clinical", tags=["clinical"])


def execute_governance_checks(
    request: ClinicalDocRequest,
    note_hash: str,
    patient_hash: str
) -> Dict[str, Any]:
    """
    Execute healthcare-specific governance checks.
    
    In v1, these are stubs. The architecture supports real implementations.
    
    Args:
        request: Clinical documentation request
        note_hash: Hash of the clinical note
        patient_hash: Hash of the patient ID
        
    Returns:
        Dictionary with governance check results
    """
    # Stub governance checks - real implementations would include:
    # - PHI filter to ensure no raw PHI in logs
    # - Hallucination detection scan
    # - Bias filter execution
    # - Clinical accuracy checks
    # - Regulatory compliance verification
    
    checks_executed = [
        "phi_filter_executed",
        "hallucination_scan_executed",
        "bias_filter_executed"
    ]
    
    return {
        "checks_executed": checks_executed,
        "all_passed": True,
        "policy_version": request.governance_policy_version
    }


@router2.post("/documentation", response_model=ClinicalDocResponse)
async def create_clinical_documentation_certificate(
    request: ClinicalDocRequest
) -> ClinicalDocResponse:
    """
    Generate a Clinical Documentation Integrity Certificate.
    
    This endpoint:
    1. Hashes the clinical note and patient ID (never stores raw PHI)
    2. Executes governance checks (stubs in v1)
    3. Generates integrity packet using existing infrastructure
    4. Stores the certificate
    5. Returns certificate with verification URL
    
    Flow:
    - AI vendor to this endpoint to integrity certificate
    - Certificate can be verified offline
    - No PHI stored in plaintext
    """
    # Generate certificate ID and timestamp
    certificate_id = generate_uuid7()
    timestamp_utc = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    # Hash sensitive data (never store raw)
    note_hash = sha256_hex(request.note_text.encode('utf-8'))
    patient_hash = sha256_hex(request.patient_id.encode('utf-8'))
    
    # Execute governance checks
    governance_result = execute_governance_checks(request, note_hash, patient_hash)
    
    # Build accountability packet using existing infrastructure
    # Map clinical fields to existing packet builder parameters
    packet = build_accountability_packet(
        transaction_id=certificate_id,
        gateway_timestamp_utc=timestamp_utc,
        environment=request.environment,
        client_id=request.clinician_id,
        intent_manifest="clinical-documentation",
        feature_tag=request.note_type or "clinical-note",
        user_ref=request.human_editor_id or request.clinician_id,
        prompt_hash=request.prompt_version,  # Store prompt version as hash
        rag_hash=None,
        multimodal_hash=None,
        policy_version_hash=sha256_hex(request.governance_policy_version.encode('utf-8')),
        policy_change_ref=request.governance_policy_version,
        rules_applied=governance_result["checks_executed"],
        policy_decision="approved",
        model_fingerprint=f"{request.ai_vendor}:{request.model_version}",
        param_snapshot={
            "ai_vendor": request.ai_vendor,
            "model_version": request.model_version,
            "prompt_version": request.prompt_version,
            "human_reviewed": request.human_reviewed,
            "human_editor_id": request.human_editor_id
        },
        execution={
            "outcome": "approved",
            "output_hash": note_hash,
            "encounter_id": request.encounter_id,
            "patient_hash": patient_hash,
            "governance_checks": governance_result["checks_executed"]
        }
    )
    
    # Add clinical-specific governance metadata to packet
    packet["governance_metadata"] = {
        "governance_checks": governance_result["checks_executed"],
        "policy_version": request.governance_policy_version,
        "clinical_context": {
            "encounter_id": request.encounter_id,
            "note_type": request.note_type,
            "human_reviewed": request.human_reviewed
        }
    }
    
    # Store the packet
    store_transaction(packet)
    
    # Build certificate response
    certificate = ClinicalDocumentationCertificate(
        certificate_id=certificate_id,
        encounter_id=request.encounter_id,
        model_version=request.model_version,
        prompt_version=request.prompt_version,
        governance_policy_version=request.governance_policy_version,
        note_hash=note_hash,
        patient_hash=patient_hash,
        timestamp=timestamp_utc,
        human_reviewed=request.human_reviewed,
        signature=packet["verification"]["signature_b64"],
        final_hash=packet["halo_chain"]["final_hash"],
        governance_checks=governance_result["checks_executed"]
    )
    
    # Generate verification URL (assumes standard base URL)
    verification_url = f"/v1/transactions/{certificate_id}/verify"
    
    # Get hash prefix for quick reference
    hash_prefix = packet["halo_chain"]["final_hash"][:8]
    
    return ClinicalDocResponse(
        certificate_id=certificate_id,
        verification_url=verification_url,
        hash_prefix=hash_prefix,
        certificate=certificate
    )
