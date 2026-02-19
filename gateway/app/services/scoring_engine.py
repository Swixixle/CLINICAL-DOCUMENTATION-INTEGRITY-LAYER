"""
Deterministic Denial Shield Scoring Engine for CDIL Shadow Mode.

This module implements MEAT-based (Monitor/Evaluate/Assess/Treat) scoring for
clinical documentation to identify high-value diagnoses and assess denial risk.

All scoring is deterministic, explainable, and based on keyword matching.
No LLM calls, no ambiguous behavior.
"""

import re
from typing import List, Tuple

from gateway.app.models.shadow import (
    ShadowRequest,
    EvidenceSufficiency,
    ScoreExplanation,
    EvidenceDeficit,
    DenialRisk,
    RevenueEstimate,
    EvidenceReference,
    RiskBand,
)

# ============================================================================
# Rule IDs (canonical, stable identifiers)
# ============================================================================

# Diagnosis presence
RULE_DX_DIABETES_PRESENT = "DX_DIABETES_PRESENT"
RULE_DX_HTN_PRESENT = "DX_HTN_PRESENT"
RULE_DX_CHF_PRESENT = "DX_CHF_PRESENT"
RULE_DX_SEPSIS_PRESENT = "DX_SEPSIS_PRESENT"
RULE_DX_ARF_PRESENT = "DX_ARF_PRESENT"
RULE_DX_MALNUTRITION_PRESENT = "DX_MALNUTRITION_PRESENT"

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

# Sepsis MEAT
RULE_SEPSIS_MONITOR_MISSING = "SEPSIS_MONITOR_MISSING"
RULE_SEPSIS_EVAL_MISSING = "SEPSIS_EVAL_MISSING"
RULE_SEPSIS_ASSESS_MISSING = "SEPSIS_ASSESS_MISSING"
RULE_SEPSIS_TREAT_MISSING = "SEPSIS_TREAT_MISSING"

# Acute Respiratory Failure MEAT
RULE_ARF_MONITOR_MISSING = "ARF_MONITOR_MISSING"
RULE_ARF_EVAL_MISSING = "ARF_EVAL_MISSING"
RULE_ARF_ASSESS_MISSING = "ARF_ASSESS_MISSING"
RULE_ARF_TREAT_MISSING = "ARF_TREAT_MISSING"

# Malnutrition MEAT
RULE_MALNUTRITION_MONITOR_MISSING = "MALNUTRITION_MONITOR_MISSING"
RULE_MALNUTRITION_EVAL_MISSING = "MALNUTRITION_EVAL_MISSING"
RULE_MALNUTRITION_ASSESS_MISSING = "MALNUTRITION_ASSESS_MISSING"
RULE_MALNUTRITION_TREAT_MISSING = "MALNUTRITION_TREAT_MISSING"

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

# Specific medication tokens for diabetes (used for co-occurrence checking)
DIABETES_MED_TOKENS = [
    "metformin",
    "insulin",
    "glp-1",
    "semaglutide",
    "ozempic",
    "tirzepatide",
    "mounjaro",
    "glipizide",
    "glyburide",
    "jardiance",
    "farxiga",
]

# Generic action words (only count if med token nearby)
DIABETES_ACTION_WORDS = ["dose", "increase", "decrease", "continue", "start", "stop"]

# Combined treatment keywords (meds are always valid, actions need co-occurrence)
DIABETES_TREAT = DIABETES_MED_TOKENS + DIABETES_ACTION_WORDS

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

# Specific medication tokens for hypertension
HTN_MED_TOKENS = [
    "lisinopril",
    "amlodipine",
    "losartan",
    "hctz",
    "hydrochlorothiazide",
    "metoprolol",
    "carvedilol",
    "atenolol",
    "valsartan",
    "enalapril",
]

# Generic action words (only count if med token nearby)
HTN_ACTION_WORDS = ["start", "continue", "increase", "decrease", "stop"]

# Combined treatment keywords
HTN_TREAT = HTN_MED_TOKENS + HTN_ACTION_WORDS

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

# Specific medication tokens for CHF
CHF_MED_TOKENS = [
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
    "carvedilol",
    "metoprolol",
]

# Generic action words (only count if med token nearby)
CHF_ACTION_WORDS = ["dose", "increase", "decrease", "stop", "continue"]

# Combined treatment keywords
CHF_TREAT = CHF_MED_TOKENS + CHF_ACTION_WORDS

