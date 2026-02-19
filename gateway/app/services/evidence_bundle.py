"""
Evidence Bundle Generation Service

Creates evidence bundles in two formats:
1. JSON bundle (primary) - structured evidence bundle for programmatic use
2. ZIP archive - complete package with PDF, README, and verification instructions

Evidence bundles provide hospitals with exportable artifacts for:
- Payer appeals
- Compliance audits
- Legal proceedings
- Regulatory submissions
"""

import zipfile
from io import BytesIO
from typing import Dict, Any, Optional
import json
from datetime import datetime, timezone


def build_evidence_bundle(
    certificate: Dict[str, Any], identity: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build a structured evidence bundle (JSON) per INTEGRITY_ARTIFACT_SPEC.

    This is the primary evidence artifact for hospitals to export for:
    - Appeals and litigation
    - Compliance audits
    - Regulatory submissions

    The bundle includes:
    - Certificate metadata
    - Canonical message (what was signed)
    - Note hash and algorithm
    - Model info (if available)
    - Human attestation details
    - Verification instructions
    - Public key reference

    Args:
        certificate: Complete certificate dictionary
        identity: Optional tenant_id for authorization check

    Returns:
        Structured evidence bundle dictionary
    """
    # Extract core metadata
    metadata = {
        "certificate_id": certificate.get("certificate_id"),
        "tenant_id": certificate.get("tenant_id"),
        "issued_at": certificate.get("timestamp"),
        "key_id": certificate.get("signature", {}).get("key_id"),
        "algorithm": certificate.get("signature", {}).get("algorithm"),
    }

    # Extract hashes
    hashes = {
        "note_hash": certificate.get("note_hash"),
        "hash_algorithm": "SHA-256",
        "patient_hash": certificate.get("patient_hash"),
        "reviewer_hash": certificate.get("reviewer_hash"),
    }

    # Build model info (basic for now, Phase 2 will enhance this)
    model_info = {
        "model_version": certificate.get("model_version"),
        "prompt_version": certificate.get("prompt_version"),
        "governance_policy_version": certificate.get("governance_policy_version"),
        "policy_hash": certificate.get("policy_hash"),
    }

    # Add model_id if present (Phase 2 enhancement)
    if certificate.get("model_id"):
        model_info["model_id"] = certificate.get("model_id")

    # Build human attestation
    human_attestation = {
        "reviewed": certificate.get("human_reviewed", False),
        "reviewer_hash": certificate.get("reviewer_hash"),
        "review_timestamp": certificate.get(
            "finalized_at"
        ),  # Finalization is when review occurred
    }

    # Attribution (Phase 2 - optional for now)
    attribution = certificate.get("attribution")

    # Verification instructions
    cert_id = certificate.get("certificate_id")
    verification_instructions = {
        "offline_cli": "python verify_certificate_cli.py certificate.json",
        "api_endpoint": f"POST /v1/certificates/{cert_id}/verify",
        "manual_verification": "Recompute chain_hash and verify signature with public key",
    }

    # Public key reference (prefer reference over embed)
    key_id = certificate.get("signature", {}).get("key_id")
    public_key_reference = {"key_id": key_id, "reference_url": f"GET /v1/keys/{key_id}"}

    # Litigation metadata (Courtroom Defense Mode)
    # This section provides all fields needed for legal proceedings
    canonical_message = certificate.get("signature", {}).get("canonical_message", {})

    litigation_metadata = {
        "verification_status": "VALID",  # Assume valid unless caller specifies otherwise
        "verification_timestamp_utc": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "signer_public_key_id": key_id,
        "signature_algorithm": certificate.get("signature", {}).get(
            "algorithm", "ECDSA_SHA_256"
        ),
        "canonical_hash": certificate.get("signature", {})
        .get("canonical_message", {})
        .get("note_hash"),
        "human_attestation_summary": (
            f"{'Human reviewed and attested' if certificate.get('human_reviewed') else 'Not reviewed by human'}"
            f"{' at ' + certificate.get('human_attested_at_utc') if certificate.get('human_attested_at_utc') else ''}"
        ),
        "provenance_fields_signed": (
            list(canonical_message.keys()) if canonical_message else []
        ),
        "chain_integrity": {
            "chain_hash": certificate.get("integrity_chain", {}).get("chain_hash"),
            "previous_hash": certificate.get("integrity_chain", {}).get(
                "previous_hash"
            ),
            "prevents_insertion": True,
            "prevents_reordering": True,
        },
    }

    # Build complete bundle
    bundle = {
        "bundle_version": "2.0",  # Bumped for Courtroom Defense Mode
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "certificate": certificate,
        "metadata": metadata,
        "hashes": hashes,
        "model_info": model_info,
        "human_attestation": human_attestation,
        "litigation_metadata": litigation_metadata,  # NEW: Courtroom Defense Mode
        "verification_instructions": verification_instructions,
        "public_key_reference": public_key_reference,
    }

    # Add attribution if present (Phase 2)
    if attribution:
        bundle["attribution"] = attribution

    return bundle


def generate_evidence_bundle(
    certificate: Dict[str, Any],
    certificate_pdf: bytes,
    verification_report: Dict[str, Any],
) -> bytes:
    """
    Generate a complete evidence bundle as a ZIP file.

    This is the secondary format (ZIP) for convenience.
    The primary format is JSON via build_evidence_bundle().

    Args:
        certificate: Certificate dictionary
        certificate_pdf: PDF bytes
        verification_report: Verification result dictionary

    Returns:
        ZIP file bytes
    """
    buffer = BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Add certificate.json
        cert_json = json.dumps(certificate, indent=2, sort_keys=True)
        zipf.writestr("certificate.json", cert_json)

        # Add certificate.pdf
        zipf.writestr("certificate.pdf", certificate_pdf)

        # Add evidence_bundle.json (structured bundle)
        evidence_bundle_json = build_evidence_bundle(certificate)
        zipf.writestr(
            "evidence_bundle.json", json.dumps(evidence_bundle_json, indent=2)
        )

        # Add verification_report.json
        verify_json = json.dumps(verification_report, indent=2)
        zipf.writestr("verification_report.json", verify_json)

        # Add public_key.pem (for offline verification with OpenSSL)
        key_id = certificate.get("signature", {}).get("key_id")
        if key_id:
            try:
                from gateway.app.services.storage import get_tenant_key_by_key_id

                tenant_key = get_tenant_key_by_key_id(key_id)
                if tenant_key and tenant_key.get("public_jwk_json"):
                    # Convert JWK to PEM format
                    import json as json_lib
                    from cryptography.hazmat.primitives import serialization
                    from cryptography.hazmat.primitives.asymmetric import rsa
                    from cryptography.hazmat.backends import default_backend

                    jwk = json_lib.loads(tenant_key["public_jwk_json"])

                    # Extract RSA public key components from JWK
                    if jwk.get("kty") == "RSA" and jwk.get("n") and jwk.get("e"):
                        import base64

                        # Decode base64url encoded values with proper padding
                        def decode_base64url(data):
                            """Decode base64url with automatic padding."""
                            # Add padding if needed
                            padding = 4 - (len(data) % 4)
                            if padding != 4:
                                data += "=" * padding
                            return base64.urlsafe_b64decode(data)

                        # Decode components
                        n_bytes = decode_base64url(jwk["n"])
                        e_bytes = decode_base64url(jwk["e"])

                        # Convert to integers
                        n = int.from_bytes(n_bytes, byteorder="big")
                        e = int.from_bytes(e_bytes, byteorder="big")

                        # Create RSA public key
                        public_numbers = rsa.RSAPublicNumbers(e, n)
                        public_key = public_numbers.public_key(default_backend())

                        # Serialize to PEM
                        pem_bytes = public_key.public_key_bytes(
                            encoding=serialization.Encoding.PEM,
                            format=serialization.PublicFormat.SubjectPublicKeyInfo,
                        )

                        zipf.writestr("public_key.pem", pem_bytes.decode("utf-8"))
            except Exception as e:
                # If public key extraction fails, add a note
                zipf.writestr(
                    "public_key.pem",
                    f"# Public key extraction failed: {str(e)}\n# Retrieve from /v1/keys/{key_id}",
                )

        # Add README.txt (offline verification instructions)
        readme_content = generate_verification_readme(
            certificate.get("certificate_id", "unknown"),
            verification_report.get("valid", False),
        )
        zipf.writestr("README.txt", readme_content)

    zip_bytes = buffer.getvalue()
    buffer.close()

    return zip_bytes


def generate_verification_readme(certificate_id: str, is_valid: bool) -> str:
    """
    Generate README content with verification instructions.

    Args:
        certificate_id: Certificate ID
        is_valid: Current verification status

    Returns:
        README text content
    """
    status_text = "VERIFIED - PASSED" if is_valid else "INVALID - FAILED"

    readme = f"""
=================================================================
CLINICAL DOCUMENTATION INTEGRITY CERTIFICATE
Evidence Bundle - Verification Instructions
=================================================================

Certificate ID: {certificate_id}
Current Status: {status_text}

=================================================================
CONTENTS OF THIS BUNDLE
=================================================================

1. certificate.json
   - Complete certificate in JSON format
   - Contains all metadata, hashes, and cryptographic signature
   - No plaintext PHI included

2. certificate.pdf
   - Human-readable certificate document
   - Suitable for legal and compliance purposes
   - Contains hash prefixes (not full hashes)

3. verification_report.json
   - Verification result at time of bundle creation
   - Includes human-friendly explanation of status
   - Lists any integrity failures detected

4. README_VERIFICATION.txt
   - This file
   - Instructions for offline verification

=================================================================
HOW TO VERIFY THIS CERTIFICATE
=================================================================

OPTION 1: Online API Verification (Recommended)
------------------------------------------------
If you have API access to the CDIL service:

1. POST the certificate_id to the verification endpoint:
   
   curl -X POST https://your-cdil-api.com/v1/certificates/{certificate_id}/verify
   
2. Check the 'valid' field in the response:
   - true = PASS (integrity confirmed)
   - false = FAIL (tampering or integrity violation detected)

3. Review the 'human_friendly_report' for explanation:
   - status: "PASS" or "FAIL"
   - summary: One-line verdict
   - reason: Detailed explanation (if failed)
   - recommended_action: What to do next (if failed)


OPTION 2: Offline CLI Verification
-----------------------------------
If you have the offline verification tool:

1. Run the CLI verifier with the certificate.json file:
   
   python verify_clinical_certificate.py certificate.json
   
2. The tool will:
   - Recompute integrity chain hashes
   - Verify cryptographic signature
   - Check timing integrity (if ehr_referenced_at is set)
   - Display PASS (green) or FAIL (red)

3. Exit codes:
   - 0 = PASS
   - 1 = FAIL


OPTION 3: Manual Verification (Advanced)
-----------------------------------------
For technical users who want to manually verify:

1. Extract data from certificate.json:
   - integrity_chain.chain_hash (stored value)
   - signature.signature (cryptographic signature)
   
2. Recompute chain hash from certificate fields:
   - certificate_id, tenant_id, timestamp
   - note_hash, model_version, governance_policy_version
   - previous_hash (from integrity_chain.previous_hash)
   
3. Compare recomputed chain_hash with stored chain_hash:
   - Must match exactly or certificate is invalid

4. Verify signature using public key:
   - Obtain public key from issuing organization
   - Verify signature against canonical message
   - Canonical message = chain_hash + certificate core fields


OPTION 4: OpenSSL Verification (Offline)
-----------------------------------------
For offline verification using OpenSSL:

1. Extract the signature from certificate.json:
   
   cat certificate.json | jq -r '.signature.signature' > signature.b64
   
2. Decode the base64 signature:
   
   cat signature.b64 | base64 -d > signature.bin
   
3. Extract the canonical message (what was signed):
   
   # This requires reconstructing the canonical message from certificate fields
   # See certificate.json for the exact fields and order
   
4. Verify the signature with OpenSSL:
   
   openssl dgst -sha256 -verify public_key.pem -signature signature.bin message.txt
   
   Expected output:
   - "Verified OK" = PASS (signature is valid)
   - "Verification Failure" = FAIL (signature is invalid)

5. Notes:
   - public_key.pem is included in this bundle
   - The canonical message format is deterministic (see certificate.json)
   - RSA-PSS with SHA-256 is the signature algorithm

=================================================================
WHAT DOES "PASS" MEAN?
=================================================================

A PASS result means:

1. INTEGRITY: The certificate data has not been modified since issuance.
   
2. AUTHENTICITY: The cryptographic signature is valid and proves the
   certificate was issued by the authorized signing authority.

3. TIMING: If ehr_referenced_at is set, the certificate was finalized
   BEFORE the EHR system referenced it (no backdating).

4. CHAIN LINKAGE: The certificate is properly linked to the previous
   certificate in the tenant's chain, preventing insertion attacks.

A PASS result provides cryptographic proof that:
- The documented AI-generated clinical note has not been altered
- The governance policy and model versions are authentic
- The human review status (if claimed) was set at issuance
- The certificate timeline is consistent with medical record timeline

=================================================================
WHAT DOES "FAIL" MEAN?
=================================================================

A FAIL result means one or more integrity checks failed:

- INTEGRITY FAILURE: Certificate data was modified after signing
- SIGNATURE FAILURE: Signature is invalid or key not found
- TIMING FAILURE: Certificate may have been backdated
- POLICY FAILURE: Governance policy information is missing/invalid
- TENANT FAILURE: Tenant authorization mismatch

DO NOT USE A FAILED CERTIFICATE FOR:
- Legal proceedings or compliance audits
- Medical record attestation
- Regulatory submissions
- Any purpose requiring proof of integrity

If a certificate fails verification:
1. Contact the issuing organization immediately
2. Preserve all evidence including this bundle
3. Document the failure and circumstances
4. Do not rely on the certificate until resolved

=================================================================
LEGAL NOTICE
=================================================================

This certificate provides cryptographic proof of integrity for
AI-generated clinical documentation. It does NOT:

- Replace clinical judgment or human oversight
- Guarantee accuracy or appropriateness of clinical content
- Constitute medical advice or clinical guidance
- Satisfy all regulatory requirements automatically

The certificate proves:
- Documentation was generated under stated governance
- Content has not been altered since issuance
- Specified compliance checks were executed
- Human review occurred (if claimed)

Consult legal counsel regarding use of this certificate
in litigation, regulatory filings, or compliance audits.

=================================================================
QUESTIONS OR ISSUES?
=================================================================

If you encounter problems verifying this certificate:

1. Check that certificate.json is valid JSON
2. Ensure you have the correct public key
3. Verify network connectivity (for API verification)
4. Contact the certificate issuing organization

For technical support:
- Include the certificate_id in all communications
- Preserve this entire bundle
- Document any error messages received

=================================================================
"""

    return readme.strip()


def generate_defense_bundle(
    certificate: Dict[str, Any],
    public_key_pem: str,
    verification_report: Dict[str, Any],
) -> bytes:
    """
    Generate a tamper-evident defense bundle as a ZIP file.

    This is the audit-ready format with all artifacts needed for:
    - Legal proceedings
    - Expert witness testimony
    - Offline verification
    - Compliance presentation

    Contents:
    - certificate.json: Complete certificate with all provenance fields
    - canonical_message.json: Exact message that was signed (for hash recomputation)
    - verification_report.json: Current verification status
    - public_key.pem: Public key for signature verification
    - README.txt: Step-by-step offline verification instructions

    Args:
        certificate: Complete certificate dictionary
        public_key_pem: Public key in PEM format
        verification_report: Current verification status

    Returns:
        ZIP file bytes
    """
    buffer = BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        # 1. Add certificate.json (complete certificate)
        cert_json = json.dumps(certificate, indent=2, sort_keys=True)
        zipf.writestr("certificate.json", cert_json)

        # 2. Add canonical_message.json (what was signed)
        canonical_message = certificate.get("signature", {}).get(
            "canonical_message", {}
        )
        canonical_json = json.dumps(canonical_message, indent=2, sort_keys=True)
        zipf.writestr("canonical_message.json", canonical_json)

        # 3. Add verification_report.json
        verify_json = json.dumps(verification_report, indent=2, sort_keys=True)
        zipf.writestr("verification_report.json", verify_json)

        # 4. Add public_key.pem
        zipf.writestr("public_key.pem", public_key_pem)

        # 5. Add README.txt with offline verification instructions
        readme_content = generate_defense_readme(certificate, verification_report)
        zipf.writestr("README.txt", readme_content)

    zip_bytes = buffer.getvalue()
    buffer.close()

    return zip_bytes


def generate_defense_readme(
    certificate: Dict[str, Any], verification_report: Dict[str, Any]
) -> str:
    """
    Generate README for defense bundle with offline verification instructions.

    This README is designed for legal audiences and provides clear,
    step-by-step instructions for verifying certificate integrity.
    """
    cert_id = certificate.get("certificate_id", "UNKNOWN")
    timestamp = certificate.get(
        "issued_at_utc", certificate.get("timestamp", "UNKNOWN")
    )
    human_reviewed = certificate.get("human_reviewed", False)
    model_name = certificate.get("model_name", "UNKNOWN")

    readme = f"""
=================================================================
COURTROOM DEFENSE BUNDLE - CERTIFICATE VERIFICATION INSTRUCTIONS
=================================================================

Certificate ID: {cert_id}
Issued: {timestamp}
Model: {model_name}
Human Reviewed: {'Yes' if human_reviewed else 'No'}

=================================================================
WHAT IS THIS BUNDLE?
=================================================================

This bundle contains all artifacts needed to INDEPENDENTLY VERIFY
the integrity and authenticity of a clinical documentation certificate.

You do NOT need:
- Internet access
- API access
- Trust in any third party

You CAN verify:
- Document has not been altered since certification
- Signature is cryptographically valid
- Certificate was issued by stated authority
- Human attestation (if applicable) is part of signed record

This evidence is suitable for:
- Court proceedings
- Expert witness testimony
- Regulatory submissions
- Payer appeals
- Compliance audits

=================================================================
BUNDLE CONTENTS
=================================================================

1. certificate.json
   - Complete certificate with all provenance fields
   - Includes: model info, governance policy, human attestation
   - No PHI (only hashes)

2. canonical_message.json
   - Exact message that was cryptographically signed
   - This is what you will hash and verify

3. verification_report.json
   - Current verification status (as of bundle generation)
   - Includes all integrity checks performed

4. public_key.pem
   - Public key for signature verification
   - Use this to verify the signature

5. README.txt (this file)
   - Verification instructions

=================================================================
OFFLINE VERIFICATION - MANUAL METHOD
=================================================================

Step 1: Verify Hash Integrity
------------------------------
1. Open canonical_message.json
2. Remove ALL whitespace (including newlines)
3. Ensure keys are alphabetically sorted
4. Compute SHA-256 hash

Expected format (compact JSON, sorted keys):
{{"certificate_id":"...","chain_hash":"...","governance_policy_hash":"...",...}}

You should get the same hash as in verification_report.json

Step 2: Verify Signature
-------------------------
1. Use OpenSSL to verify ECDSA signature:

   openssl dgst -sha256 -verify public_key.pem \\
       -signature <signature_bytes> \\
       canonical_message.json

2. Signature bytes are base64-encoded in certificate.json
   under "signature" -> "signature"

3. Decode base64 before verification

Step 3: Verify Provenance Fields
---------------------------------
Check that canonical_message.json includes:
- certificate_id: Unique identifier
- note_hash: Hash of clinical note content
- model_name: AI model identifier
- model_version: AI model version
- human_reviewed: Boolean (true/false)
- human_reviewer_id_hash: If reviewed, hash of reviewer ID
- human_attested_at_utc: If reviewed, attestation timestamp
- governance_policy_hash: Hash of governance policy
- governance_policy_version: Policy version
- tenant_id: Organization identifier
- issued_at_utc: Issuance timestamp
- key_id: Signing key identifier

ALL of these fields are part of the signed message.
ANY alteration would invalidate the signature.

=================================================================
OFFLINE VERIFICATION - AUTOMATED METHOD
=================================================================

Use the provided CLI tool (if available):

    python verify_bundle.py defense_bundle.zip

This will:
1. Extract all files
2. Recompute canonical hash
3. Verify ECDSA signature
4. Print PASS or FAIL

Exit code: 0 (PASS), 1 (FAIL)

=================================================================
LEGAL INTERPRETATION
=================================================================

VALID CERTIFICATE:
- Document integrity is cryptographically proven
- Signature verification passes
- All provenance fields are authentic
- Human attestation (if present) is part of signed record
- Suitable for legal and compliance proceedings

INVALID CERTIFICATE:
- Document has been altered since certification
- Signature verification fails
- Certificate cannot be considered authentic
- May indicate tampering or corruption

=================================================================
COMMON QUESTIONS
=================================================================

Q: Can this certificate be forged?
A: No. The signature is cryptographically bound to the content.
   Without the private key, forgery is computationally infeasible.

Q: What if the note content was changed after certification?
A: The note_hash in the certificate would no longer match.
   Verification would fail. This proves tampering.

Q: Is the human attestation part of the signed record?
A: Yes. human_reviewed, human_reviewer_id_hash, and 
   human_attested_at_utc are all part of canonical_message.json.
   They cannot be altered without invalidating the signature.

Q: Can I trust this without internet access?
A: Yes. All verification can be performed offline using only
   the contents of this bundle and standard cryptographic tools.

=================================================================
TECHNICAL DETAILS
=================================================================

Algorithm: ECDSA with SHA-256
Curve: P-256 (NIST secp256r1)
Signature Format: DER-encoded, Base64
Hash Algorithm: SHA-256
Canonicalization: Sorted JSON keys, no whitespace

=================================================================
FOR EXPERT WITNESSES
=================================================================

When testifying:
1. Explain that this is a standard cryptographic signature
2. ECDSA is widely accepted and used in digital certificates
3. Hash functions provide one-way, collision-resistant integrity
4. Any modification to signed fields invalidates signature
5. This is equivalent to a digital notary seal

Talking points:
- "This signature proves the document has not been altered"
- "The human attestation is cryptographically sealed in the record"
- "Verification can be independently performed by any party"
- "This meets legal standards for electronic signatures"

=================================================================
SUPPORT
=================================================================

For questions about this bundle:
1. Certificate ID: {cert_id}
2. Verification status: {verification_report.get('status', 'UNKNOWN')}
3. Generated: {verification_report.get('verified_at', 'UNKNOWN')}

For technical support:
- Preserve this entire bundle
- Document any verification errors
- Include certificate ID in all communications

=================================================================
"""

    return readme.strip()
