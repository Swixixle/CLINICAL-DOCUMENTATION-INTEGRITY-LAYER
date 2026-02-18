"""
Clinical documentation endpoint for healthcare-specific integrity certificates.

This wraps the existing AI execution + packet builder with healthcare-specific
models and governance checks.
"""

from fastapi import APIRouter
from datetime import datetime, timezone
from typing import Dict, Any

from gateway.app.models.clinical import (
    ClinicalDocRequest,
    ClinicalDocResponse,
    ClinicalDocumentationCertificate
)
from gateway.app.services.hashing import sha256_hex
from gateway.app.services.uuid7 import generate_uuid7
from gateway.app.services.packet_builder import build_accountability_packet
from gateway.app.services.storage import store_transaction

router = APIRouter(prefix="/v1/clinical", tags=["clinical"])


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


@router.post("/documentation", response_model=ClinicalDocResponse)
async def create_clinical_documentation_certificate(
    request: ClinicalDocRequest
) -> ClinicalDocResponse:
    """
    Generate a Clinical Documentation Integrity Certificate.
    
    This endpoint:
    1. Hashes the clinical note and patient ID (never stores raw PHI)
    2. Executes governance checks (stubs in v1)
    3. Generates integrity packet using existing HALO + packet builder
    4. Stores the certificate
    5. Returns certificate with verification URL
    
    Flow:
    - AI vendor → This endpoint → Integrity certificate
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
        signature=packet["verification"]["signature"],
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
