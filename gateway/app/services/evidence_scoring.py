"""
Evidence Scoring Engine for Shadow Mode.

This module implements rule-based scoring for clinical documentation quality.
All rules are heuristic indicators, not clinical truth or billing advice.

Scoring Philosophy:
- Start at 100 (perfect documentation)
- Apply penalties for missing/inconsistent elements
- All rules are auditable with rule_id + rationale
- Focus on common denial-prone patterns (not exhaustive)

IMPORTANT: These are heuristic rules for risk estimation, not:
- Clinical decision support
- Billing/coding advice
- Guarantees of denial or approval
"""

import re
from typing import List, Tuple
from gateway.app.models.shadow import (
    ShadowRequest,
    ScoreExplanation,
    EvidenceReference,
    EvidenceDeficit,
    DenialRiskFlag
)


# Rule-based scoring thresholds
SCORE_THRESHOLDS = {
    "green": 80,   # >= 80: Low risk
    "yellow": 60,  # 60-79: Medium risk
    "red": 0       # < 60: High risk
}

# High-risk diagnoses that often face payer scrutiny
HIGH_SCRUTINY_DIAGNOSES = [
    "malnutrition", "sepsis", "respiratory failure", "encephalopathy",
    "acute respiratory failure", "severe malnutrition", "septic shock"
]


def check_hpi_elements(note_text: str) -> Tuple[bool, List[str]]:
    """
    Check for History of Present Illness (HPI) elements.
    
    This is a heuristic check, not a comprehensive HPI parser.
    
    Returns:
        (has_sufficient_hpi, missing_elements)
    """
    note_lower = note_text.lower()
    missing = []
    
    # Check for timing indicators
    if not any(word in note_lower for word in ["day", "days", "week", "weeks", "month", "today", "yesterday", "onset"]):
        missing.append("timing/duration")
    
    # Check for severity indicators
    if not any(word in note_lower for word in ["severe", "moderate", "mild", "worsening", "improving", "stable"]):
        missing.append("severity")
    
    # Check for context
    if not any(word in note_lower for word in ["associated", "associated with", "along with", "accompanied by"]):
        missing.append("associated symptoms")
    
    has_sufficient = len(missing) < 2  # Allow 1 missing element
    return has_sufficient, missing


def check_attestation(note_text: str) -> bool:
    """
    Check for physician attestation phrases.
    
    Heuristic: looks for common attestation patterns.
    """
    attestation_patterns = [
        r"reviewed and agree",
        r"personally reviewed",
        r"i have personally",
        r"attending physician",
        r"attestation:",
        r"electronically signed"
    ]
    
    note_lower = note_text.lower()
    return any(re.search(pattern, note_lower) for pattern in attestation_patterns)


def check_diagnosis_support(
    diagnoses: List[str],
    labs: List,
    vitals: List,
    problem_list: List[str]
) -> List[Tuple[str, str]]:
    """
    Check if high-scrutiny diagnoses have supporting evidence.
    
    Returns:
        List of (diagnosis, missing_evidence_type) tuples
    """
    unsupported = []
    
    for diagnosis in diagnoses:
        diagnosis_lower = diagnosis.lower()
        
        # Check malnutrition support
        if "malnutrition" in diagnosis_lower:
            has_albumin = any(lab.name.lower() == "albumin" for lab in labs)
            has_weight = any(v.name.lower() in ["weight", "bmi"] for v in vitals)
            if not has_albumin and not has_weight:
                unsupported.append((diagnosis, "albumin/weight"))
        
        # Check sepsis support
        elif "sepsis" in diagnosis_lower:
            has_wbc = any(lab.name.lower() in ["wbc", "white blood cell"] for lab in labs)
            has_temp = any(v.name.lower() in ["temp", "temperature"] for v in vitals)
            if not has_wbc and not has_temp:
                unsupported.append((diagnosis, "wbc/temperature"))
        
        # Check respiratory failure support
        elif "respiratory failure" in diagnosis_lower or "respiratory distress" in diagnosis_lower:
            has_o2 = any(v.name.lower() in ["o2", "spo2", "oxygen"] for v in vitals)
            has_rr = any(v.name.lower() in ["rr", "respiratory rate"] for v in vitals)
            if not has_o2 and not has_rr:
                unsupported.append((diagnosis, "o2/respiratory rate"))
    
    return unsupported


