"""
Clinical documentation endpoints for CDIL.

Handles certificate issuance and verification for AI-generated clinical notes.

Security Model:
- JWT authentication required (tenant_id from authenticated identity)
- Role-based access control (clinician can issue, auditor can verify)
- Rate limiting to prevent abuse
- Per-tenant cryptographic keys
"""

import os
import uuid
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, Optional
from fastapi.responses import Response
from datetime import datetime, timezone
from slowapi import Limiter
from slowapi.util import get_remote_address

from gateway.app.models.clinical import (
    ClinicalDocumentationRequest,
    DocumentationIntegrityCertificate,
    CertificateIssuanceResponse,
)
from gateway.app.security.auth import Identity, get_current_identity, require_role
from gateway.app.services.uuid7 import generate_uuid7
from gateway.app.services.hashing import sha256_hex
from gateway.app.services.signer import sign_generic_message, verify_signature
from gateway.app.services.verification_interpreter import interpret_verification
from gateway.app.services.certificate_pdf import generate_certificate_pdf
from gateway.app.services.evidence_bundle import (
    generate_evidence_bundle,
    build_evidence_bundle,
)
from gateway.app.services.key_registry import get_key_registry
from gateway.app.routes.verify_utils import fail

router = APIRouter(prefix="/v1", tags=["clinical-documentation"])


# Rate limiter instance (respects ENV=TEST for disabling in tests)
def get_clinical_limiter():
    """Create rate limiter that respects test mode environment variables."""
    disable_limits = (
        os.environ.get("ENV") == "TEST" or os.environ.get("DISABLE_RATE_LIMITS") == "1"
    )

    if disable_limits:
        # In test mode, return a disabled limiter
        return Limiter(key_func=lambda: str(uuid.uuid4()), enabled=False)
    else:
        return Limiter(key_func=get_remote_address)


limiter = get_clinical_limiter()


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
        cursor = conn.execute(
            """
            SELECT chain_hash
            FROM certificates
            WHERE tenant_id = ?
            ORDER BY created_at_utc DESC
            LIMIT 1
        """,
            (tenant_id,),
        )
        row = cursor.fetchone()
        return row["chain_hash"] if row else None
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
    key_id = certificate["signature"]["key_id"]

    # Serialize full certificate as JSON
    certificate_json = json.dumps(certificate, sort_keys=True)

    # Current timestamp for created_at
    created_at_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Insert into database
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO certificates (
                certificate_id,
                tenant_id,
                timestamp,
                note_hash,
                chain_hash,
                key_id,
                certificate_json,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                certificate_id,
                tenant_id,
                timestamp,
                note_hash,
                chain_hash,
                key_id,
                certificate_json,
                created_at_utc,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def compute_chain_hash(
    certificate_data: Dict[str, Any], previous_hash: str | None
) -> str:
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
        "governance_policy_version": certificate_data["governance_policy_version"],
    }

    # Remove sha256: prefix from hash_c14n result
    full_hash = hash_c14n(chain_payload)
    return full_hash.replace("sha256:", "")


