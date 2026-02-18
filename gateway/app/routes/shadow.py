"""
Shadow Mode API Routes for CDIL.

Provides endpoints for retrospective analysis of clinical documentation
to identify evidence deficits and estimate revenue at risk.

This is designed for pilot deployments and does NOT require EMR integration.

Security Model:
- JWT authentication required
- Tenant isolation enforced
- No PHI logging
- Rate limiting applies
"""

import os
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone

from gateway.app.security.auth import Identity, get_current_identity
from gateway.app.services.evidence_scoring import score_note_defensibility
from gateway.app.services.revenue_model import estimate_revenue_risk, calculate_annual_projection
from slowapi import Limiter
from slowapi.util import get_remote_address


router = APIRouter(prefix="/v1/shadow", tags=["shadow-mode"])


# Rate limiter instance (respects ENV=TEST for disabling in tests)
def get_shadow_limiter():
    """Create rate limiter that respects test mode environment variables."""
    disable_limits = (
        os.environ.get("ENV") == "TEST" or
        os.environ.get("DISABLE_RATE_LIMITS") == "1"
    )
    
    if disable_limits:
        import uuid
        return Limiter(key_func=lambda: str(uuid.uuid4()), enabled=False)
    else:
        return Limiter(key_func=get_remote_address)

shadow_limiter = get_shadow_limiter()


# Request/Response Models
class NoteInput(BaseModel):
    """Input model for a single clinical note to analyze."""
    note_text: str = Field(..., description="Clinical note text")
    diagnosis_codes: List[str] = Field(..., description="List of ICD-10 diagnosis codes")
    claim_value: Optional[float] = Field(None, description="Claim value for this note (optional)")
    structured_data: Optional[Dict[str, Any]] = Field(None, description="Optional structured data (labs, vitals)")


class ShadowAnalyzeRequest(BaseModel):
    """Request model for shadow mode analysis."""
    notes: List[NoteInput] = Field(..., description="List of notes to analyze")
    average_claim_value: Optional[float] = Field(20000.0, description="Default claim value if not specified per note")
    denial_probability: Optional[float] = Field(0.08, description="Estimated denial probability for flagged notes")


class ShadowAnalyzeResponse(BaseModel):
    """Response model for shadow mode analysis."""
    summary: Dict[str, Any] = Field(..., description="Executive summary of findings")
    details: List[Dict[str, Any]] = Field(..., description="Detailed analysis per note")
    revenue_impact: Dict[str, Any] = Field(..., description="Revenue impact analysis")
    tenant_id: str = Field(..., description="Tenant ID (from authenticated identity)")
    analyzed_at: str = Field(..., description="Analysis timestamp")


class DashboardResponse(BaseModel):
    """Response model for executive dashboard."""
    percent_defensible: float = Field(..., description="Percentage of notes with strong evidence")
    percent_at_risk: float = Field(..., description="Percentage of notes with evidence gaps")
    estimated_annual_leakage: float = Field(..., description="Estimated annual revenue at risk")
    top_vulnerable_diagnoses: List[Dict[str, Any]] = Field(..., description="Most frequently unsupported diagnoses")
    tenant_id: str = Field(..., description="Tenant ID (from authenticated identity)")
    generated_at: str = Field(..., description="Report generation timestamp")


# In-memory storage for dashboard data (per-tenant)
# In production, this should use a proper database
DASHBOARD_DATA: Dict[str, Dict[str, Any]] = {}