# ============================================================================
# Sepsis / Severe sepsis / Septic shock anchors
# ============================================================================
SEPSIS_KEYWORDS = [
    "sepsis",
    "severe sepsis",
    "septic shock",
    "a41",
    "r65.20",
    "r65.21",
    "septic",
    "bacteremia",
]
SEPSIS_MONITOR = [
    "lactate",
    "wbc",
    "white blood cell",
    "temperature",
    "blood pressure",
    "heart rate",
    "respiratory rate",
    "vital signs",
    "fever",
    "culture",
    "blood culture",
]
SEPSIS_EVALUATE = [
    "source control",
    "infection source",
    "organ dysfunction",
    "resolving",
    "worsening",
    "improving",
    "septic",
    "sirs criteria",
]
SEPSIS_ASSESS = [
    "sepsis",
    "septic",
    "sirs",
    "organ dysfunction",
    "qsofa",
    "sofa score",
]

# Sepsis medication tokens
SEPSIS_MED_TOKENS = [
    "antibiotic",
    "antibiotics",
    "vancomycin",
    "piperacillin",
    "tazobactam",
    "zosyn",
    "ceftriaxone",
    "cefepime",
    "meropenem",
    "levofloxacin",
    "fluids",
    "crystalloid",
    "normal saline",
    "lactated ringer",
]
SEPSIS_ACTION_WORDS = ["start", "continue", "broaden", "narrow", "escalate", "stop"]
SEPSIS_TREAT = SEPSIS_MED_TOKENS + SEPSIS_ACTION_WORDS

# ============================================================================
# Acute Respiratory Failure anchors
# ============================================================================
ARF_KEYWORDS = [
    "respiratory failure",
    "acute respiratory failure",
    "j96",
    "arf",
    "hypoxic respiratory failure",
    "hypercapnic respiratory failure",
]
ARF_MONITOR = [
    "oxygen saturation",
    "spo2",
    "o2 sat",
    "abg",
    "arterial blood gas",
    "pao2",
    "paco2",
    "respiratory rate",
    "work of breathing",
    "abg",
]
ARF_EVALUATE = [
    "hypoxia",
    "hypoxemia",
    "hypercapnia",
    "improving",
    "worsening",
    "stable",
    "respiratory distress",
]
ARF_ASSESS = [
    "respiratory failure",
    "hypoxic",
    "hypercapnic",
    "type 1",
    "type 2",
    "arf",
]

# ARF treatment tokens
ARF_MED_TOKENS = [
    "oxygen",
    "supplemental oxygen",
    "ventilation",
    "mechanical ventilation",
    "bipap",
    "cpap",
    "high flow",
    "nasal cannula",
    "non-rebreather",
    "intubation",
    "ventilator",
]
ARF_ACTION_WORDS = ["increase", "decrease", "wean", "titrate", "continue"]
ARF_TREAT = ARF_MED_TOKENS + ARF_ACTION_WORDS

# ============================================================================
# Malnutrition anchors
# ============================================================================
MALNUTRITION_KEYWORDS = [
    "malnutrition",
    "malnourished",
    "e43",
    "e44",
    "protein-calorie malnutrition",
    "undernutrition",
]
MALNUTRITION_MONITOR = [
    "weight",
    "bmi",
    "body mass index",
    "albumin",
    "prealbumin",
    "caloric intake",
    "dietary intake",
]
MALNUTRITION_EVALUATE = [
    "severity",
    "mild",
    "moderate",
    "severe",
    "improving",
    "worsening",
    "stable",
]
MALNUTRITION_ASSESS = [
    "malnutrition",
    "malnourished",
    "nutritional status",
    "bmi",
    "albumin",
]

# Malnutrition treatment tokens
MALNUTRITION_MED_TOKENS = [
    "nutrition",
    "nutritional support",
    "dietician",
    "dietitian",
    "dietary consult",
    "tube feeding",
    "tpn",
    "parenteral nutrition",
    "enteral nutrition",
    "supplements",
    "nutritional supplements",
    "ensure",
    "boost",
]
MALNUTRITION_ACTION_WORDS = ["start", "continue", "increase", "advance"]
MALNUTRITION_TREAT = MALNUTRITION_MED_TOKENS + MALNUTRITION_ACTION_WORDS

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