@router.post("/clinical/documentation", response_model=CertificateIssuanceResponse)
@limiter.limit("30/minute")  # Rate limit: 30 certificate issuances per minute
async def issue_certificate(
    request: Request,  # Required for rate limiting
    req_body: ClinicalDocumentationRequest,
    identity: Identity = Depends(require_role("clinician")),
) -> CertificateIssuanceResponse:
    """
    Issue an integrity certificate for finalized clinical documentation.

    SECURITY: Requires JWT authentication with 'clinician' role.
    Tenant ID is derived from authenticated identity, NOT from client input.

    This endpoint is called when a clinical note is finalized and ready for
    commitment to the EHR. It:

    1. Authenticates caller and extracts tenant_id from JWT
    2. Validates note_text for PHI patterns (rejects obvious PHI)
    3. Hashes note content and PHI fields (never stores plaintext)
    4. Retrieves tenant's chain head
    5. Computes new chain hash
    6. Signs the certificate with tenant-specific key
    7. Stores the certificate
    8. Returns certificate and verification URL

    Args:
        request: FastAPI request (for rate limiting)
        req_body: Clinical documentation details
        identity: Authenticated identity (injected by JWT dependency)

    Returns:
        Certificate issuance response with certificate_id and full certificate

    Raises:
        HTTPException: 400 if PHI patterns detected in note_text
        HTTPException: 401 if not authenticated
        HTTPException: 403 if insufficient permissions
        HTTPException: 429 if rate limit exceeded
    """
    # Tenant ID comes from authenticated identity, NEVER from client
    tenant_id = identity.tenant_id
    import re

    # Step 0: PHI Detection Guardrails - reject obvious PHI patterns
    # This protects against accidental PHI exposure in note_text
    note_text = req_body.note_text

    phi_patterns = {
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",  # SSN: 123-45-6789
        "phone": r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",  # Phone: 555-123-4567
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email
    }

    detected_phi = []
    for phi_type, pattern in phi_patterns.items():
        if re.search(pattern, note_text):
            detected_phi.append(phi_type)

    if detected_phi:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "phi_detected_in_note_text",
                "message": "Note text contains potential PHI patterns that should not be included",
                "detected_patterns": detected_phi,
                "guidance": "Remove SSN, phone numbers, and email addresses from note_text before submission",
            },
        )

    # Step 1: Generate certificate ID and timestamp
    certificate_id = generate_uuid7()
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    finalized_at = timestamp  # Server sets finalization time, never client

    # Step 2: Hash PHI fields (note_text, patient_reference, reviewer_id)
    # IMPORTANT: note_text is NEVER persisted in plaintext, only its hash
    note_hash = sha256_hex(note_text.encode("utf-8"))

    patient_hash = None
    if req_body.patient_reference:
        patient_hash = sha256_hex(req_body.patient_reference.encode("utf-8"))

    reviewer_hash = None
    if req_body.human_reviewer_id:
        reviewer_hash = sha256_hex(req_body.human_reviewer_id.encode("utf-8"))

    # Step 3: Compute policy hash and generate governance summary
    policy_hash = sha256_hex(req_body.governance_policy_version.encode("utf-8"))
    governance_policy_hash = policy_hash  # Same value, clearer name for signing
    governance_summary = f"Governance policy {req_body.governance_policy_version} applied. Model: {req_body.model_name} {req_body.model_version}. Human reviewed: {req_body.human_reviewed}."

    # Step 3a: Handle human attestation (Courtroom Defense Mode)
    # If human_reviewed is true, reviewer_id is REQUIRED
    if req_body.human_reviewed and not req_body.human_reviewer_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing_reviewer_id",
                "message": "human_reviewer_id is required when human_reviewed is true",
                "guidance": "Provide the reviewer's identifier for attestation integrity",
            },
        )

    # Set attestation timestamp
    human_attested_at_utc = timestamp if req_body.human_reviewed else None

    # Step 4: Get tenant's current chain head
    previous_hash = get_tenant_chain_head(tenant_id)

    # Step 5: Build certificate data for chain hash computation
    certificate_data = {
        "certificate_id": certificate_id,
        "tenant_id": tenant_id,
        "timestamp": timestamp,
        "note_hash": note_hash,
        "model_version": req_body.model_version,
        "governance_policy_version": req_body.governance_policy_version,
    }

    # Step 6: Compute chain hash
    chain_hash = compute_chain_hash(certificate_data, previous_hash)

    # Step 7: Build canonical message for signing (Courtroom Defense Mode)
    # ALL provenance fields MUST be included in the signed message
    # This provides complete chain of custody for litigation
    # Note: nonce and server_timestamp will be added by sign_generic_message()
    canonical_message = {
        "certificate_id": certificate_id,
        "chain_hash": chain_hash,
        "governance_policy_hash": governance_policy_hash,
        "governance_policy_version": req_body.governance_policy_version,
        "human_attested_at_utc": human_attested_at_utc,
        "human_reviewed": req_body.human_reviewed,
        "human_reviewer_id_hash": reviewer_hash,
        "issued_at_utc": timestamp,
        "model_name": req_body.model_name,
        "model_version": req_body.model_version,
        "note_hash": note_hash,
        "prompt_version": req_body.prompt_version,
        "tenant_id": tenant_id,
        # key_id will be added by signing function based on tenant's active key
    }

    # Step 8: Sign the certificate with per-tenant key
    # This uses tenant-specific keys for cryptographic isolation
    signature_bundle = sign_generic_message(canonical_message, tenant_id=tenant_id)

    # Step 9: Assemble complete certificate
    certificate_dict = {
        "certificate_id": certificate_id,
        "tenant_id": tenant_id,
        "timestamp": timestamp,
        "issued_at_utc": timestamp,  # Same as timestamp, but explicitly named for signed field
        "finalized_at": finalized_at,
        "ehr_referenced_at": None,  # Can be set later
        "ehr_commit_id": None,  # Can be set later
        "model_name": req_body.model_name,
        "model_version": req_body.model_version,
        "prompt_version": req_body.prompt_version,
        "governance_policy_version": req_body.governance_policy_version,
        "governance_policy_hash": governance_policy_hash,
        "policy_hash": policy_hash,  # Legacy field, same value
        "governance_summary": governance_summary,
        "note_hash": note_hash,
        "patient_hash": patient_hash,
        "reviewer_hash": reviewer_hash,  # Legacy field
        "human_reviewed": req_body.human_reviewed,
        "human_reviewer_id_hash": reviewer_hash,  # Signed field
        "human_attested_at_utc": human_attested_at_utc,
        "encounter_id": req_body.encounter_id,
        "integrity_chain": {"previous_hash": previous_hash, "chain_hash": chain_hash},
        "signature": {
            "key_id": signature_bundle["key_id"],
            "algorithm": signature_bundle["algorithm"],
            "signature": signature_bundle["signature"],
            "canonical_message": signature_bundle["canonical_message"],
        },
    }

    # Step 10: Store certificate
    store_certificate(certificate_dict)

    # Step 11: Build response
    certificate = DocumentationIntegrityCertificate(**certificate_dict)

    return CertificateIssuanceResponse(
        certificate_id=certificate_id,
        certificate=certificate,
        verify_url=f"/v1/certificates/{certificate_id}/verify",
    )


