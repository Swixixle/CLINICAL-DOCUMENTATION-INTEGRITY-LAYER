"""
Evidence Bundle Generation Service

Creates ZIP archives containing:
- Certificate JSON
- Certificate PDF
- Verification report JSON
- README with verification instructions
"""

import zipfile
from io import BytesIO
from typing import Dict, Any
import json


def generate_evidence_bundle(
    certificate: Dict[str, Any],
    certificate_pdf: bytes,
    verification_report: Dict[str, Any]
) -> bytes:
    """
    Generate a complete evidence bundle as a ZIP file.
    
    Args:
        certificate: Certificate dictionary
        certificate_pdf: PDF bytes
        verification_report: Verification result dictionary
        
    Returns:
        ZIP file bytes
    """
    buffer = BytesIO()
    
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add certificate.json
        cert_json = json.dumps(certificate, indent=2, sort_keys=True)
        zipf.writestr('certificate.json', cert_json)
        
        # Add certificate.pdf
        zipf.writestr('certificate.pdf', certificate_pdf)
        
        # Add verification_report.json
        verify_json = json.dumps(verification_report, indent=2)
        zipf.writestr('verification_report.json', verify_json)
        
        # Add README_VERIFICATION.txt
        readme_content = generate_verification_readme(
            certificate.get('certificate_id', 'unknown'),
            verification_report.get('valid', False)
        )
        zipf.writestr('README_VERIFICATION.txt', readme_content)
    
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