def contains_treatment_with_cooccurrence(
    text: str, med_tokens: List[str], action_words: List[str], window_size: int = 80
) -> bool:
    """
    Check if text contains treatment keywords with context-aware co-occurrence logic.

    Medication tokens are always valid. Action words only count if a medication
    token appears within ±window_size characters.

    Args:
        text: Clinical note text
        med_tokens: List of medication-specific keywords (always valid)
        action_words: List of generic action words (need co-occurrence)
        window_size: Character window for co-occurrence check (default: 80)

    Returns:
        True if any medication token found, or action word found with nearby med token
    """
    text_lower = text.lower()

    # First check for medication tokens (always valid)
    for med_token in med_tokens:
        pattern = r"\b" + re.escape(med_token.lower())
        if re.search(pattern, text_lower):
            return True

    # Check action words with co-occurrence requirement
    for action_word in action_words:
        pattern = r"\b" + re.escape(action_word.lower())
        match = re.search(pattern, text_lower)

        if match:
            # Found action word, check for nearby medication token
            start = max(0, match.start() - window_size)
            end = min(len(text_lower), match.end() + window_size)
            context = text_lower[start:end]

            # Check if any medication token is in the context window
            for med_token in med_tokens:
                med_pattern = r"\b" + re.escape(med_token.lower())
                if re.search(med_pattern, context):
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

        # Sepsis
        if detect_diagnosis(note_text, diagnoses, SEPSIS_KEYWORDS):
            risk_score, explanations, deficits = self._check_sepsis_meat(
                note_text, risk_score, explanations, deficits
            )

        # Acute Respiratory Failure
        if detect_diagnosis(note_text, diagnoses, ARF_KEYWORDS):
            risk_score, explanations, deficits = self._check_arf_meat(
                note_text, risk_score, explanations, deficits
            )

        # Malnutrition
        if detect_diagnosis(note_text, diagnoses, MALNUTRITION_KEYWORDS):
            risk_score, explanations, deficits = self._check_malnutrition_meat(
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
        if not contains_treatment_with_cooccurrence(
            note_text, DIABETES_MED_TOKENS, DIABETES_ACTION_WORDS
        ):
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
        if not contains_treatment_with_cooccurrence(
            note_text, HTN_MED_TOKENS, HTN_ACTION_WORDS
        ):
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
        if not contains_treatment_with_cooccurrence(
            note_text, CHF_MED_TOKENS, CHF_ACTION_WORDS
        ):
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

    def _check_sepsis_meat(
        self,
        note_text: str,
        risk_score: int,
        explanations: List[ScoreExplanation],
        deficits: List[EvidenceDeficit],
    ) -> Tuple[int, List[ScoreExplanation], List[EvidenceDeficit]]:
        """Check MEAT anchors for sepsis."""

        # Monitor
        if not contains_any_keyword(note_text, SEPSIS_MONITOR):
            risk_score += 30
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_SEPSIS_MONITOR_MISSING,
                    impact=30,
                    reason="Sepsis documented but no monitoring data (lactate, vitals, cultures)",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-SEPSIS-M",
                    title="Sepsis: Missing Monitor",
                    category="monitor",
                    why_payer_denies="Sepsis diagnosis without vital signs and lab monitoring fails MEAT criteria",
                    what_to_add="Document lactate trend, vital signs, fever curve, and culture results.",
                    evidence_refs=[],
                    confidence=0.95,
                    condition="sepsis",
                    missing=["lactate", "vital signs", "cultures"],
                    fix="Document lactate trend, vital signs, fever curve, and culture results.",
                )
            )

        # Evaluate
        if not contains_any_keyword(note_text, SEPSIS_EVALUATE):
            risk_score += 20
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_SEPSIS_EVAL_MISSING,
                    impact=20,
                    reason="Sepsis documented but no evaluation of infection source or organ dysfunction",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-SEPSIS-E",
                    title="Sepsis: Missing Evaluate",
                    category="evaluate",
                    why_payer_denies="No evaluation of sepsis source or trajectory undermines medical necessity",
                    what_to_add="Document suspected infection source, organ dysfunction, and clinical trajectory.",
                    evidence_refs=[],
                    confidence=0.90,
                    condition="sepsis",
                    missing=[
                        "infection source",
                        "organ dysfunction",
                        "clinical trajectory",
                    ],
                    fix="Document suspected infection source, organ dysfunction, and clinical trajectory.",
                )
            )

        # Assess
        if not contains_any_keyword(note_text, SEPSIS_ASSESS):
            risk_score += 20
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_SEPSIS_ASSESS_MISSING,
                    impact=20,
                    reason="Sepsis documented but no assessment with SIRS or SOFA criteria",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-SEPSIS-A",
                    title="Sepsis: Missing Assess",
                    category="assess",
                    why_payer_denies="Assessment must specify sepsis criteria (SIRS/qSOFA) and organ dysfunction",
                    what_to_add="Add 'Sepsis with organ dysfunction' or SIRS/qSOFA criteria to assessment.",
                    evidence_refs=[],
                    confidence=0.88,
                    condition="sepsis",
                    missing=["SIRS criteria", "organ dysfunction", "sepsis criteria"],
                    fix="Add 'Sepsis with organ dysfunction' or SIRS/qSOFA criteria to assessment.",
                )
            )

        # Treat
        if not contains_treatment_with_cooccurrence(
            note_text, SEPSIS_MED_TOKENS, SEPSIS_ACTION_WORDS
        ):
            risk_score += 30
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_SEPSIS_TREAT_MISSING,
                    impact=30,
                    reason="Sepsis documented but no treatment plan (antibiotics, fluids)",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-SEPSIS-T",
                    title="Sepsis: Missing Treat",
                    category="treat",
                    why_payer_denies="Sepsis without documented antibiotics and fluid resuscitation fails to justify medical necessity",
                    what_to_add="Document suspected source + organ dysfunction + lactate trend + fluids/antibiotics timing.",
                    evidence_refs=[],
                    confidence=0.96,
                    condition="sepsis",
                    missing=["antibiotics", "fluid resuscitation", "source control"],
                    fix="Document suspected source + organ dysfunction + lactate trend + fluids/antibiotics timing.",
                )
            )

        return risk_score, explanations, deficits

    def _check_arf_meat(
        self,
        note_text: str,
        risk_score: int,
        explanations: List[ScoreExplanation],
        deficits: List[EvidenceDeficit],
    ) -> Tuple[int, List[ScoreExplanation], List[EvidenceDeficit]]:
        """Check MEAT anchors for acute respiratory failure."""

        # Monitor
        if not contains_any_keyword(note_text, ARF_MONITOR):
            risk_score += 28
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_ARF_MONITOR_MISSING,
                    impact=28,
                    reason="Respiratory failure documented but no monitoring data (SpO2, ABG, RR)",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-ARF-M",
                    title="ARF: Missing Monitor",
                    category="monitor",
                    why_payer_denies="ARF diagnosis without oxygenation monitoring fails MEAT criteria",
                    what_to_add="Document SpO2 values, ABG results, respiratory rate, and work of breathing.",
                    evidence_refs=[],
                    confidence=0.93,
                    condition="acute respiratory failure",
                    missing=["SpO2", "ABG", "respiratory rate"],
                    fix="Document SpO2 values, ABG results, respiratory rate, and work of breathing.",
                )
            )

        # Evaluate
        if not contains_any_keyword(note_text, ARF_EVALUATE):
            risk_score += 18
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_ARF_EVAL_MISSING,
                    impact=18,
                    reason="Respiratory failure documented but no evaluation of hypoxia/hypercapnia status",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-ARF-E",
                    title="ARF: Missing Evaluate",
                    category="evaluate",
                    why_payer_denies="No evaluation of respiratory status undermines medical necessity",
                    what_to_add="Document if hypoxic vs hypercapnic, improving vs worsening respiratory status.",
                    evidence_refs=[],
                    confidence=0.87,
                    condition="acute respiratory failure",
                    missing=["hypoxia assessment", "clinical trajectory"],
                    fix="Document if hypoxic vs hypercapnic, improving vs worsening respiratory status.",
                )
            )

        # Assess
        if not contains_any_keyword(note_text, ARF_ASSESS):
            risk_score += 18
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_ARF_ASSESS_MISSING,
                    impact=18,
                    reason="Respiratory failure documented but no assessment with type/severity",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-ARF-A",
                    title="ARF: Missing Assess",
                    category="assess",
                    why_payer_denies="Assessment must specify ARF type (hypoxic/hypercapnic) and severity",
                    what_to_add="Add 'Acute hypoxic respiratory failure' or 'Type 1 respiratory failure' to assessment.",
                    evidence_refs=[],
                    confidence=0.85,
                    condition="acute respiratory failure",
                    missing=["ARF type", "severity"],
                    fix="Add 'Acute hypoxic respiratory failure' or 'Type 1 respiratory failure' to assessment.",
                )
            )

        # Treat
        if not contains_treatment_with_cooccurrence(
            note_text, ARF_MED_TOKENS, ARF_ACTION_WORDS
        ):
            risk_score += 28
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_ARF_TREAT_MISSING,
                    impact=28,
                    reason="Respiratory failure documented but no treatment plan (oxygen, ventilation)",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-ARF-T",
                    title="ARF: Missing Treat",
                    category="treat",
                    why_payer_denies="ARF without documented oxygen/ventilation support fails to justify medical necessity",
                    what_to_add="Document oxygen delivery method (nasal cannula, high flow, BiPAP, ventilator) with settings.",
                    evidence_refs=[],
                    confidence=0.94,
                    condition="acute respiratory failure",
                    missing=["oxygen therapy", "ventilation support"],
                    fix="Document oxygen delivery method (nasal cannula, high flow, BiPAP, ventilator) with settings.",
                )
            )

        return risk_score, explanations, deficits

    def _check_malnutrition_meat(
        self,
        note_text: str,
        risk_score: int,
        explanations: List[ScoreExplanation],
        deficits: List[EvidenceDeficit],
    ) -> Tuple[int, List[ScoreExplanation], List[EvidenceDeficit]]:
        """Check MEAT anchors for malnutrition."""

        # Monitor
        if not contains_any_keyword(note_text, MALNUTRITION_MONITOR):
            risk_score += 26
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_MALNUTRITION_MONITOR_MISSING,
                    impact=26,
                    reason="Malnutrition documented but no monitoring data (weight, BMI, albumin)",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-MALNUTRITION-M",
                    title="Malnutrition: Missing Monitor",
                    category="monitor",
                    why_payer_denies="Malnutrition diagnosis without nutritional markers fails MEAT criteria",
                    what_to_add="Document weight trend, BMI, albumin/prealbumin levels, and dietary intake.",
                    evidence_refs=[],
                    confidence=0.92,
                    condition="malnutrition",
                    missing=["weight", "BMI", "albumin", "dietary intake"],
                    fix="Document weight trend, BMI, albumin/prealbumin levels, and dietary intake.",
                )
            )

        # Evaluate
        if not contains_any_keyword(note_text, MALNUTRITION_EVALUATE):
            risk_score += 16
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_MALNUTRITION_EVAL_MISSING,
                    impact=16,
                    reason="Malnutrition documented but no evaluation of severity or trajectory",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-MALNUTRITION-E",
                    title="Malnutrition: Missing Evaluate",
                    category="evaluate",
                    why_payer_denies="No evaluation of malnutrition severity undermines medical necessity",
                    what_to_add="Document if mild, moderate, or severe malnutrition and clinical trajectory.",
                    evidence_refs=[],
                    confidence=0.86,
                    condition="malnutrition",
                    missing=["severity", "clinical trajectory"],
                    fix="Document if mild, moderate, or severe malnutrition and clinical trajectory.",
                )
            )

        # Assess
        if not contains_any_keyword(note_text, MALNUTRITION_ASSESS):
            risk_score += 16
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_MALNUTRITION_ASSESS_MISSING,
                    impact=16,
                    reason="Malnutrition documented but no assessment with criteria",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-MALNUTRITION-A",
                    title="Malnutrition: Missing Assess",
                    category="assess",
                    why_payer_denies="Assessment must specify malnutrition criteria (BMI, albumin, weight loss)",
                    what_to_add="Add 'Moderate malnutrition with BMI 16 and albumin 2.8' to assessment.",
                    evidence_refs=[],
                    confidence=0.84,
                    condition="malnutrition",
                    missing=["malnutrition criteria", "severity grade"],
                    fix="Add 'Moderate malnutrition with BMI 16 and albumin 2.8' to assessment.",
                )
            )

        # Treat
        if not contains_treatment_with_cooccurrence(
            note_text, MALNUTRITION_MED_TOKENS, MALNUTRITION_ACTION_WORDS
        ):
            risk_score += 26
            explanations.append(
                ScoreExplanation(
                    rule_id=RULE_MALNUTRITION_TREAT_MISSING,
                    impact=26,
                    reason="Malnutrition documented but no treatment plan (nutrition support, dietitian)",
                )
            )
            deficits.append(
                EvidenceDeficit(
                    id="DEF-MALNUTRITION-T",
                    title="Malnutrition: Missing Treat",
                    category="treat",
                    why_payer_denies="Malnutrition without documented nutritional intervention fails to justify medical necessity",
                    what_to_add="Document nutritional support plan (dietitian consult, supplements, tube feeding, TPN).",
                    evidence_refs=[],
                    confidence=0.93,
                    condition="malnutrition",
                    missing=["nutritional support", "dietitian consult"],
                    fix="Document nutritional support plan (dietitian consult, supplements, tube feeding, TPN).",
                )
            )

        return risk_score, explanations, deficits