@router.post("/analyze", response_model=ShadowAnalyzeResponse)
async def analyze_notes(
    request: ShadowAnalyzeRequest,
    identity: Identity = Depends(get_current_identity)
):
    """
    Analyze clinical notes for evidence deficits and revenue risk.
    
    This endpoint performs retrospective analysis on a batch of clinical notes
    to identify documentation gaps that could lead to claim denials.
    
    Security:
    - JWT authentication required
    - Tenant ID derived from authenticated identity
    - No PHI stored or logged
    
    Args:
        request: Batch of notes to analyze
        identity: Authenticated user identity (from JWT)
        
    Returns:
        Analysis results with summary, details, and revenue impact
    """
    tenant_id = identity.tenant_id
    
    if not request.notes:
        raise HTTPException(status_code=400, detail="No notes provided for analysis")
    
    # Analyze each note
    scored_notes = []
    details = []
    
    for idx, note_input in enumerate(request.notes):
        # Score the note
        score_result = score_note_defensibility(
            note_text=note_input.note_text,
            diagnosis_codes=note_input.diagnosis_codes,
            structured_data=note_input.structured_data
        )
        
        # Determine claim value for this note
        claim_value = note_input.claim_value or request.average_claim_value
        
        # Build detailed result
        detail = {
            "note_index": idx,
            "overall_score": score_result["overall_score"],
            "summary": score_result["summary"],
            "diagnoses": score_result["diagnoses"],
            "flags": score_result["flags"],
            "claim_value": claim_value
        }
        
        details.append(detail)
        scored_notes.append(score_result)
    
    # Calculate revenue impact
    revenue_impact = estimate_revenue_risk(
        scored_notes=scored_notes,
        average_claim_value=request.average_claim_value,
        denial_probability=request.denial_probability
    )
    
    # Build summary
    summary = {
        "notes_analyzed": len(request.notes),
        "notes_flagged": revenue_impact["notes_flagged"],
        "percent_flagged": revenue_impact["percent_flagged"],
        "estimated_revenue_at_risk": revenue_impact["estimated_revenue_at_risk"]
    }
    
    # Update dashboard data for this tenant
    DASHBOARD_DATA[tenant_id] = {
        "last_analysis": datetime.now(timezone.utc).isoformat(),
        "notes_analyzed": len(request.notes),
        "notes_flagged": revenue_impact["notes_flagged"],
        "percent_flagged": revenue_impact["percent_flagged"],
        "revenue_at_risk": revenue_impact["estimated_revenue_at_risk"],
        "high_risk_diagnoses": revenue_impact["high_risk_diagnoses"],
        "scored_notes": scored_notes  # Store for dashboard
    }
    
    return ShadowAnalyzeResponse(
        summary=summary,
        details=details,
        revenue_impact=revenue_impact,
        tenant_id=tenant_id,
        analyzed_at=datetime.now(timezone.utc).isoformat()
    )


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    identity: Identity = Depends(get_current_identity),
    annual_note_volume: Optional[int] = None
):
    """
    Get executive dashboard with defensibility metrics and revenue impact.
    
    This endpoint provides the "scary screen" for executives, showing:
    - Percent of documentation that is defensible
    - Percent at risk of denial
    - Estimated annual revenue leakage
    - Top vulnerable diagnosis codes
    
    Security:
    - JWT authentication required
    - Tenant isolation enforced
    - Only shows data for authenticated tenant
    
    Args:
        identity: Authenticated user identity (from JWT)
        annual_note_volume: Optional annual note volume for projection
        
    Returns:
        Executive dashboard metrics
    """
    tenant_id = identity.tenant_id
    
    # Check if this tenant has analysis data
    if tenant_id not in DASHBOARD_DATA:
        raise HTTPException(
            status_code=404,
            detail="No analysis data available. Run /v1/shadow/analyze first."
        )
    
    data = DASHBOARD_DATA[tenant_id]
    
    # Calculate defensibility metrics
    notes_analyzed = data.get("notes_analyzed", 0)
    notes_flagged = data.get("notes_flagged", 0)
    
    if notes_analyzed == 0:
        percent_at_risk = 0.0
        percent_defensible = 100.0
    else:
        percent_at_risk = (notes_flagged / notes_analyzed) * 100
        percent_defensible = 100.0 - percent_at_risk
    
    # Get revenue at risk
    revenue_at_risk = data.get("revenue_at_risk", 0.0)
    
    # If annual volume provided, calculate annual projection
    if annual_note_volume and notes_analyzed > 0:
        projection = calculate_annual_projection(
            current_risk=revenue_at_risk,
            notes_in_sample=notes_analyzed,
            annual_note_volume=annual_note_volume
        )
        estimated_annual_leakage = projection["projected_annual_risk"]
    else:
        # Use current sample as estimate
        estimated_annual_leakage = revenue_at_risk
    
    # Get top vulnerable diagnoses
    top_vulnerable = data.get("high_risk_diagnoses", [])[:5]  # Top 5 for dashboard
    
    return DashboardResponse(
        percent_defensible=round(percent_defensible, 1),
        percent_at_risk=round(percent_at_risk, 1),
        estimated_annual_leakage=round(estimated_annual_leakage, 2),
        top_vulnerable_diagnoses=top_vulnerable,
        tenant_id=tenant_id,
        generated_at=datetime.now(timezone.utc).isoformat()
    )
