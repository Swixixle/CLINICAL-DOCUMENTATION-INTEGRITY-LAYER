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
        risk_level: str = "medium",
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

    def evaluate(
        self, note_text: str, structured_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
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
                    pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
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
            "missing_elements": missing_elements,
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
            "Dietary Assessment": [
                "dietary",
                "nutrition",
                "dietician",
                "nutritional assessment",
                "caloric intake",
            ],
        },
        risk_level="high",
    ),
    "E44": DiagnosisRule(
        code="E44",
        description="Protein-calorie malnutrition",
        required_elements=["BMI", "Albumin", "Weight Loss"],
        keywords={
            "BMI": ["bmi", "body mass index", "underweight"],
            "Albumin": ["albumin", "hypoalbuminemia", "low albumin"],
            "Weight Loss": ["weight loss", "malnourished", "poor nutrition"],
        },
        risk_level="high",
    ),
    # Sepsis (A41.9)
    "A41.9": DiagnosisRule(
        code="A41.9",
        description="Sepsis, unspecified organism",
        required_elements=[
            "SIRS Criteria",
            "Infection Source",
            "Lab Results",
            "Vital Signs",
        ],
        keywords={
            "SIRS Criteria": ["sirs", "systemic inflammatory response", "sepsis"],
            "Infection Source": [
                "infection",
                "bacteremia",
                "source",
                "culture positive",
                "infected",
                "pneumonia",
                "uti",
                "urinary tract infection",
                "cellulitis",
                "abscess",
            ],
            "Lab Results": [
                "wbc",
                "white blood cell",
                "lactate",
                "procalcitonin",
                "blood culture",
            ],
            "Vital Signs": [
                "fever",
                "temperature",
                "tachycardia",
                "heart rate",
                "hypotension",
                "blood pressure",
            ],
        },
        risk_level="high",
    ),
    # Congestive Heart Failure (I50.9, I50.23, I50.33)
    "I50.9": DiagnosisRule(
        code="I50.9",
        description="Heart failure, unspecified",
        required_elements=[
            "Ejection Fraction",
            "Symptoms",
            "Physical Exam",
            "Chest X-ray",
        ],
        keywords={
            "Ejection Fraction": [
                "ejection fraction",
                "ef",
                "lvef",
                "systolic function",
            ],
            "Symptoms": ["dyspnea", "shortness of breath", "sob", "orthopnea", "edema"],
            "Physical Exam": [
                "rales",
                "crackles",
                "s3",
                "jvd",
                "jugular venous distension",
                "peripheral edema",
            ],
            "Chest X-ray": ["chest x-ray", "cxr", "pulmonary edema", "cardiomegaly"],
        },
        risk_level="high",
    ),
    "I50.23": DiagnosisRule(
        code="I50.23",
        description="Acute on chronic systolic heart failure",
        required_elements=["Ejection Fraction", "Acute Symptoms", "Prior CHF History"],
        keywords={
            "Ejection Fraction": ["ejection fraction", "ef", "lvef", "reduced ef"],
            "Acute Symptoms": ["acute", "decompensated", "worsening", "exacerbation"],
            "Prior CHF History": [
                "history of heart failure",
                "chronic heart failure",
                "prior chf",
            ],
        },
        risk_level="high",
    ),
    "I50.33": DiagnosisRule(
        code="I50.33",
        description="Acute on chronic diastolic heart failure",
        required_elements=[
            "Ejection Fraction",
            "Acute Symptoms",
            "Diastolic Dysfunction",
        ],
        keywords={
            "Ejection Fraction": ["ejection fraction", "ef", "preserved ef", "hfpef"],
            "Acute Symptoms": ["acute", "decompensated", "worsening"],
            "Diastolic Dysfunction": ["diastolic", "diastolic dysfunction", "hfpef"],
        },
        risk_level="high",
    ),
    # Acute Kidney Injury (N17.9)
    "N17.9": DiagnosisRule(
        code="N17.9",
        description="Acute kidney injury, unspecified",
        required_elements=[
            "Creatinine",
            "Baseline Renal Function",
            "Urine Output",
            "Etiology",
        ],
        keywords={
            "Creatinine": [
                "creatinine",
                "cr",
                "serum creatinine",
                "elevated creatinine",
            ],
            "Baseline Renal Function": [
                "baseline",
                "baseline creatinine",
                "prior renal function",
            ],
            "Urine Output": ["urine output", "oliguria", "anuria", "decreased urine"],
            "Etiology": ["prerenal", "intrinsic", "postrenal", "cause", "aki cause"],
        },
        risk_level="high",
    ),
    # Respiratory Failure (J96.00, J96.90)
    "J96.00": DiagnosisRule(
        code="J96.00",
        description="Acute respiratory failure, unspecified",
        required_elements=[
            "ABG Results",
            "Oxygen Saturation",
            "Respiratory Rate",
            "Clinical Presentation",
        ],
        keywords={
            "ABG Results": ["abg", "arterial blood gas", "pao2", "paco2", "ph"],
            "Oxygen Saturation": [
                "oxygen saturation",
                "spo2",
                "o2 sat",
                "hypoxemia",
                "hypoxia",
            ],
            "Respiratory Rate": [
                "respiratory rate",
                "rr",
                "tachypnea",
                "respiratory distress",
            ],
            "Clinical Presentation": [
                "respiratory failure",
                "dyspnea",
                "respiratory distress",
                "shortness of breath",
            ],
        },
        risk_level="high",
    ),
    "J96.90": DiagnosisRule(
        code="J96.90",
        description="Respiratory failure, unspecified",
        required_elements=["Oxygen Requirement", "Clinical Status", "Etiology"],
        keywords={
            "Oxygen Requirement": [
                "oxygen",
                "supplemental oxygen",
                "ventilation",
                "cpap",
                "bipap",
            ],
            "Clinical Status": [
                "respiratory status",
                "work of breathing",
                "respiratory distress",
            ],
            "Etiology": ["pneumonia", "copd", "asthma", "pulmonary", "cause"],
        },
        risk_level="high",
    ),
}


def score_note_defensibility(
    note_text: str,
    diagnosis_codes: List[str],
    structured_data: Optional[Dict[str, Any]] = None,
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
            "summary": "Insufficient data for evaluation",
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
                "risk_level": rule.risk_level,
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
            diagnoses.append(
                {
                    "code": code,
                    "description": "Unknown diagnosis code",
                    "evidence_present": None,
                    "missing_elements": [],
                    "found_elements": [],
                    "risk_level": "unknown",
                }
            )

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
        "summary": summary,
    }