@router.get("/certificates/{certificate_id}")
@limiter.limit("100/minute")  # Rate limit: 100 certificate retrievals per minute
async def get_certificate(
    request: Request,  # Required for rate limiting
    certificate_id: str,
    identity: Identity = Depends(get_current_identity),
) -> DocumentationIntegrityCertificate:
    """
    Retrieve a certificate by its ID.

    SECURITY: Requires JWT authentication.
    Enforces tenant isolation - returns 404 if certificate belongs to different tenant.
    Returns the stored certificate with no plaintext PHI.

    Args:
        request: FastAPI request (for rate limiting)
        certificate_id: Certificate identifier
        identity: Authenticated identity (injected by JWT dependency)

    Returns:
        Complete certificate

    Raises:
        HTTPException: 401 if not authenticated
        HTTPException: 404 if certificate not found or belongs to different tenant
    """
    import json
    from gateway.app.db.migrate import get_connection

    # Use tenant_id from authenticated identity
    tenant_id = identity.tenant_id

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT certificate_json, tenant_id
            FROM certificates
            WHERE certificate_id = ?
        """,
            (certificate_id,),
        )
        row = cursor.fetchone()

        # Return 404 if not found (don't reveal existence)
        if not row:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Certificate not found"},
            )

        # Return 404 for cross-tenant access (don't reveal existence to other tenants)
        if row["tenant_id"] != tenant_id:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Certificate not found"},
            )

        certificate_dict = json.loads(row["certificate_json"])

        return DocumentationIntegrityCertificate(**certificate_dict)
    finally:
        conn.close()


@router.post("/certificates/{certificate_id}/verify")
@limiter.limit("100/minute")  # Rate limit: 100 verifications per minute
async def verify_certificate(
    request: Request,  # Required for rate limiting
    certificate_id: str,
    identity: Identity = Depends(require_role("auditor")),
) -> Dict[str, Any]:
    """
    Verify the cryptographic integrity of a certificate.

    SECURITY: Requires JWT authentication with 'auditor' role.
    Enforces tenant isolation - returns 404 if certificate belongs to different tenant.

    Verifies:
    1. Certificate exists
    2. Certificate belongs to requesting tenant

    Verifies:
    1. Certificate exists and belongs to tenant
    2. Timing integrity (if ehr_referenced_at is set)
    3. Chain hash is valid (recomputes from stored fields)
    4. Signature is valid using per-tenant key

    Args:
        request: FastAPI request (for rate limiting)
        certificate_id: Certificate identifier
        identity: Authenticated identity (injected by JWT dependency)

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

    # Use tenant_id from authenticated identity
    tenant_id = identity.tenant_id

    # Load certificate
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT certificate_json, tenant_id
            FROM certificates
            WHERE certificate_id = ?
        """,
            (certificate_id,),
        )
        row = cursor.fetchone()

        # Return 404 if not found (don't reveal existence)
        if not row:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Certificate not found"},
            )

        # Return 404 for cross-tenant access (don't reveal existence to other tenants)
        if row["tenant_id"] != tenant_id:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Certificate not found"},
            )

        certificate = json.loads(row["certificate_json"])
    finally:
        conn.close()

    failures = []

    # Verify timing integrity
    finalized_at_str = certificate.get("finalized_at")
    ehr_referenced_at_str = certificate.get("ehr_referenced_at")

    if finalized_at_str and ehr_referenced_at_str:
        try:
            from datetime import datetime

            finalized_at = datetime.fromisoformat(
                finalized_at_str.replace("Z", "+00:00")
            )
            ehr_referenced_at = datetime.fromisoformat(
                ehr_referenced_at_str.replace("Z", "+00:00")
            )

            if finalized_at > ehr_referenced_at:
                debug_info = {
                    "finalized_at": finalized_at_str,
                    "ehr_referenced_at": ehr_referenced_at_str,
                }
                failures.append(
                    fail("timing", "finalized_after_ehr_reference", debug_info)
                )
        except Exception as e:
            failures.append(
                fail("timing", "timestamp_parse_error", {"exception": type(e).__name__})
            )

    # Verify chain hash
    try:
        # Recompute chain hash from certificate fields
        certificate_data = {
            "certificate_id": certificate["certificate_id"],
            "tenant_id": certificate["tenant_id"],
            "timestamp": certificate["timestamp"],
            "note_hash": certificate["note_hash"],
            "model_version": certificate["model_version"],
            "governance_policy_version": certificate["governance_policy_version"],
        }

        previous_hash = certificate["integrity_chain"]["previous_hash"]
        recomputed_chain_hash = compute_chain_hash(certificate_data, previous_hash)
        stored_chain_hash = certificate["integrity_chain"]["chain_hash"]

        if recomputed_chain_hash != stored_chain_hash:
            debug_info = None
            if recomputed_chain_hash and stored_chain_hash:
                debug_info = {
                    "stored_prefix": stored_chain_hash[:16],
                    "recomputed_prefix": recomputed_chain_hash[:16],
                }
            failures.append(fail("integrity_chain", "chain_hash_mismatch", debug_info))
    except Exception as e:
        failures.append(
            fail(
                "integrity_chain",
                "recomputation_failed",
                {"exception": type(e).__name__},
            )
        )

    # Verify signature using per-tenant key
    signature_bundle = certificate.get("signature", {})
    key_id = signature_bundle.get("key_id")

    if not key_id:
        failures.append(fail("signature", "missing_key_id"))
    else:
        # Look up key from tenant key registry
        registry = get_key_registry()
        key_data = registry.get_key_by_id(tenant_id, key_id)

        if not key_data:
            # No fallback - per-tenant keys are required for security
            # Cross-tenant key usage would be a critical security vulnerability
            failures.append(fail("signature", "key_not_found"))
            jwk = None
        else:
            jwk = key_data.get("public_jwk")

        if jwk:
            try:
                # Reconstruct canonical message for verification
                # Check if this is a new-style signature (with nonce/timestamp)
                canonical_message = signature_bundle.get("canonical_message")

                if not canonical_message:
                    # Legacy format: reconstruct from certificate fields
                    canonical_message = {
                        "certificate_id": certificate["certificate_id"],
                        "tenant_id": certificate["tenant_id"],
                        "timestamp": certificate["timestamp"],
                        "chain_hash": certificate["integrity_chain"]["chain_hash"],
                        "note_hash": certificate["note_hash"],
                        "governance_policy_version": certificate[
                            "governance_policy_version"
                        ],
                    }

                # Build signature bundle for verification
                sig_bundle = {
                    "key_id": signature_bundle["key_id"],
                    "algorithm": signature_bundle["algorithm"],
                    "signature": signature_bundle["signature"],
                    "canonical_message": canonical_message,
                }

                signature_valid = verify_signature(sig_bundle, jwk)
                if not signature_valid:
                    failures.append(fail("signature", "invalid_signature"))
            except Exception as e:
                failures.append(
                    fail(
                        "signature",
                        "verification_failed",
                        {"exception": type(e).__name__},
                    )
                )

    valid = len(failures) == 0

    # Generate human-friendly interpretation
    human_friendly_report = interpret_verification(
        failures=failures,
        valid=valid,
        certificate_id=certificate_id,
        timestamp=certificate.get("timestamp"),
    )

    return {
        "certificate_id": certificate_id,
        "valid": valid,
        "failures": failures,
        "human_friendly_report": human_friendly_report,
    }


@router.get("/certificates/{certificate_id}/pdf")
@limiter.limit("100/minute")  # Rate limit: 100 PDF generations per minute
async def get_certificate_pdf(
    request: Request,  # Required for rate limiting
    certificate_id: str,
    identity: Identity = Depends(get_current_identity),
) -> Response:
    """
    Generate and return certificate as a formal PDF document.

    SECURITY: Requires JWT authentication.
    Enforces tenant isolation.

    Args:
        request: FastAPI request (for rate limiting)
        certificate_id: Certificate identifier
        identity: Authenticated identity (injected by JWT dependency)

    Returns:
        PDF file as application/pdf
    """
    import json
    from gateway.app.db.migrate import get_connection

    # Use tenant_id from authenticated identity
    tenant_id = identity.tenant_id

    # Load certificate with tenant check
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT certificate_json
            FROM certificates
            WHERE certificate_id = ?
        """,
            (certificate_id,),
        )
        row = cursor.fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Certificate not found"},
            )

        certificate = json.loads(row["certificate_json"])

        # Enforce tenant isolation
        if certificate.get("tenant_id") != tenant_id:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Certificate not found"},
            )
    finally:
        conn.close()

    # Verify certificate to get status
    verification_result = await verify_certificate(
        request, certificate_id, identity=identity
    )
    valid = verification_result.get("valid", False)

    # Generate PDF
    pdf_bytes = generate_certificate_pdf(certificate, valid=valid)

    # Return PDF
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=certificate-{certificate_id}.pdf"
        },
    )


