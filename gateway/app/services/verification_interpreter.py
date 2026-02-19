"""
Verification Interpreter - Human-to-Crypto Translation Layer

Translates cryptographic verification failures into plain English explanations
with actionable recommendations for legal and audit contexts.
"""

from typing import Dict, Any, List, Optional


def interpret_verification(
    failures: List[Dict[str, Any]],
    valid: bool,
    certificate_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Interpret verification results into human-friendly format.

    Args:
        failures: List of failure dictionaries with 'check' and 'error' fields
        valid: Whether verification passed
        certificate_id: Optional certificate ID for context
        timestamp: Optional timestamp for context

    Returns:
        Dictionary with human-friendly interpretation:
        - status: "PASS" | "FAIL"
        - summary: One-line summary
        - reason: Detailed explanation (if failed)
        - recommended_action: What to do next (if failed)
        - details: List of per-check explanations
    """
    if valid:
        return {
            "status": "PASS",
            "summary": "Certificate verification successful. Document integrity confirmed.",
            "reason": None,
            "recommended_action": None,
            "details": [],
        }

    # Categorize failures
    failure_categories = _categorize_failures(failures)

    # Generate summary based on most severe failure
    summary = _generate_summary(failure_categories)

    # Generate overall reason
    reason = _generate_reason(failure_categories, failures)

    # Generate recommended action
    recommended_action = _generate_recommended_action(failure_categories)

    # Generate per-check details
    details = []
    for failure in failures:
        check = failure.get("check", "unknown")
        error = failure.get("error", "unknown_error")
        detail = _interpret_failure(check, error, failure.get("debug"))
        details.append(detail)

    return {
        "status": "FAIL",
        "summary": summary,
        "reason": reason,
        "recommended_action": recommended_action,
        "details": details,
    }


def _categorize_failures(failures: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Categorize failures by type."""
    categories = {
        "integrity": [],
        "signature": [],
        "timing": [],
        "policy": [],
        "tenant": [],
        "other": [],
    }

    for failure in failures:
        check = failure.get("check", "")
        error = failure.get("error", "")

        if "chain" in check.lower() or "hash" in check.lower():
            categories["integrity"].append(error)
        elif "signature" in check.lower():
            categories["signature"].append(error)
        elif (
            "timing" in check.lower()
            or "finalized" in error.lower()
            or "backdated" in error.lower()
        ):
            categories["timing"].append(error)
        elif "policy" in check.lower():
            categories["policy"].append(error)
        elif "tenant" in check.lower():
            categories["tenant"].append(error)
        else:
            categories["other"].append(error)

    return categories


def _generate_summary(categories: Dict[str, List[str]]) -> str:
    """Generate one-line summary of failures."""
    if categories["integrity"]:
        return (
            "Certificate verification FAILED: Document has been altered since issuance."
        )
    elif categories["signature"]:
        return "Certificate verification FAILED: Cryptographic signature is invalid."
    elif categories["timing"]:
        return "Certificate verification FAILED: Timing integrity violation detected (possible backdating)."
    elif categories["tenant"]:
        return "Certificate verification FAILED: Tenant authorization mismatch."
    elif categories["policy"]:
        return "Certificate verification FAILED: Policy provenance violation."
    else:
        return "Certificate verification FAILED: Unknown integrity violation."


def _generate_reason(
    categories: Dict[str, List[str]], failures: List[Dict[str, Any]]
) -> str:
    """Generate detailed reason for failure."""
    reasons = []

    if categories["integrity"]:
        reasons.append(
            "The document content or certificate metadata has been modified after the certificate was issued. "
            + "This breaks the cryptographic integrity chain and indicates tampering."
        )

    if categories["signature"]:
        reasons.append(
            "The cryptographic signature does not match the certificate contents. "
            + "This could indicate forgery or corruption during transmission."
        )

    if categories["timing"]:
        reasons.append(
            "The certificate finalization timestamp is after the EHR reference timestamp. "
            + "This suggests the certificate may have been backdated, which violates temporal integrity requirements."
        )

    if categories["policy"]:
        reasons.append(
            "The governance policy hash does not match or policy information is missing. "
            + "This prevents verification of which rules and compliance checks were applied."
        )

    if categories["tenant"]:
        reasons.append(
            "The certificate tenant identifier does not match the requesting organization. "
            + "Access to this certificate is restricted to the issuing tenant."
        )

    if categories["other"]:
        reasons.append(
            "Additional integrity checks failed. Review detailed error list."
        )

    return " ".join(reasons)


def _generate_recommended_action(categories: Dict[str, List[str]]) -> str:
    """Generate recommended action based on failure type."""
    if categories["tenant"]:
        return (
            "Contact the certificate issuing organization to verify access permissions. "
            + "Do not attempt to use this certificate for compliance or legal purposes."
        )

    if categories["timing"]:
        return (
            "Investigate the certificate issuance timeline. Contact the issuing organization to verify "
            + "whether the certificate was legitimately issued after the EHR record was created. "
            + "Do not rely on this certificate for legal defensibility until timing discrepancy is resolved."
        )

    if categories["integrity"] or categories["signature"]:
        return (
            "DO NOT USE this certificate. The document has failed cryptographic verification. "
            + "If this certificate was obtained from an official source, contact the issuing organization immediately. "
            + "If litigation or audit is involved, preserve all evidence including this failed verification result."
        )

    if categories["policy"]:
        return (
            "Contact the certificate issuing organization to obtain the correct governance policy documentation. "
            + "Without policy verification, compliance claims cannot be validated."
        )

    return (
        "Review the detailed failure information below. Contact the certificate issuing organization "
        + "for assistance. Do not rely on this certificate until all integrity checks pass."
    )


def _interpret_failure(
    check: str, error: str, debug: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Interpret a single failure into human-friendly detail."""
    # Map known check/error combinations to human explanations
    interpretations = {
        ("integrity_chain", "chain_hash_mismatch"): {
            "meaning": "Document altered since issuance",
            "explanation": "The integrity chain hash does not match the stored value. This means the certificate data has been modified after it was issued and signed.",
            "action": "Reject this certificate. The document has been tampered with.",
        },
        ("signature", "signature_invalid"): {
            "meaning": "Certificate signature invalid",
            "explanation": "The cryptographic signature verification failed. The signature does not match the certificate contents.",
            "action": "Reject this certificate. It may be forged or corrupted.",
        },
        ("signature", "missing_key_id"): {
            "meaning": "Signing key identifier missing",
            "explanation": "The certificate does not contain a signing key identifier. Cannot verify authenticity.",
            "action": "Reject this certificate. Missing critical signature metadata.",
        },
        ("signature", "key_not_found_and_fallback_failed"): {
            "meaning": "Signing key not available",
            "explanation": "The signing key referenced by this certificate is not available and fallback key lookup failed.",
            "action": "Contact the issuing organization to obtain the public signing key.",
        },
        ("timing", "finalized_after_ehr_reference"): {
            "meaning": "Certificate timing invalid; may be backdated",
            "explanation": "The certificate was finalized after the EHR system referenced it. This is a temporal impossibility and suggests backdating.",
            "action": "Investigate certificate issuance timeline. Do not rely on this certificate for legal purposes.",
        },
        ("policy", "policy_hash_mismatch"): {
            "meaning": "Policy provenance missing or changed",
            "explanation": "The governance policy hash in the certificate does not match expected values or is missing.",
            "action": "Obtain correct policy documentation from issuing organization.",
        },
        ("policy", "policy_missing"): {
            "meaning": "Policy provenance missing or changed",
            "explanation": "The certificate does not contain governance policy information.",
            "action": "Cannot verify compliance. Obtain policy documentation.",
        },
        ("tenant", "tenant_mismatch"): {
            "meaning": "Wrong tenant; access denied",
            "explanation": "The certificate belongs to a different organization. You do not have permission to access this certificate.",
            "action": "Contact the certificate issuing organization to verify access permissions.",
        },
    }

    key = (check, error)
    if key in interpretations:
        interp = interpretations[key]
        return {
            "check": check,
            "error": error,
            "meaning": interp["meaning"],
            "explanation": interp["explanation"],
            "action": interp["action"],
            "debug": debug,
        }

    # Default interpretation for unknown failures
    return {
        "check": check,
        "error": error,
        "meaning": f"Verification check '{check}' failed with error '{error}'",
        "explanation": "This is an unexpected failure. Review technical details.",
        "action": "Contact technical support with the certificate ID and this error code.",
        "debug": debug,
    }
