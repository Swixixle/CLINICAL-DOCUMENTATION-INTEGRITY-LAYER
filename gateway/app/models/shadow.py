"""
Shadow Mode models for Evidence Deficit Intelligence.

These models define request/response schemas for the read-only Shadow Mode
evidence deficit analysis endpoint. No PHI is stored - only hashes and scores.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class LabResult(BaseModel):
    """Laboratory test result."""
    name: str = Field(..., description="Lab test name (e.g., 'albumin', 'wbc')")
    value: float = Field(..., description="Numeric result value")
    unit: str = Field(..., description="Unit of measurement (e.g., 'g/dL', 'K/uL')")
    collected_at: str = Field(..., description="ISO 8601 timestamp of collection")


class VitalSign(BaseModel):
    """Vital sign measurement."""
    name: str = Field(..., description="Vital name (e.g., 'bp', 'temp', 'hr')")
    value: str = Field(..., description="Vital value (may be string like '120/80')")
    taken_at: str = Field(..., description="ISO 8601 timestamp of measurement")


class ShadowRequest(BaseModel):
    """
    Request for Shadow Mode evidence deficit analysis.
    
    Shadow Mode is read-only and does not integrate with Epic or other EHRs.
    It analyzes clinical note + structured context to identify documentation gaps.
    
    Privacy: note_text is hashed but never stored in plaintext.
    Security: tenant_id is derived from JWT, not from request.
    """
    note_text: str = Field(..., description="Clinical note text (will be hashed, never stored)")
    encounter_type: str = Field(..., description="Type: inpatient|observation|outpatient|ed")
    service_line: str = Field(..., description="Service: medicine|surgery|icu|other")
    diagnoses: List[str] = Field(default_factory=list, description="List of diagnosis codes or descriptions")
    procedures: List[str] = Field(default_factory=list, description="List of procedure codes or descriptions")
    labs: List[LabResult] = Field(default_factory=list, description="Laboratory results")
    vitals: List[VitalSign] = Field(default_factory=list, description="Vital signs")
    problem_list: List[str] = Field(default_factory=list, description="Active problem list")
    meds: List[str] = Field(default_factory=list, description="Current medications")
    discharge_disposition: Optional[str] = Field(default=None, description="Discharge disposition if applicable")


class ScoreExplanation(BaseModel):
    """Explanation for a score adjustment."""
    rule_id: str = Field(..., description="Unique rule identifier for traceability")
    impact: int = Field(..., description="Score impact (negative = penalty, positive = bonus)")
    reason: str = Field(..., description="Human-readable explanation")


class EvidenceSufficiency(BaseModel):
    """Evidence sufficiency scoring results."""
    score: int = Field(..., ge=0, le=100, description="Evidence sufficiency score (0-100)")
    band: str = Field(..., description="Risk band: green|yellow|red")
    explain: List[ScoreExplanation] = Field(..., description="List of scoring rule applications")


class EvidenceReference(BaseModel):
    """Reference to supporting or missing evidence."""
    type: str = Field(..., description="Evidence type: lab|vital|diagnosis|problem|med|note_text")
    key: str = Field(..., description="Evidence key (e.g., lab name, diagnosis code)")
    value: Any = Field(default=None, description="Evidence value if present")


class EvidenceDeficit(BaseModel):
    """Identified documentation or evidence gap."""
    id: str = Field(..., description="Unique deficit identifier (e.g., 'DEF-001')")
    title: str = Field(..., description="Brief deficit description")
    category: str = Field(..., description="Category: documentation|coding|clinical_inconsistency")
    why_payer_denies: str = Field(..., description="Payer perspective on why this is vulnerable")
    what_to_add: str = Field(..., description="Provider-facing guidance on what to document")
    evidence_refs: List[EvidenceReference] = Field(default_factory=list, description="Referenced evidence")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in this finding (0-1)")


class DenialRiskFlag(BaseModel):
    """Denial risk indicator."""
    id: str = Field(..., description="Unique risk flag identifier (e.g., 'DR-001')")
    severity: str = Field(..., description="Risk severity: high|med|low")
    rationale: str = Field(..., description="Why this is a denial risk")
    rule_id: str = Field(..., description="Rule that triggered this flag")


class RevenueEstimate(BaseModel):
    """Estimated preventable revenue loss range."""
    low: float = Field(..., ge=0, description="Conservative estimate")
    high: float = Field(..., ge=0, description="Optimistic estimate")
    assumptions: List[str] = Field(..., description="Assumptions used in estimation")


class DenialRisk(BaseModel):
    """Denial risk assessment."""
    flags: List[DenialRiskFlag] = Field(..., description="List of risk flags")
    estimated_preventable_revenue_loss: RevenueEstimate = Field(..., description="Revenue at risk")


class AuditMetadata(BaseModel):
    """Audit trail metadata."""
    ruleset_version: str = Field(..., description="Version of ruleset used")
    inputs_redacted: bool = Field(default=True, description="Whether inputs were redacted from storage")


class ShadowResult(BaseModel):
    """
    Shadow Mode evidence deficit analysis result.
    
    This is the complete output from the evidence scoring engine.
    Includes dashboard-ready fields for board/CFO presentation.
    """
    tenant_id: str = Field(..., description="Tenant ID from JWT authentication")
    request_hash: str = Field(..., description="SHA-256 hash of canonicalized request")
    generated_at_utc: str = Field(..., description="ISO 8601 UTC timestamp")
    
    # Core analysis results
    evidence_sufficiency: EvidenceSufficiency = Field(..., description="Evidence sufficiency scoring")
    deficits: List[EvidenceDeficit] = Field(..., description="Identified documentation deficits")
    denial_risk: DenialRisk = Field(..., description="Denial risk assessment")
    
    # Audit trail
    audit: AuditMetadata = Field(..., description="Audit metadata")
    
    # Dashboard presentation fields
    dashboard_title: str = Field(default="Evidence Deficit Intelligence", description="Dashboard title")
    headline: str = Field(..., description="Key metric headline for executives")
    next_best_actions: List[str] = Field(..., description="Top 3 recommended actions")