def score_evidence(request: ShadowRequest) -> Tuple[int, List[ScoreExplanation], List[EvidenceDeficit], List[DenialRiskFlag]]:
    """
    Score evidence sufficiency using rule-based heuristics.
    
    Args:
        request: Shadow mode request with clinical context
        
    Returns:
        Tuple of (score, explanations, deficits, risk_flags)
    """
    score = 100  # Start with perfect score
    explanations: List[ScoreExplanation] = []
    deficits: List[EvidenceDeficit] = []
    risk_flags: List[DenialRiskFlag] = []
    
    # Rule 1: Check for empty note
    if not request.note_text or len(request.note_text.strip()) < 50:
        score -= 40
        explanations.append(ScoreExplanation(
            rule_id="RULE-001",
            impact=-40,
            reason="Note text is missing or insufficient (< 50 characters)"
        ))
        deficits.append(EvidenceDeficit(
            id="DEF-001",
            title="Insufficient clinical documentation",
            category="documentation",
            why_payer_denies="Insufficient documentation to support medical necessity",
            what_to_add="Add comprehensive clinical note with HPI, assessment, and plan",
            evidence_refs=[EvidenceReference(type="note_text", key="length", value=len(request.note_text))],
            confidence=1.0
        ))
        risk_flags.append(DenialRiskFlag(
            id="DR-001",
            severity="high",
            rationale="Minimal documentation increases denial risk significantly",
            rule_id="RULE-001"
        ))
    
    # Rule 2: Check HPI elements
    has_hpi, missing_hpi = check_hpi_elements(request.note_text)
    if not has_hpi:
        penalty = len(missing_hpi) * 5
        score -= penalty
        explanations.append(ScoreExplanation(
            rule_id="RULE-002",
            impact=-penalty,
            reason=f"Missing HPI elements: {', '.join(missing_hpi)}"
        ))
        deficits.append(EvidenceDeficit(
            id="DEF-002",
            title=f"Incomplete History of Present Illness (missing: {', '.join(missing_hpi)})",
            category="documentation",
            why_payer_denies="Incomplete HPI fails to establish medical necessity timeline",
            what_to_add=f"Add {', '.join(missing_hpi)} to HPI section",
            evidence_refs=[EvidenceReference(type="note_text", key="hpi_elements", value=missing_hpi)],
            confidence=0.8
        ))
    
    # Rule 3: Check for physician attestation
    if not check_attestation(request.note_text):
        score -= 10
        explanations.append(ScoreExplanation(
            rule_id="RULE-003",
            impact=-10,
            reason="Missing physician attestation or signature"
        ))
        deficits.append(EvidenceDeficit(
            id="DEF-003",
            title="Missing physician attestation",
            category="documentation",
            why_payer_denies="Unsigned notes may not meet authentication requirements",
            what_to_add="Add physician attestation/signature to note",
            evidence_refs=[],
            confidence=0.7
        ))
    
    # Rule 4: Check diagnosis support for high-scrutiny conditions
    unsupported = check_diagnosis_support(request.diagnoses, request.labs, request.vitals, request.problem_list)
    if unsupported:
        penalty = len(unsupported) * 10
        score -= penalty
        for diagnosis, missing_evidence in unsupported:
            explanations.append(ScoreExplanation(
                rule_id=f"RULE-004-{diagnosis[:10]}",
                impact=-10,
                reason=f"Diagnosis '{diagnosis}' lacks supporting {missing_evidence}"
            ))
            deficits.append(EvidenceDeficit(
                id=f"DEF-004-{len(deficits)+1}",
                title=f"Unsupported high-scrutiny diagnosis: {diagnosis}",
                category="clinical_inconsistency",
                why_payer_denies=f"High-dollar diagnosis '{diagnosis}' without objective {missing_evidence} may be denied",
                what_to_add=f"Document {missing_evidence} or add clinical rationale for {diagnosis}",
                evidence_refs=[EvidenceReference(type="diagnosis", key=diagnosis, value=None)],
                confidence=0.85
            ))
            risk_flags.append(DenialRiskFlag(
                id=f"DR-004-{len(risk_flags)+1}",
                severity="high",
                rationale=f"High-scrutiny diagnosis without supporting evidence",
                rule_id=f"RULE-004-{diagnosis[:10]}"
            ))
    
    # Rule 5: Check for diagnoses without any supporting data
    if request.diagnoses and not request.labs and not request.vitals:
        score -= 15
        explanations.append(ScoreExplanation(
            rule_id="RULE-005",
            impact=-15,
            reason="Diagnoses present but no labs or vitals documented"
        ))
        deficits.append(EvidenceDeficit(
            id="DEF-005",
            title="Diagnoses without objective clinical data",
            category="clinical_inconsistency",
            why_payer_denies="Claims lack objective data to support diagnoses",
            what_to_add="Document relevant labs, vitals, or physical exam findings",
            evidence_refs=[
                EvidenceReference(type="diagnosis", key="count", value=len(request.diagnoses)),
                EvidenceReference(type="lab", key="count", value=0),
                EvidenceReference(type="vital", key="count", value=0)
            ],
            confidence=0.75
        ))
        risk_flags.append(DenialRiskFlag(
            id="DR-005",
            severity="med",
            rationale="Diagnoses without supporting objective data",
            rule_id="RULE-005"
        ))
    
    # Rule 6: Check for critical lab values without note discussion
    critical_labs = [lab for lab in request.labs if _is_critical_value(lab)]
    if critical_labs:
        for lab in critical_labs:
            if lab.name.lower() not in request.note_text.lower():
                score -= 5
                explanations.append(ScoreExplanation(
                    rule_id=f"RULE-006-{lab.name}",
                    impact=-5,
                    reason=f"Critical lab '{lab.name}={lab.value}' not discussed in note"
                ))
                deficits.append(EvidenceDeficit(
                    id=f"DEF-006-{len(deficits)+1}",
                    title=f"Critical lab value not addressed: {lab.name}",
                    category="documentation",
                    why_payer_denies="Abnormal labs without documentation may indicate incomplete care",
                    what_to_add=f"Document clinical interpretation of {lab.name}={lab.value} {lab.unit}",
                    evidence_refs=[EvidenceReference(type="lab", key=lab.name, value=lab.value)],
                    confidence=0.9
                ))
    
    # Ensure score doesn't go below 0
    score = max(0, score)
    
    return score, explanations, deficits, risk_flags


def _is_critical_value(lab) -> bool:
    """
    Check if lab value is potentially critical.
    
    Heuristic thresholds - not comprehensive medical guidelines.
    """
    lab_name = lab.name.lower()
    value = lab.value
    
    # Simple heuristics for common critical values
    if lab_name == "albumin" and value < 2.5:
        return True
    if lab_name in ["wbc", "white blood cell"] and (value < 2.0 or value > 20.0):
        return True
    if lab_name in ["sodium", "na"] and (value < 120 or value > 155):
        return True
    if lab_name in ["potassium", "k"] and (value < 2.5 or value > 6.0):
        return True
    
    return False


def get_score_band(score: int) -> str:
    """
    Convert numeric score to risk band.
    
    Args:
        score: Evidence sufficiency score (0-100)
        
    Returns:
        Risk band: "green", "yellow", or "red"
    """
    if score >= SCORE_THRESHOLDS["green"]:
        return "green"
    elif score >= SCORE_THRESHOLDS["yellow"]:
        return "yellow"
    else:
        return "red"
