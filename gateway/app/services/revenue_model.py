"""
Revenue Impact Estimation Service for CDIL Shadow Mode.

This service provides transparent, simple calculations to estimate revenue at risk
from documentation deficiencies.

Design Principles:
- Simple, transparent math
- Adjustable assumptions
- CFO-readable outputs
- Conservative estimates
"""

from typing import Dict, List, Any


def estimate_revenue_risk(
    scored_notes: List[Dict[str, Any]],
    average_claim_value: float = 20000.0,
    denial_probability: float = 0.08,
) -> Dict[str, Any]:
    """
    Estimate revenue at risk from documentation deficiencies.

    Uses simple, transparent math to calculate potential revenue loss from
    notes that have evidence gaps. This is designed to be CFO-readable and
    conservative in its estimates.

    Formula:
        Revenue at Risk = (Flagged Notes) × (Avg Claim Value) × (Denial Probability)

    Args:
        scored_notes: List of notes with defensibility scores
        average_claim_value: Average dollar value per claim (default: $20,000)
        denial_probability: Probability of denial for flagged notes (default: 0.08 = 8%)

    Returns:
        Dict containing:
            - notes_flagged: Number of notes with evidence gaps
            - notes_analyzed: Total number of notes analyzed
            - percent_flagged: Percentage of notes flagged
            - estimated_revenue_at_risk: Dollar amount at risk
            - high_risk_diagnoses: List of frequently unsupported diagnosis codes
            - assumptions: Parameters used in calculation
    """
    if not scored_notes:
        return {
            "notes_flagged": 0,
            "notes_analyzed": 0,
            "percent_flagged": 0.0,
            "estimated_revenue_at_risk": 0.0,
            "high_risk_diagnoses": [],
            "assumptions": {
                "average_claim_value": average_claim_value,
                "denial_probability": denial_probability,
            },
        }

    notes_analyzed = len(scored_notes)
    notes_flagged = 0
    high_risk_diagnoses_map = {}

    # Define threshold for flagging (scores below 70 are concerning)
    FLAG_THRESHOLD = 70

    for note in scored_notes:
        # Check if note has concerning evidence gaps
        overall_score = note.get("overall_score", 100)

        if overall_score < FLAG_THRESHOLD:
            notes_flagged += 1

            # Track which diagnoses are frequently unsupported
            for diagnosis in note.get("diagnoses", []):
                if not diagnosis.get("evidence_present", True):
                    code = diagnosis.get("code")
                    if code:
                        if code not in high_risk_diagnoses_map:
                            high_risk_diagnoses_map[code] = {
                                "code": code,
                                "description": diagnosis.get("description", "Unknown"),
                                "count": 0,
                            }
                        high_risk_diagnoses_map[code]["count"] += 1

    # Calculate percentages and revenue risk
    percent_flagged = (notes_flagged / notes_analyzed) if notes_analyzed > 0 else 0.0

    # Conservative revenue risk calculation
    estimated_revenue_at_risk = notes_flagged * average_claim_value * denial_probability

    # Sort high-risk diagnoses by frequency
    high_risk_diagnoses = sorted(
        high_risk_diagnoses_map.values(), key=lambda x: x["count"], reverse=True
    )[
        :10
    ]  # Top 10

    # Calculate percent missing support for each diagnosis
    for diagnosis in high_risk_diagnoses:
        diagnosis["percent_missing_support"] = int(
            (diagnosis["count"] / notes_analyzed) * 100
        )

    return {
        "notes_flagged": notes_flagged,
        "notes_analyzed": notes_analyzed,
        "percent_flagged": round(percent_flagged * 100, 1),
        "estimated_revenue_at_risk": round(estimated_revenue_at_risk, 2),
        "high_risk_diagnoses": high_risk_diagnoses,
        "assumptions": {
            "average_claim_value": average_claim_value,
            "denial_probability": denial_probability,
            "flag_threshold": FLAG_THRESHOLD,
        },
    }


def calculate_annual_projection(
    current_risk: float, notes_in_sample: int, annual_note_volume: int
) -> Dict[str, Any]:
    """
    Project annual revenue impact based on sample analysis.

    Extrapolates from a sample of notes to estimate annual revenue at risk.

    Args:
        current_risk: Revenue at risk in current sample
        notes_in_sample: Number of notes in sample
        annual_note_volume: Expected annual note volume

    Returns:
        Dict containing:
            - projected_annual_risk: Estimated annual revenue at risk
            - projection_method: How projection was calculated
            - confidence_note: Caveat about projection accuracy
    """
    if notes_in_sample == 0:
        return {
            "projected_annual_risk": 0.0,
            "projection_method": "insufficient_data",
            "confidence_note": "Insufficient sample size for projection",
        }

    # Simple linear extrapolation
    risk_per_note = current_risk / notes_in_sample
    projected_annual_risk = risk_per_note * annual_note_volume

    return {
        "projected_annual_risk": round(projected_annual_risk, 2),
        "projection_method": "linear_extrapolation",
        "confidence_note": f"Based on {notes_in_sample} note sample; actual results may vary",
    }