@router.get("/certificates/{certificate_id}/evidence-bundle.zip")
@limiter.limit("100/minute")  # Rate limit: 100 bundle generations per minute
async def get_evidence_bundle_zip(
    request: Request,  # Required for rate limiting
    certificate_id: str,
    identity: Identity = Depends(get_current_identity),
) -> Response:
    """
    Generate and return complete evidence bundle as ZIP archive.

    SECURITY: Requires JWT authentication.
    Enforces tenant isolation.

    Bundle contains:
    - certificate.json
    - certificate.pdf
    - evidence_bundle.json
    - verification_report.json
    - README_VERIFICATION.txt

    Args:
        request: FastAPI request (for rate limiting)
        certificate_id: Certificate identifier
        identity: Authenticated identity (injected by JWT dependency)

    Returns:
        ZIP file as application/zip
    """
    import json
    from gateway.app.db.migrate import get_connection

    # Use tenant_id from authenticated identity
    tenant_id = identity.tenant_id

    # Load certificate with tenant check
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT certificate_json
            FROM certificates
            WHERE certificate_id = ?
        """,
            (certificate_id,),
        )
        row = cursor.fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Certificate not found"},
            )

        certificate = json.loads(row["certificate_json"])

        # Enforce tenant isolation
        if certificate.get("tenant_id") != tenant_id:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Certificate not found"},
            )
    finally:
        conn.close()

    # Verify certificate
    verification_report = await verify_certificate(
        request, certificate_id, identity=identity
    )

    # Generate PDF
    pdf_bytes = generate_certificate_pdf(
        certificate, valid=verification_report.get("valid", False)
    )

    # Generate bundle
    bundle_bytes = generate_evidence_bundle(
        certificate=certificate,
        certificate_pdf=pdf_bytes,
        verification_report=verification_report,
    )

    # Return ZIP
    return Response(
        content=bundle_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=evidence-bundle-{certificate_id}.zip"
        },
    )


@router.get("/certificates/{certificate_id}/evidence-bundle.json")
@limiter.limit("100/minute")  # Rate limit: 100 bundle generations per minute
async def get_evidence_bundle_json(
    request: Request,  # Required for rate limiting
    certificate_id: str,
    identity: Identity = Depends(get_current_identity),
) -> Dict[str, Any]:
    """
    Generate and return structured evidence bundle as JSON (primary format).

    SECURITY: Requires JWT authentication.
    Enforces tenant isolation - returns 404 for cross-tenant access.

    This is the primary evidence bundle format per INTEGRITY_ARTIFACT_SPEC.
    Returns a structured JSON bundle containing:
    - Certificate metadata (certificate_id, tenant_id, issued_at, key_id, algorithm)
    - Canonical message (what was signed)
    - Content hashes (note_hash, patient_hash, reviewer_hash)
    - Model info (model_version, policy_version, policy_hash)
    - Human attestation (reviewed, reviewer_hash, timestamp)
    - Verification instructions (CLI, API, manual)
    - Public key reference (key_id, reference_url)

    Use cases:
    - Payer appeals (export bundle for submission)
    - Compliance audits (demonstrate integrity proof)
    - Legal proceedings (admissible evidence)
    - Regulatory submissions (cryptographic verification)

    Args:
        request: FastAPI request (for rate limiting)
        certificate_id: Certificate identifier
        identity: Authenticated identity (injected by JWT dependency)

    Returns:
        Structured evidence bundle JSON

    Raises:
        HTTPException: 401 if not authenticated
        HTTPException: 404 if certificate not found or belongs to different tenant
    """
    import json
    from gateway.app.db.migrate import get_connection

    # Use tenant_id from authenticated identity
    tenant_id = identity.tenant_id

    # Load certificate with tenant check
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT certificate_json, tenant_id
            FROM certificates
            WHERE certificate_id = ?
        """,
            (certificate_id,),
        )
        row = cursor.fetchone()

        # Return 404 if not found (don't reveal existence)
        if not row:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Certificate not found"},
            )

        # Enforce tenant isolation (cross-tenant returns 404)
        if row["tenant_id"] != tenant_id:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Certificate not found"},
            )

        certificate = json.loads(row["certificate_json"])
    finally:
        conn.close()

    # Build structured evidence bundle
    evidence_bundle = build_evidence_bundle(certificate, identity=tenant_id)

    return evidence_bundle


