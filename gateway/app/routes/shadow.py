"""
Shadow Mode routes for Evidence Deficit Intelligence.

Shadow Mode is a read-only analysis feature that:
- Analyzes clinical notes + structured context
- Identifies documentation deficits and denial risks
- Provides actionable recommendations
- Does NOT write back to EHR or store PHI

Security:
- JWT authentication required (tenant_id from JWT, never from request)
- Rate limiting to prevent abuse
- No PHI storage (only hashes and aggregates)
"""

import os
import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from typing import Any

from gateway.app.models.shadow import ShadowRequest, ShadowResult
from gateway.app.security.auth import Identity, get_current_identity
from gateway.app.services.hashing import sha256_hex
from gateway.app.services.evidence_scoring import score_evidence, get_score_band
from gateway.app.services.shadow_dashboard import build_dashboard_payload


router = APIRouter(prefix="/v1/shadow", tags=["shadow-mode"])


def canonicalize_request(request: ShadowRequest) -> str:
    """
    Canonicalize request for hashing.
    
    Ensures deterministic hash for same logical input.
    
    Args:
        request: Shadow mode request
        
    Returns:
        Canonical JSON string
    """
    # Convert to dict and sort keys
    data = request.model_dump()
    
    # Sort lists for determinism
    if "diagnoses" in data:
        data["diagnoses"] = sorted(data["diagnoses"])
    if "procedures" in data:
        data["procedures"] = sorted(data["procedures"])
    if "problem_list" in data:
        data["problem_list"] = sorted(data["problem_list"])
    if "meds" in data:
        data["meds"] = sorted(data["meds"])
    
    # Sort labs by name
    if "labs" in data:
        data["labs"] = sorted(data["labs"], key=lambda x: x["name"])
    
    # Sort vitals by name
    if "vitals" in data:
        data["vitals"] = sorted(data["vitals"], key=lambda x: x["name"])
    
    # Convert to canonical JSON (sorted keys, no whitespace)
    return json.dumps(data, sort_keys=True, separators=(',', ':'))


@router.post(
    "/evidence-deficit",
    response_model=ShadowResult,
    summary="Analyze evidence deficits in clinical documentation",
    description="""
    Shadow Mode evidence deficit analysis (read-only).
    
    Analyzes clinical note + structured context to identify:
    - Documentation gaps
    - Clinical inconsistencies
    - Denial risk factors
    - Recommended actions
    
    **Important Disclaimers:**
    - This is NOT clinical decision support
    - This is NOT billing/coding advice
    - Results are heuristic risk indicators, not guarantees
    - No PHI is stored (only hashes and aggregate scores)
    
    **Authentication:**
    - Requires valid JWT with tenant_id claim
    - Tenant context is derived from JWT, never from request
    
    **Rate Limiting:**
    - Applied per IP to prevent abuse
    - Disabled in test environments
    """
)
async def analyze_evidence_deficit(
    request: ShadowRequest,
    identity: Identity = Depends(get_current_identity)
) -> ShadowResult:
    """
    Analyze clinical documentation for evidence deficits.
    
    This endpoint performs read-only analysis and does not:
    - Write to EHR systems
    - Store PHI in plaintext
    - Make clinical decisions
    - Provide billing advice
    
    Args:
        request: Clinical documentation and context
        identity: Authenticated identity (from JWT)
        
    Returns:
        Evidence deficit analysis with dashboard payload
        
    Raises:
        HTTPException: 400 for invalid input, 401 for auth failure
    """
    # Validate encounter type
    valid_encounter_types = {"inpatient", "observation", "outpatient", "ed"}
    if request.encounter_type not in valid_encounter_types:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_encounter_type",
                "message": f"encounter_type must be one of: {valid_encounter_types}"
            }
        )
    
    # Validate service line
    valid_service_lines = {"medicine", "surgery", "icu", "other"}
    if request.service_line not in valid_service_lines:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_service_line",
                "message": f"service_line must be one of: {valid_service_lines}"
            }
        )
    
    # Generate request hash (for deduplication/audit, but we don't store the note)
    canonical_request = canonicalize_request(request)
    request_hash = sha256_hex(canonical_request.encode('utf-8'))
    
    # Run evidence scoring
    try:
        score, explanations, deficits, risk_flags = score_evidence(request)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "scoring_failed",
                "message": f"Evidence scoring failed: {str(e)}"
            }
        )
    
    # Determine score band
    score_band = get_score_band(score)
    
    # Generate timestamp
    generated_at = datetime.now(timezone.utc).isoformat()
    
    # Build dashboard payload
    result = build_dashboard_payload(
        request=request,
        tenant_id=identity.tenant_id,  # From JWT, not client input
        request_hash=request_hash,
        generated_at_utc=generated_at,
        score=score,
        score_band=score_band,
        explanations=explanations,
        deficits=deficits,
        risk_flags=risk_flags,
        ruleset_version="EDI-v1"
    )
    
    return result
