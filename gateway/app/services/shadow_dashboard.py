"""
Shadow Dashboard Service.

Converts raw evidence scoring output into dashboard-ready presentation format.
Focuses on executive/board-level KPIs and actionable insights.
"""

from typing import List
from gateway.app.models.shadow import (
    ShadowRequest,
    ShadowResult,
    EvidenceSufficiency,
    EvidenceDeficit,
    DenialRisk,
    DenialRiskFlag,
    RevenueEstimate,
    AuditMetadata,
    ScoreExplanation
)


# Revenue estimation heuristics (conservative)
REVENUE_ESTIMATES = {
    "high": {
        "base_per_encounter": 15000,  # Rough average for inpatient
        "high_scrutiny_multiplier": 2.0,
        "denial_probability_high": 0.30,
        "denial_probability_med": 0.15,
        "denial_probability_low": 0.05
    },
    "outpatient": {
        "base_per_encounter": 500,
        "high_scrutiny_multiplier": 1.5,
        "denial_probability_high": 0.20,
        "denial_probability_med": 0.10,
        "denial_probability_low": 0.03
    }
}


def estimate_preventable_revenue_loss(
    encounter_type: str,
    deficits: List[EvidenceDeficit],
    risk_flags: List[DenialRiskFlag]
) -> RevenueEstimate:
    """
    Estimate preventable revenue loss using heuristic rules.
    
    This is NOT a guarantee or prediction - it's a rule-based risk indicator.
    
    Args:
        encounter_type: Type of encounter
        deficits: List of identified deficits
        risk_flags: List of denial risk flags
        
    Returns:
        Revenue estimate with assumptions
    """
    # Select base parameters based on encounter type
    if encounter_type in ["inpatient", "observation", "icu"]:
        params = REVENUE_ESTIMATES["high"]
        base_revenue = params["base_per_encounter"]
    else:
        params = REVENUE_ESTIMATES["outpatient"]
        base_revenue = params["base_per_encounter"]
    
    # Count risk flags by severity
    high_severity = sum(1 for flag in risk_flags if flag.severity == "high")
    med_severity = sum(1 for flag in risk_flags if flag.severity == "med")
    low_severity = sum(1 for flag in risk_flags if flag.severity == "low")
    
    # Apply heuristic denial probabilities
    high_risk_loss = high_severity * base_revenue * params["denial_probability_high"]
    med_risk_loss = med_severity * base_revenue * params["denial_probability_med"]
    low_risk_loss = low_severity * base_revenue * params["denial_probability_low"]
    
    # Conservative (low) estimate
    low_estimate = high_risk_loss + (med_risk_loss * 0.5)
    
    # Optimistic (high) estimate - assume all deficits could cause denials
    high_estimate = high_risk_loss + med_risk_loss + low_risk_loss
    
    # If high-scrutiny diagnosis deficits, multiply
    has_high_scrutiny = any("high-scrutiny" in d.title.lower() for d in deficits)
    if has_high_scrutiny:
        low_estimate *= params["high_scrutiny_multiplier"]
        high_estimate *= params["high_scrutiny_multiplier"]
    
    assumptions = [
        f"Based on {encounter_type} encounter type",
        f"Base revenue per encounter: ${base_revenue:,.0f}",
        f"Risk flags: {high_severity} high, {med_severity} medium, {low_severity} low",
        f"Denial probabilities: high={params['denial_probability_high']:.0%}, med={params['denial_probability_med']:.0%}, low={params['denial_probability_low']:.0%}",
        "These are heuristic estimates, not guarantees"
    ]
    
    if has_high_scrutiny:
        assumptions.append(f"High-scrutiny diagnosis multiplier: {params['high_scrutiny_multiplier']}x")
    
    return RevenueEstimate(
        low=round(low_estimate, 2),
        high=round(high_estimate, 2),
        assumptions=assumptions
    )


def generate_next_best_actions(
    deficits: List[EvidenceDeficit],
    max_actions: int = 3
) -> List[str]:
    """
    Generate prioritized list of recommended actions.
    
    Args:
        deficits: List of evidence deficits
        max_actions: Maximum number of actions to return
        
    Returns:
        List of action prompts
    """
    if not deficits:
        return ["No critical documentation gaps identified"]
    
    # Sort deficits by confidence (highest first)
    sorted_deficits = sorted(deficits, key=lambda d: d.confidence, reverse=True)
    
    # Take top N and format as actions
    actions = []
    for deficit in sorted_deficits[:max_actions]:
        actions.append(deficit.what_to_add)
    
    return actions


def build_dashboard_payload(
    request: ShadowRequest,
    tenant_id: str,
    request_hash: str,
    generated_at_utc: str,
    score: int,
    score_band: str,
    explanations: List[ScoreExplanation],
    deficits: List[EvidenceDeficit],
    risk_flags: List[DenialRiskFlag],
    ruleset_version: str = "EDI-v1"
) -> ShadowResult:
    """
    Build complete dashboard payload from scoring results.
    
    Args:
        request: Original shadow request
        tenant_id: Tenant ID from JWT
        request_hash: SHA-256 hash of canonicalized request
        generated_at_utc: ISO timestamp
        score: Evidence sufficiency score
        score_band: Risk band (green/yellow/red)
        explanations: List of score explanations
        deficits: List of identified deficits
        risk_flags: List of denial risk flags
        ruleset_version: Version of scoring ruleset
        
    Returns:
        Complete ShadowResult payload
    """
    # Estimate revenue loss
    revenue_estimate = estimate_preventable_revenue_loss(
        request.encounter_type,
        deficits,
        risk_flags
    )
    
    # Generate action prompts
    next_actions = generate_next_best_actions(deficits, max_actions=3)
    
    # Build headline
    if revenue_estimate.low == 0 and revenue_estimate.high == 0:
        headline = "Preventable Revenue Loss: $0 (estimated - low risk)"
    else:
        headline = f"Preventable Revenue Loss: ${revenue_estimate.low:,.0f}–${revenue_estimate.high:,.0f} (estimated)"
    
    # Assemble result
    return ShadowResult(
        tenant_id=tenant_id,
        request_hash=request_hash,
        generated_at_utc=generated_at_utc,
        evidence_sufficiency=EvidenceSufficiency(
            score=score,
            band=score_band,
            explain=explanations
        ),
        deficits=deficits,
        denial_risk=DenialRisk(
            flags=risk_flags,
            estimated_preventable_revenue_loss=revenue_estimate
        ),
        audit=AuditMetadata(
            ruleset_version=ruleset_version,
            inputs_redacted=True
        ),
        dashboard_title="Evidence Deficit Intelligence",
        headline=headline,
        next_best_actions=next_actions
    )
