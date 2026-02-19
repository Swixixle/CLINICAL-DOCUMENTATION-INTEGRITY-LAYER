"""
Deterministic Denial Shield Scoring Engine for CDIL Shadow Mode.

This module implements MEAT-based (Monitor/Evaluate/Assess/Treat) scoring for
clinical documentation to identify high-value diagnoses and assess denial risk.

All scoring is deterministic, explainable, and based on keyword matching.
No LLM calls, no ambiguous behavior.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from gateway.app.models.shadow import (
    ShadowRequest,
    EvidenceSufficiency,
    ScoreExplanation,
    EvidenceDeficit,
    DenialRisk,
    DenialRiskFlag,
    RevenueEstimate,
    EvidenceReference,
    EncounterType,
    RiskBand,
)

# ============================================================================
# Rule IDs (canonical, stable identifiers)
# ============================================================================

# Diagnosis presence
RULE_DX_DIABETES_PRESENT = "DX_DIABETES_PRESENT"
RULE_DX_HTN_PRESENT = "DX_HTN_PRESENT"
RULE_DX_CHF_PRESENT = "DX_CHF_PRESENT"

# Diabetes MEAT
RULE_DIAB_MONITOR_MISSING = "DIAB_MONITOR_MISSING"
RULE_DIAB_EVAL_MISSING = "DIAB_EVAL_MISSING"
RULE_DIAB_ASSESS_MISSING = "DIAB_ASSESS_MISSING"
RULE_DIAB_TREAT_MISSING = "DIAB_TREAT_MISSING"

# Hypertension MEAT
RULE_HTN_MONITOR_MISSING = "HTN_MONITOR_MISSING"
RULE_HTN_EVAL_MISSING = "HTN_EVAL_MISSING"
RULE_HTN_ASSESS_MISSING = "HTN_ASSESS_MISSING"
RULE_HTN_TREAT_MISSING = "HTN_TREAT_MISSING"

# CHF MEAT
RULE_CHF_MONITOR_MISSING = "CHF_MONITOR_MISSING"
RULE_CHF_EVAL_MISSING = "CHF_EVAL_MISSING"
RULE_CHF_ASSESS_MISSING = "CHF_ASSESS_MISSING"
RULE_CHF_TREAT_MISSING = "CHF_TREAT_MISSING"

# General
RULE_NOTE_TOO_SHORT = "NOTE_TOO_SHORT"
RULE_PLAN_VAGUE = "PLAN_VAGUE"
RULE_NO_DIAGNOSES_PROVIDED = "NO_DIAGNOSES_PROVIDED"


# ============================================================================
# MEAT Anchor Keywords (case-insensitive)
# ============================================================================

# Diabetes anchors
DIABETES_KEYWORDS = ["diabetes", "dm2", "t2dm", "diabetic", "e11.9", "e10", "e11"]
DIABETES_MONITOR = [
    "glucose",
    "blood sugar",
    "fingerstick",
    "fsbs",
    "a1c",
    "hba1c",
    "cgm",
]
DIABETES_EVALUATE = [
    "controlled",
    "uncontrolled",
    "at goal",
    "above goal",
    "improving",
    "worsening",
]
DIABETES_ASSESS = ["diabetes", "dm", "controlled", "uncontrolled", "a1c"]
DIABETES_TREAT = [
    "metformin",
    "insulin",
    "glp-1",
    "semaglutide",
    "ozempic",
    "tirzepatide",
    "mounjaro",
    "dose",
    "increase",
    "decrease",
    "continue",
    # Note: Generic action words like "increase", "decrease", "continue" may match
    # unintended contexts (e.g., "symptoms increased"). This is a known limitation
    # of simple keyword matching. Future enhancements should use context-aware matching.
]

# Hypertension anchors
HTN_KEYWORDS = ["hypertension", "htn", "i10", "elevated bp", "high blood pressure"]
HTN_MONITOR = ["bp", "blood pressure", "home bp", "ambulatory", "log"]
HTN_EVALUATE = [
    "controlled",
    "uncontrolled",
    "at goal",
    "above goal",
    "improving",
    "worsening",
]
HTN_ASSESS = ["htn", "hypertension", "bp", "blood pressure"]
HTN_TREAT = [
    "lisinopril",
    "amlodipine",
    "losartan",
    "hctz",
    "hydrochlorothiazide",
    "metoprolol",
    "carvedilol",
    "start",
    "continue",
    "increase",
    "decrease",
    # Note: Generic action words may cause false positives. V2 should implement
    # context-aware matching or require co-occurrence with medication names.
]

# CHF anchors
CHF_KEYWORDS = [
    "heart failure",
    "chf",
    "hfref",
    "hfpef",
    "i50",
    "congestive heart failure",
]
CHF_MONITOR = [
    "weight",
    "daily weight",
    "edema",
    "swelling",
    "i/o",
    "oxygen",
    "sob",
    "dyspnea",
]
CHF_EVALUATE = [
    "euvolemic",
    "volume overloaded",
    "improving",
    "worsening",
    "stable",
    "exacerbation",
]
CHF_ASSESS = ["hfref", "hfpef", "ef", "ejection fraction", "nyha"]
CHF_TREAT = [
    "furosemide",
    "lasix",
    "bumetanide",
    "torsemide",
    "entresto",
    "sacubitril",
    "valsartan",
    "beta blocker",
    "spironolactone",
    "sglt2",
    "dapagliflozin",
    "empagliflozin",
    "diuretic",
    "dose",
    "increase",
    "decrease",
    # Note: "dose", "increase", "decrease" are generic and may match unrelated contexts.
    # Future versions should use more specific patterns or context windows.
]

# Vague plan indicators
VAGUE_PLAN_PHRASES = [
    "follow up",
    "f/u",
    "continue current",
    "monitor",
    "stable",
    "as above",
    "no changes",
]


# ============================================================================
# Helper Functions
# ============================================================================


def contains_any_keyword(text: str, keywords: List[str]) -> bool:
    """Check if text contains any of the keywords (case-insensitive)."""
    text_lower = text.lower()
    for keyword in keywords:
        # Use word boundary matching where applicable
        pattern = r"\b" + re.escape(keyword.lower())
        if re.search(pattern, text_lower):
            return True
    return False


def detect_diagnosis(note_text: str, diagnoses: List[str], keywords: List[str]) -> bool:
    """
    Check if diagnosis is present in note or diagnosis list.

    Args:
        note_text: Clinical note text
        diagnoses: List of diagnosis codes/descriptions
        keywords: Keywords to search for

    Returns:
        True if diagnosis is detected
    """
    # Check in diagnoses list
    for dx in diagnoses:
        if contains_any_keyword(dx, keywords):
            return True

    # Check in note text
    if contains_any_keyword(note_text, keywords):
        return True

    return False


def check_vague_plan(note_text: str) -> bool:
    """
    Check if plan appears vague.

    Returns True if vague plan indicators are present without specific actions nearby.
    """
    text_lower = note_text.lower()

    for phrase in VAGUE_PLAN_PHRASES:
        # Look for vague phrase
        pattern = re.escape(phrase.lower())
        match = re.search(pattern, text_lower)

        if match:
            # Check if there are specific actions within ±80 chars
            start = max(0, match.start() - 80)
            end = min(len(text_lower), match.end() + 80)
            context = text_lower[start:end]

            # Look for action words
            action_words = [
                "start",
                "stop",
                "increase",
                "decrease",
                "add",
                "discontinue",
                "adjust",
                "change",
            ]
            has_action = any(word in context for word in action_words)

            if not has_action:
                return True

    return False


# ============================================================================
# Denial Shield Scorer
# ============================================================================


class DenialShieldScorer:
    """
    Deterministic MEAT-based scorer for clinical documentation.

    Scores documentation quality and denial risk based on:
    - High-value diagnosis detection (diabetes, HTN, CHF)
    - MEAT anchor presence (Monitor/Evaluate/Assess/Treat)
    - General documentation quality (length, plan specificity)

    Risk score: 0-100 where higher = higher denial risk
    Sufficiency score: inverse of risk score (100 - risk)
    """

    def score(
        self, request: ShadowRequest
    ) -> Tuple[int, EvidenceSufficiency, List[EvidenceDeficit], DenialRisk]:
        """
        Score a clinical documentation request.

        Args:
            request: Shadow mode request with clinical context

        Returns:
            Tuple of (risk_score, sufficiency, deficits, denial_risk)
        """
        risk_score = 0
        explanations: List[ScoreExplanation] = []
        deficits: List[EvidenceDeficit] = []

        note_text = request.note_text
        diagnoses = request.diagnoses

        # Rule 1: Check note length
        if len(note_text) < 400:
            risk_score += 15
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_NOTE_TOO_SHORT,
                    impact=15,
                    reason="Note text is too short (< 400 characters) to support medical necessity",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-NOTE-001",
                    title="Insufficient note length",
                    category="documentation",
                    why_payer_denies="Minimal documentation cannot establish medical necessity",
                    what_to_add="Expand clinical note with detailed HPI, assessment, and plan",
                    evidence_refs=[
                        EvidenceReference(
                            type="note_text", key="length", value=len(note_text)
                        )
                    ],
                    confidence=0.95,
                )
            )

        # Rule 2: Check for diagnoses
        if not diagnoses and not contains_any_keyword(
            note_text, DIABETES_KEYWORDS + HTN_KEYWORDS + CHF_KEYWORDS
        ):
            risk_score += 20
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_NO_DIAGNOSES_PROVIDED,
                    impact=20,
                    reason="No diagnoses provided and none detected in note",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-DX-001",
                    title="No diagnoses documented",
                    category="documentation",
                    why_payer_denies="Claims require documented diagnoses to establish medical necessity",
                    what_to_add="Add diagnosis codes or diagnosis descriptions to note",
                    evidence_refs=[],
                    confidence=0.99,
                )
            )

        # Rule 3: Check for vague plan
        if check_vague_plan(note_text):
            risk_score += 10
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_PLAN_VAGUE,
                    impact=10,
                    reason="Plan contains vague language without specific actions",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-PLAN-001",
                    title="Vague treatment plan",
                    category="documentation",
                    why_payer_denies="Non-specific plans fail to demonstrate active clinical management",
                    what_to_add="Add specific medication changes, orders, or interventions to plan",
                    evidence_refs=[],
                    confidence=0.75,
                )
            )

        # Rule 4-6: Check MEAT for high-value diagnoses

        # Diabetes
        if detect_diagnosis(note_text, diagnoses, DIABETES_KEYWORDS):
            risk_score, explanations, deficits = self._check_diabetes_meat(
                note_text, risk_score, explanations, deficits
            )

        # Hypertension
        if detect_diagnosis(note_text, diagnoses, HTN_KEYWORDS):
            risk_score, explanations, deficits = self._check_htn_meat(
                note_text, risk_score, explanations, deficits
            )

        # CHF
        if detect_diagnosis(note_text, diagnoses, CHF_KEYWORDS):
            risk_score, explanations, deficits = self._check_chf_meat(
                note_text, risk_score, explanations, deficits
            )

        # Cap risk score at 100
        risk_score = min(100, risk_score)

        # Convert to sufficiency score (inverse)
        sufficiency_score = max(0, 100 - risk_score)

        # Determine band
        if risk_score <= 30:
            band = RiskBand.LOW
        elif risk_score <= 60:
            band = RiskBand.MODERATE
        elif risk_score <= 80:
            band = RiskBand.HIGH
        else:
            band = RiskBand.CRITICAL

        # Create sufficiency object
        sufficiency = EvidenceSufficiency(
            score=sufficiency_score, band=band.value, explain=explanations
        )

        # Get top 3 reasons by impact
        sorted_explanations = sorted(explanations, key=lambda x: x.impact, reverse=True)
        primary_reasons = [exp.reason for exp in sorted_explanations[:3]]

        # Create denial risk object
        denial_risk = DenialRisk(
            score=risk_score,
            band=band,
            primary_reasons=primary_reasons,
            flags=[],  # Will be populated by caller if needed
            estimated_preventable_revenue_loss=RevenueEstimate(
                low=0.0,
                high=0.0,
                assumptions=["To be calculated by revenue estimation logic"],
            ),
        )

        return risk_score, sufficiency, deficits, denial_risk

    def _check_diabetes_meat(
        self,
        note_text: str,
        risk_score: int,
        explanations: List[ScoreExplanation],
        deficits: List[EvidenceDeficit],
    ) -> Tuple[int, List[ScoreExplanation], List[EvidenceDeficit]]:
        """Check MEAT anchors for diabetes."""

        # Monitor
        if not contains_any_keyword(note_text, DIABETES_MONITOR):
            risk_score += 25
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_DIAB_MONITOR_MISSING,
                    impact=25,
                    reason="Diabetes documented but no monitoring data (glucose, A1C, CGM)",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-DIAB-M",
                    title="Diabetes: Missing Monitor",
                    category="monitor",
                    why_payer_denies="Diabetes diagnosis without glucose monitoring fails MEAT criteria",
                    what_to_add="Add A1C value or state CGM/fingerstick monitoring plan (frequency + target range).",
                    evidence_refs=[],
                    confidence=0.90,
                    condition="diabetes",
                    missing=["A1C", "glucose monitoring", "fingerstick"],
                    fix="Add A1C value or state CGM/fingerstick monitoring plan (frequency + target range).",
                )
            )

        # Evaluate
        if not contains_any_keyword(note_text, DIABETES_EVALUATE):
            risk_score += 15
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_DIAB_EVAL_MISSING,
                    impact=15,
                    reason="Diabetes documented but no evaluation of control status",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-DIAB-E",
                    title="Diabetes: Missing Evaluate",
                    category="evaluate",
                    why_payer_denies="No evaluation of diabetes control undermines medical necessity",
                    what_to_add="Document if diabetes is controlled, uncontrolled, at goal, or worsening.",
                    evidence_refs=[],
                    confidence=0.85,
                    condition="diabetes",
                    missing=["control status", "goal assessment"],
                    fix="Document if diabetes is controlled, uncontrolled, at goal, or worsening.",
                )
            )

        # Assess
        if not contains_any_keyword(note_text, DIABETES_ASSESS):
            risk_score += 15
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_DIAB_ASSESS_MISSING,
                    impact=15,
                    reason="Diabetes documented but no assessment in note",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-DIAB-A",
                    title="Diabetes: Missing Assess",
                    category="assess",
                    why_payer_denies="Assessment section must explicitly mention diabetes with status",
                    what_to_add="Add 'Diabetes: [controlled/uncontrolled]' or A1C interpretation to assessment.",
                    evidence_refs=[],
                    confidence=0.80,
                    condition="diabetes",
                    missing=["assessment mention", "clinical status"],
                    fix="Add 'Diabetes: [controlled/uncontrolled]' or A1C interpretation to assessment.",
                )
            )

        # Treat
        if not contains_any_keyword(note_text, DIABETES_TREAT):
            risk_score += 25
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_DIAB_TREAT_MISSING,
                    impact=25,
                    reason="Diabetes documented but no treatment plan",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-DIAB-T",
                    title="Diabetes: Missing Treat",
                    category="treat",
                    why_payer_denies="Diabetes without documented treatment fails to justify medical necessity",
                    what_to_add="Document diabetes medications (metformin, insulin, etc.) with dose/frequency or plan.",
                    evidence_refs=[],
                    confidence=0.95,
                    condition="diabetes",
                    missing=["medication plan", "dose adjustment"],
                    fix="Document diabetes medications (metformin, insulin, etc.) with dose/frequency or plan.",
                )
            )

        return risk_score, explanations, deficits

    def _check_htn_meat(
        self,
        note_text: str,
        risk_score: int,
        explanations: List[ScoreExplanation],
        deficits: List[EvidenceDeficit],
    ) -> Tuple[int, List[ScoreExplanation], List[EvidenceDeficit]]:
        """Check MEAT anchors for hypertension."""

        # Monitor
        if not contains_any_keyword(note_text, HTN_MONITOR):
            risk_score += 25
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_HTN_MONITOR_MISSING,
                    impact=25,
                    reason="Hypertension documented but no BP monitoring data",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-HTN-M",
                    title="Hypertension: Missing Monitor",
                    category="monitor",
                    why_payer_denies="HTN diagnosis without blood pressure values fails MEAT criteria",
                    what_to_add="Add BP reading or reference to home BP log/ambulatory monitoring.",
                    evidence_refs=[],
                    confidence=0.92,
                    condition="hypertension",
                    missing=["blood pressure values", "BP monitoring"],
                    fix="Add BP reading or reference to home BP log/ambulatory monitoring.",
                )
            )

        # Evaluate
        if not contains_any_keyword(note_text, HTN_EVALUATE):
            risk_score += 15
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_HTN_EVAL_MISSING,
                    impact=15,
                    reason="Hypertension documented but no evaluation of control status",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-HTN-E",
                    title="Hypertension: Missing Evaluate",
                    category="evaluate",
                    why_payer_denies="No evaluation of HTN control undermines medical necessity",
                    what_to_add="Document if HTN is controlled, uncontrolled, at goal, or improving.",
                    evidence_refs=[],
                    confidence=0.85,
                    condition="hypertension",
                    missing=["control status", "goal assessment"],
                    fix="Document if HTN is controlled, uncontrolled, at goal, or improving.",
                )
            )

        # Assess
        if not contains_any_keyword(note_text, HTN_ASSESS):
            risk_score += 15
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_HTN_ASSESS_MISSING,
                    impact=15,
                    reason="Hypertension documented but no assessment in note",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-HTN-A",
                    title="Hypertension: Missing Assess",
                    category="assess",
                    why_payer_denies="Assessment section must explicitly mention HTN with BP status",
                    what_to_add="Add 'HTN: [controlled/uncontrolled]' or BP interpretation to assessment.",
                    evidence_refs=[],
                    confidence=0.80,
                    condition="hypertension",
                    missing=["assessment mention", "BP status"],
                    fix="Add 'HTN: [controlled/uncontrolled]' or BP interpretation to assessment.",
                )
            )

        # Treat
        if not contains_any_keyword(note_text, HTN_TREAT):
            risk_score += 25
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_HTN_TREAT_MISSING,
                    impact=25,
                    reason="Hypertension documented but no treatment plan",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-HTN-T",
                    title="Hypertension: Missing Treat",
                    category="treat",
                    why_payer_denies="HTN without documented treatment fails to justify medical necessity",
                    what_to_add="Document HTN medications (lisinopril, amlodipine, etc.) with dose or plan.",
                    evidence_refs=[],
                    confidence=0.93,
                    condition="hypertension",
                    missing=["medication plan", "dose adjustment"],
                    fix="Document HTN medications (lisinopril, amlodipine, etc.) with dose or plan.",
                )
            )

        return risk_score, explanations, deficits

    def _check_chf_meat(
        self,
        note_text: str,
        risk_score: int,
        explanations: List[ScoreExplanation],
        deficits: List[EvidenceDeficit],
    ) -> Tuple[int, List[ScoreExplanation], List[EvidenceDeficit]]:
        """Check MEAT anchors for CHF."""

        # Monitor
        if not contains_any_keyword(note_text, CHF_MONITOR):
            risk_score += 25
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_CHF_MONITOR_MISSING,
                    impact=25,
                    reason="CHF documented but no monitoring data (weight, edema, I/O)",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-CHF-M",
                    title="CHF: Missing Monitor",
                    category="monitor",
                    why_payer_denies="CHF diagnosis without volume status monitoring fails MEAT criteria",
                    what_to_add="Add daily weight, edema status, I/O balance, or dyspnea assessment.",
                    evidence_refs=[],
                    confidence=0.91,
                    condition="chf",
                    missing=["weight monitoring", "edema assessment", "volume status"],
                    fix="Add daily weight, edema status, I/O balance, or dyspnea assessment.",
                )
            )

        # Evaluate
        if not contains_any_keyword(note_text, CHF_EVALUATE):
            risk_score += 15
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_CHF_EVAL_MISSING,
                    impact=15,
                    reason="CHF documented but no evaluation of volume status",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-CHF-E",
                    title="CHF: Missing Evaluate",
                    category="evaluate",
                    why_payer_denies="No evaluation of CHF status undermines medical necessity",
                    what_to_add="Document if patient is euvolemic, overloaded, stable, or exacerbating.",
                    evidence_refs=[],
                    confidence=0.87,
                    condition="chf",
                    missing=["volume status", "clinical trajectory"],
                    fix="Document if patient is euvolemic, overloaded, stable, or exacerbating.",
                )
            )

        # Assess
        if not contains_any_keyword(note_text, CHF_ASSESS):
            risk_score += 15
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_CHF_ASSESS_MISSING,
                    impact=15,
                    reason="CHF documented but no assessment with phenotype",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-CHF-A",
                    title="CHF: Missing Assess",
                    category="assess",
                    why_payer_denies="Assessment must specify HF phenotype (HFrEF/HFpEF) or EF",
                    what_to_add="Add 'HFrEF with EF 30%' or 'HFpEF' or NYHA class to assessment.",
                    evidence_refs=[],
                    confidence=0.82,
                    condition="chf",
                    missing=["HF phenotype", "ejection fraction", "NYHA class"],
                    fix="Add 'HFrEF with EF 30%' or 'HFpEF' or NYHA class to assessment.",
                )
            )

        # Treat
        if not contains_any_keyword(note_text, CHF_TREAT):
            risk_score += 25
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_CHF_TREAT_MISSING,
                    impact=25,
                    reason="CHF documented but no GDMT or diuretic plan",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-CHF-T",
                    title="CHF: Missing Treat",
                    category="treat",
                    why_payer_denies="CHF without documented treatment fails to justify medical necessity",
                    what_to_add="Document HF medications (furosemide, entresto, beta blocker, SGLT2i) with dose.",
                    evidence_refs=[],
                    confidence=0.94,
                    condition="chf",
                    missing=["GDMT", "diuretic plan", "medication regimen"],
                    fix="Document HF medications (furosemide, entresto, beta blocker, SGLT2i) with dose.",
                )
            )

        return risk_score, explanations, deficits
