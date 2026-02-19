"""
Evidence Sufficiency Scoring Service for CDIL Shadow Mode.

This service provides deterministic, rule-based scoring of clinical documentation
to identify evidence gaps that could lead to claim denials.

Design Principles:
- Deterministic, not AI-based
- Reviewable and transparent
- CFO-readable outputs
- Simple, expandable rule library
"""

import re
from typing import Dict, List, Any, Optional


class DiagnosisRule:
    """
    Rule for evaluating evidence sufficiency for a diagnosis code.
    
    Each rule defines required evidence elements that should be present
    in the clinical documentation to support the diagnosis.
    """
    
    def __init__(
        self,
        code: str,
        description: str,
        required_elements: List[str],
        keywords: Dict[str, List[str]],
        risk_level: str = "medium"
    ):
        """
        Initialize a diagnosis rule.
        
        Args:
            code: ICD-10 diagnosis code
            description: Human-readable diagnosis description
            required_elements: List of evidence elements that should be documented
            keywords: Dict mapping element names to keyword patterns to search for
            risk_level: Risk level if evidence is missing (low, medium, high)
        """
        self.code = code
        self.description = description
        self.required_elements = required_elements
        self.keywords = keywords
        self.risk_level = risk_level
    
    def evaluate(self, note_text: str, structured_data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Evaluate if sufficient evidence exists for this diagnosis.
        
        Args:
            note_text: Clinical note text
            structured_data: Optional structured data (labs, vitals, etc.)
            
        Returns:
            Dict with:
                - evidence_present: bool
                - missing_elements: List[str]
                - found_elements: List[str]
        """
        note_lower = note_text.lower()
        found_elements = []
        missing_elements = []
        
        for element in self.required_elements:
            if element in self.keywords:
                # Check if any keyword for this element is present
                element_found = False
                for keyword in self.keywords[element]:
                    # Use word boundary matching for more accurate detection
                    pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                    if re.search(pattern, note_lower):
                        element_found = True
                        break
                
                # Also check structured data if available
                if not element_found and structured_data:
                    element_key = element.lower().replace(" ", "_")
                    if element_key in structured_data and structured_data[element_key]:
                        element_found = True
                
                if element_found:
                    found_elements.append(element)
                else:
                    missing_elements.append(element)
            else:
                # No keywords defined, mark as missing
                missing_elements.append(element)
        
        evidence_present = len(missing_elements) == 0
        
        return {
            "evidence_present": evidence_present,
            "found_elements": found_elements,
            "missing_elements": missing_elements
        }


# Rule Library for Common High-Value Diagnoses
DIAGNOSIS_RULES = {
    # Malnutrition (E43, E44)
    "E43": DiagnosisRule(
        code="E43",
        description="Unspecified severe protein-calorie malnutrition",
        required_elements=["BMI", "Albumin", "Weight Loss", "Dietary Assessment"],
        keywords={
            "BMI": ["bmi", "body mass index", "underweight"],
            "Albumin": ["albumin", "hypoalbuminemia", "low albumin"],
            "Weight Loss": ["weight loss", "cachexia", "wasting", "malnourished"],
            "Dietary Assessment": ["dietary", "nutrition", "dietician", "nutritional assessment", "caloric intake"]
        },
        risk_level="high"
    ),
    "E44": DiagnosisRule(
        code="E44",
        description="Protein-calorie malnutrition",
        required_elements=["BMI", "Albumin", "Weight Loss"],
        keywords={
            "BMI": ["bmi", "body mass index", "underweight"],
            "Albumin": ["albumin", "hypoalbuminemia", "low albumin"],
            "Weight Loss": ["weight loss", "malnourished", "poor nutrition"]
        },
        risk_level="high"
    ),
    
    # Sepsis (A41.9)
    "A41.9": DiagnosisRule(
        code="A41.9",
        description="Sepsis, unspecified organism",
        required_elements=["SIRS Criteria", "Infection Source", "Lab Results", "Vital Signs"],
        keywords={
            "SIRS Criteria": ["sirs", "systemic inflammatory response", "sepsis"],
            "Infection Source": ["infection", "bacteremia", "source", "culture positive", "infected", "pneumonia", "uti", "urinary tract infection", "cellulitis", "abscess"],
            "Lab Results": ["wbc", "white blood cell", "lactate", "procalcitonin", "blood culture"],
            "Vital Signs": ["fever", "temperature", "tachycardia", "heart rate", "hypotension", "blood pressure"]
        },
        risk_level="high"
    ),
    
    # Congestive Heart Failure (I50.9, I50.23, I50.33)
    "I50.9": DiagnosisRule(
        code="I50.9",
        description="Heart failure, unspecified",
        required_elements=["Ejection Fraction", "Symptoms", "Physical Exam", "Chest X-ray"],
        keywords={
            "Ejection Fraction": ["ejection fraction", "ef", "lvef", "systolic function"],
            "Symptoms": ["dyspnea", "shortness of breath", "sob", "orthopnea", "edema"],
            "Physical Exam": ["rales", "crackles", "s3", "jvd", "jugular venous distension", "peripheral edema"],
            "Chest X-ray": ["chest x-ray", "cxr", "pulmonary edema", "cardiomegaly"]
        },
        risk_level="high"
    ),
    "I50.23": DiagnosisRule(
        code="I50.23",
        description="Acute on chronic systolic heart failure",
        required_elements=["Ejection Fraction", "Acute Symptoms", "Prior CHF History"],
        keywords={
            "Ejection Fraction": ["ejection fraction", "ef", "lvef", "reduced ef"],
            "Acute Symptoms": ["acute", "decompensated", "worsening", "exacerbation"],
            "Prior CHF History": ["history of heart failure", "chronic heart failure", "prior chf"]
        },
        risk_level="high"
    ),
    "I50.33": DiagnosisRule(
        code="I50.33",
        description="Acute on chronic diastolic heart failure",
        required_elements=["Ejection Fraction", "Acute Symptoms", "Diastolic Dysfunction"],
        keywords={
            "Ejection Fraction": ["ejection fraction", "ef", "preserved ef", "hfpef"],
            "Acute Symptoms": ["acute", "decompensated", "worsening"],
            "Diastolic Dysfunction": ["diastolic", "diastolic dysfunction", "hfpef"]
        },
        risk_level="high"
    ),
    
    # Acute Kidney Injury (N17.9)
    "N17.9": DiagnosisRule(
        code="N17.9",
        description="Acute kidney injury, unspecified",
        required_elements=["Creatinine", "Baseline Renal Function", "Urine Output", "Etiology"],
        keywords={
            "Creatinine": ["creatinine", "cr", "serum creatinine", "elevated creatinine"],
            "Baseline Renal Function": ["baseline", "baseline creatinine", "prior renal function"],
            "Urine Output": ["urine output", "oliguria", "anuria", "decreased urine"],
            "Etiology": ["prerenal", "intrinsic", "postrenal", "cause", "aki cause"]
        },
        risk_level="high"
    ),
    
    # Respiratory Failure (J96.00, J96.90)
    "J96.00": DiagnosisRule(
        code="J96.00",
        description="Acute respiratory failure, unspecified",
        required_elements=["ABG Results", "Oxygen Saturation", "Respiratory Rate", "Clinical Presentation"],
        keywords={
            "ABG Results": ["abg", "arterial blood gas", "pao2", "paco2", "ph"],
            "Oxygen Saturation": ["oxygen saturation", "spo2", "o2 sat", "hypoxemia", "hypoxia"],
            "Respiratory Rate": ["respiratory rate", "rr", "tachypnea", "respiratory distress"],
            "Clinical Presentation": ["respiratory failure", "dyspnea", "respiratory distress", "shortness of breath"]
        },
        risk_level="high"
    ),
    "J96.90": DiagnosisRule(
        code="J96.90",
        description="Respiratory failure, unspecified",
        required_elements=["Oxygen Requirement", "Clinical Status", "Etiology"],
        keywords={
            "Oxygen Requirement": ["oxygen", "supplemental oxygen", "ventilation", "cpap", "bipap"],
            "Clinical Status": ["respiratory status", "work of breathing", "respiratory distress"],
            "Etiology": ["pneumonia", "copd", "asthma", "pulmonary", "cause"]
        },
        risk_level="high"
    )
}


def score_note_defensibility(
    note_text: str,
    diagnosis_codes: List[str],
    structured_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Score the defensibility of clinical documentation.
    
    Evaluates whether sufficient evidence exists in the documentation to support
    the assigned diagnosis codes. This is a deterministic, rule-based analysis
    designed to flag potential claim denial risks.
    
    Args:
        note_text: Clinical note text to evaluate
        diagnosis_codes: List of ICD-10 diagnosis codes
        structured_data: Optional structured data (labs, vitals, etc.)
        
    Returns:
        Dict containing:
            - overall_score: Overall defensibility score (0-100)
            - diagnoses: List of diagnosis evaluations
            - flags: List of concerning findings
            - summary: Human-readable summary
    """
    if not note_text or not diagnosis_codes:
        return {
            "overall_score": 0,
            "diagnoses": [],
            "flags": ["No note text or diagnosis codes provided"],
            "summary": "Insufficient data for evaluation"
        }
    
    diagnoses = []
    flags = []
    total_diagnoses = len(diagnosis_codes)
    supported_diagnoses = 0
    high_risk_unsupported = 0
    
    for code in diagnosis_codes:
        # Try to find rule - handles both formats: "A41.9" and "A419"
        # ICD-10 codes can be written with or without periods
        rule = None
        
        # Try exact match first
        if code in DIAGNOSIS_RULES:
            rule = DIAGNOSIS_RULES[code]
        # Try without periods
        elif code.replace(".", "") in DIAGNOSIS_RULES:
            rule = DIAGNOSIS_RULES[code.replace(".", "")]
        # Try adding period in standard position (after 3 chars for most ICD-10)
        elif len(code) > 3 and "." not in code:
            code_with_period = code[:3] + "." + code[3:]
            if code_with_period in DIAGNOSIS_RULES:
                rule = DIAGNOSIS_RULES[code_with_period]
        
        if rule:
            evaluation = rule.evaluate(note_text, structured_data)
            
            diagnosis_result = {
                "code": code,
                "description": rule.description,
                "evidence_present": evaluation["evidence_present"],
                "missing_elements": evaluation["missing_elements"],
                "found_elements": evaluation["found_elements"],
                "risk_level": rule.risk_level
            }
            
            diagnoses.append(diagnosis_result)
            
            if evaluation["evidence_present"]:
                supported_diagnoses += 1
            else:
                # Flag unsupported high-value diagnoses
                if rule.risk_level == "high":
                    high_risk_unsupported += 1
                    flags.append(
                        f"High-value diagnosis {code} ({rule.description}) lacks sufficient documentation"
                    )
        else:
            # Unknown diagnosis code - can't evaluate
            diagnoses.append({
                "code": code,
                "description": "Unknown diagnosis code",
                "evidence_present": None,
                "missing_elements": [],
                "found_elements": [],
                "risk_level": "unknown"
            })
    
    # Calculate overall score
    if total_diagnoses == 0:
        overall_score = 100
    else:
        # Score based on proportion of supported diagnoses
        # Weight high-risk diagnoses more heavily
        evaluable_count = sum(1 for d in diagnoses if d["evidence_present"] is not None)
        if evaluable_count == 0:
            overall_score = 100  # No evaluable diagnoses, assume OK
        else:
            support_ratio = supported_diagnoses / evaluable_count
            overall_score = int(support_ratio * 100)
            
            # Apply penalty for high-risk unsupported diagnoses
            if high_risk_unsupported > 0:
                penalty = min(high_risk_unsupported * 15, 30)  # Max 30 point penalty
                overall_score = max(0, overall_score - penalty)
    
    # Generate summary
    if overall_score >= 80:
        summary = "Documentation appears defensible with strong evidence support"
    elif overall_score >= 60:
        summary = "Documentation is adequate but has some evidence gaps"
    elif overall_score >= 40:
        summary = "Documentation has significant evidence gaps that pose denial risk"
    else:
        summary = "Documentation has critical evidence deficits with high denial risk"
    
    return {
        "overall_score": overall_score,
        "diagnoses": diagnoses,
        "flags": flags,
        "summary": summary
    }
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