@router.post("/certificates/query")
@limiter.limit("100/minute")  # Rate limit: 100 queries per minute
async def query_certificates(
    request: Request,  # Required for rate limiting
    identity: Identity = Depends(require_role("auditor")),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    model_version: Optional[str] = None,
    governance_policy_version: Optional[str] = None,
    human_reviewed: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Query certificates for audit and reporting purposes.

    SECURITY: Requires JWT authentication with 'auditor' role.
    Tenant ID is derived from authenticated identity (enforces isolation).

    Supports filtering by:
    - date_from, date_to - filter by finalized_at timestamp
    - model_version - filter by AI model version
    - governance_policy_version - filter by policy version
    - human_reviewed - filter by review status

    Args:
        request: FastAPI request (for rate limiting)
        identity: Authenticated identity (injected by JWT dependency)
        date_from: Optional start date (ISO 8601 UTC)
        date_to: Optional end date (ISO 8601 UTC)
        model_version: Optional AI model version
        governance_policy_version: Optional governance policy version
        human_reviewed: Optional human review status filter
        limit: Maximum number of results (default 100, max 1000)
        offset: Pagination offset (default 0)

    Returns:
        Dictionary with:
        - total_count: Total matching certificates
        - certificates: List of certificate summaries
        - limit: Results limit
        - offset: Results offset
    """
    import json
    from gateway.app.db.migrate import get_connection

    # Use tenant_id from authenticated identity
    tenant_id = identity.tenant_id

    # Validate limit
    if limit > 1000:
        limit = 1000

    # Build query
    query = "SELECT certificate_json FROM certificates WHERE tenant_id = ?"
    params = [tenant_id]

    # Add filters
    if date_from:
        query += " AND created_at_utc >= ?"
        params.append(date_from)

    if date_to:
        query += " AND created_at_utc <= ?"
        params.append(date_to)

    # For filters that need JSON parsing, we'll filter in Python after loading
    # This is acceptable for MVP; production would use JSON columns or denormalized fields

    # Execute query
    conn = get_connection()
    try:
        # Get total count
        count_query = query.replace("SELECT certificate_json", "SELECT COUNT(*)")
        cursor = conn.execute(count_query, params)
        total_count = cursor.fetchone()[0]

        # Get certificates with pagination
        query += " ORDER BY created_at_utc DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        # Parse certificates and apply additional filters
        certificates = []
        for row in rows:
            cert = json.loads(row["certificate_json"])

            # Apply JSON-based filters
            if model_version and cert.get("model_version") != model_version:
                continue

            if (
                governance_policy_version
                and cert.get("governance_policy_version") != governance_policy_version
            ):
                continue

            if (
                human_reviewed is not None
                and cert.get("human_reviewed") != human_reviewed
            ):
                continue

            # Build summary (no full certificate data, no PHI)
            summary = {
                "certificate_id": cert.get("certificate_id"),
                "tenant_id": cert.get("tenant_id"),
                "timestamp": cert.get("timestamp"),
                "finalized_at": cert.get("finalized_at"),
                "model_version": cert.get("model_version"),
                "prompt_version": cert.get("prompt_version"),
                "governance_policy_version": cert.get("governance_policy_version"),
                "human_reviewed": cert.get("human_reviewed"),
                "note_hash_prefix": cert.get("note_hash", "")[:16],
                "chain_hash_prefix": cert.get("integrity_chain", {}).get(
                    "chain_hash", ""
                )[:16],
            }
            certificates.append(summary)
    finally:
        conn.close()

    return {
        "total_count": total_count,
        "returned_count": len(certificates),
        "limit": limit,
        "offset": offset,
        "certificates": certificates,
    }


@router.get("/certificates/{certificate_id}/defense-bundle")
@limiter.limit("100/minute")  # Rate limit: 100 defense bundles per minute
async def get_defense_bundle(
    request: Request,  # Required for rate limiting
    certificate_id: str,
    identity: Identity = Depends(get_current_identity),
) -> Response:
    """
    Generate and return courtroom defense bundle as ZIP archive.

    This is the LITIGATION-READY format with all artifacts needed for:
    - Legal proceedings
    - Expert witness testimony
    - Offline verification
    - Courtroom presentation

    SECURITY: Requires JWT authentication.
    Enforces tenant isolation - returns 404 for cross-tenant access.

    Bundle contains:
    - certificate.json: Complete certificate with all provenance fields
    - canonical_message.json: Exact message that was signed
    - verification_report.json: Current verification status
    - public_key.pem: Public key for signature verification
    - README.txt: Step-by-step offline verification instructions for legal audiences

    The README is written for:
    - Attorneys
    - Expert witnesses
    - Judges
    - Compliance officers

    Args:
        request: FastAPI request (for rate limiting)
        certificate_id: Certificate identifier
        identity: Authenticated identity (injected by JWT dependency)

    Returns:
        ZIP file as application/zip

    Raises:
        HTTPException: 404 if certificate not found or wrong tenant
    """
    import json
    from gateway.app.db.migrate import get_connection
    from gateway.app.services.key_registry import get_key_registry
    from gateway.app.services.evidence_bundle import generate_defense_bundle
    from cryptography.hazmat.primitives import serialization

    tenant_id = identity.tenant_id

    # Retrieve certificate with tenant isolation
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT certificate_json
            FROM certificates
            WHERE certificate_id = ?
        """,
            (certificate_id,),
        )
        row = cursor.fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Certificate not found"},
            )

        certificate = json.loads(row["certificate_json"])

        # Enforce tenant isolation
        if certificate.get("tenant_id") != tenant_id:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Certificate not found"},
            )
    finally:
        conn.close()

    # Verify certificate to get current status
    verification_result = await verify_certificate(
        request, certificate_id, identity=identity
    )

    # Get public key for signature verification
    key_id = certificate.get("signature", {}).get("key_id")
    tenant_id_from_cert = certificate.get("tenant_id")

    registry = get_key_registry()
    key_data = registry.get_key_by_id(tenant_id_from_cert, key_id)

    if not key_data:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "key_not_found",
                "message": f"Signing key {key_id} not found for tenant {tenant_id_from_cert}",
            },
        )

    # Convert public key to PEM format
    # First, convert JWK to public key object
    from gateway.app.services.signer import _jwk_to_public_key

    public_key = _jwk_to_public_key(key_data["public_jwk"])

    # Serialize to PEM
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    # Generate defense bundle ZIP
    zip_bytes = generate_defense_bundle(
        certificate=certificate,
        public_key_pem=public_key_pem,
        verification_report=verification_result,
    )

    # Return ZIP file
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=defense-bundle-{certificate_id}.zip"
        },
    )
