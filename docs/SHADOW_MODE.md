# Shadow Mode - Evidence Deficit Intelligence

## Overview

Shadow Mode is a **read-only** feature that analyzes clinical documentation to identify evidence deficits, documentation gaps, and denial risk factors. It provides actionable recommendations without integrating with EHR systems or storing PHI.

## What It Is

Shadow Mode Evidence Deficit Intelligence (EDI) is a rule-based analysis system that:

- **Analyzes** clinical note text + structured clinical context (labs, vitals, diagnoses, etc.)
- **Identifies** documentation deficits, clinical inconsistencies, and denial risk factors
- **Estimates** preventable revenue loss using heuristic rules
- **Recommends** specific documentation additions to reduce denial risk
- **Provides** dashboard-ready output for executives and board presentations

## What It Is NOT

Shadow Mode is **not**:

- ❌ **Clinical decision support** - It does not diagnose or recommend treatments
- ❌ **Billing/coding advice** - It does not provide CPT/ICD-10 coding guidance
- ❌ **A guarantee** - Results are heuristic risk indicators, not predictions
- ❌ **EHR integration** - It does not read from or write to EHR systems
- ❌ **PHI storage** - It does not store clinical notes in plaintext

## Key Features

### 1. Evidence Sufficiency Scoring

- **Score**: 0-100 scale measuring documentation completeness
- **Band**: Risk categorization (green/yellow/red)
- **Explanations**: Rule-based rationale for each score adjustment

### 2. Evidence Deficits

Identifies missing or inconsistent documentation:

- **Documentation deficits**: Missing HPI elements, attestation, severity indicators
- **Clinical inconsistencies**: Diagnoses without supporting labs/vitals
- **Coding vulnerabilities**: High-scrutiny diagnoses lacking objective evidence

Each deficit includes:
- Title and category
- Payer perspective (why it might be denied)
- Provider guidance (what to add)
- Confidence score

### 3. Denial Risk Assessment

- **Risk flags**: High/medium/low severity indicators
- **Revenue estimates**: Conservative and optimistic loss ranges
- **Assumptions**: Transparent methodology for estimates

### 4. Actionable Recommendations

- Top 3 "next best actions" for providers
- Prioritized by confidence and impact
- Specific, actionable guidance

## Security & Privacy

### Authentication

- **JWT-required**: All requests must include valid JWT token
- **Tenant isolation**: Tenant ID is derived from JWT, never from request body
- **Role-based**: Accessible to clinician, auditor, and admin roles

### PHI Protection

- **No plaintext storage**: Clinical notes are never stored in plaintext
- **Hash-only persistence**: Only SHA-256 hashes stored (if audit trail needed)
- **Stateless analysis**: No patient identifiers retained after request completes

## API Specification

### Endpoint

```
POST /v1/shadow/evidence-deficit
```

### Authentication

Include JWT token in Authorization header:

```
Authorization: Bearer <jwt_token>
```

### Request Schema

```json
{
  "note_text": "Clinical note content...",
  "encounter_type": "inpatient|observation|outpatient|ed",
  "service_line": "medicine|surgery|icu|other",
  "diagnoses": ["Diagnosis 1", "Diagnosis 2"],
  "procedures": ["Procedure 1"],
  "labs": [
    {
      "name": "albumin",
      "value": 2.8,
      "unit": "g/dL",
      "collected_at": "2026-02-18T10:00:00Z"
    }
  ],
  "vitals": [
    {
      "name": "bp",
      "value": "120/80",
      "taken_at": "2026-02-18T09:00:00Z"
    }
  ],
  "problem_list": ["Problem 1", "Problem 2"],
  "meds": ["Med 1", "Med 2"],
  "discharge_disposition": "Home"
}
```

### Response Schema

```json
{
  "tenant_id": "from-jwt-claim",
  "request_hash": "sha256-hex-of-canonicalized-request",
  "generated_at_utc": "2026-02-18T16:30:00.000Z",
  "evidence_sufficiency": {
    "score": 75,
    "band": "yellow",
    "explain": [
      {
        "rule_id": "RULE-002",
        "impact": -10,
        "reason": "Missing HPI elements: timing/duration"
      }
    ]
  },
  "deficits": [
    {
      "id": "DEF-002",
      "title": "Incomplete History of Present Illness",
      "category": "documentation",
      "why_payer_denies": "Incomplete HPI fails to establish medical necessity timeline",
      "what_to_add": "Add timing/duration to HPI section",
      "evidence_refs": [
        {
          "type": "note_text",
          "key": "hpi_elements",
          "value": ["timing/duration"]
        }
      ],
      "confidence": 0.8
    }
  ],
  "denial_risk": {
    "flags": [
      {
        "id": "DR-002",
        "severity": "med",
        "rationale": "Missing HPI elements increase documentation denial risk",
        "rule_id": "RULE-002"
      }
    ],
    "estimated_preventable_revenue_loss": {
      "low": 2250.0,
      "high": 4500.0,
      "assumptions": [
        "Based on inpatient encounter type",
        "Base revenue per encounter: $15,000",
        "Risk flags: 0 high, 1 medium, 0 low",
        "Denial probabilities: high=30%, med=15%, low=5%",
        "These are heuristic estimates, not guarantees"
      ]
    }
  },
  "audit": {
    "ruleset_version": "EDI-v1",
    "inputs_redacted": true
  },
  "dashboard_title": "Evidence Deficit Intelligence",
  "headline": "Preventable Revenue Loss: $2,250–$4,500 (estimated)",
  "next_best_actions": [
    "Add timing/duration to HPI section",
    "Document clinical interpretation of albumin=2.1 g/dL",
    "Add physician attestation/signature to note"
  ]
}
```

## Example Usage

### Using cURL

```bash
# Set your JWT token
TOKEN="your-jwt-token-here"

# Make request
curl -X POST "https://your-cdil-instance.com/v1/shadow/evidence-deficit" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "note_text": "Patient presents with severe malnutrition. Weight loss 15 lbs over 2 weeks. Albumin 2.1 noted. Plan: nutrition consult.",
    "encounter_type": "inpatient",
    "service_line": "medicine",
    "diagnoses": ["Severe malnutrition"],
    "procedures": [],
    "labs": [
      {
        "name": "albumin",
        "value": 2.1,
        "unit": "g/dL",
        "collected_at": "2026-02-18T10:00:00Z"
      }
    ],
    "vitals": [
      {
        "name": "weight",
        "value": "140",
        "taken_at": "2026-02-18T09:00:00Z"
      }
    ],
    "problem_list": ["Malnutrition"],
    "meds": ["Multivitamin"],
    "discharge_disposition": null
  }'
```

### Using Python

```python
import requests

# JWT token from your identity provider
token = "your-jwt-token-here"

# Request payload
payload = {
    "note_text": "Patient presents with severe malnutrition...",
    "encounter_type": "inpatient",
    "service_line": "medicine",
    "diagnoses": ["Severe malnutrition"],
    "labs": [
        {
            "name": "albumin",
            "value": 2.1,
            "unit": "g/dL",
            "collected_at": "2026-02-18T10:00:00Z"
        }
    ],
    "vitals": [],
    "problem_list": ["Malnutrition"],
    "meds": ["Multivitamin"],
    "discharge_disposition": None
}

# Make request
response = requests.post(
    "https://your-cdil-instance.com/v1/shadow/evidence-deficit",
    headers={"Authorization": f"Bearer {token}"},
    json=payload
)

# Parse response
if response.status_code == 200:
    result = response.json()
    print(f"Score: {result['evidence_sufficiency']['score']}/100")
    print(f"Risk Band: {result['evidence_sufficiency']['band']}")
    print(f"Deficits: {len(result['deficits'])}")
    print(f"Revenue at Risk: ${result['denial_risk']['estimated_preventable_revenue_loss']['low']:,.0f} - ${result['denial_risk']['estimated_preventable_revenue_loss']['high']:,.0f}")
else:
    print(f"Error: {response.status_code}")
    print(response.json())
```

## Explainability Requirement

Every score adjustment, deficit, and risk flag includes:

1. **Rule ID**: Unique identifier for traceability (e.g., "RULE-002")
2. **Impact**: Numeric score impact (negative for penalties)
3. **Reason**: Human-readable explanation
4. **Evidence References**: What data was examined
5. **Confidence**: How certain the system is (0.0-1.0)

This ensures all outputs are **auditable** and **explainable**.

## Scoring Methodology

### Starting Score: 100 (Perfect Documentation)

Penalties are applied for:

- **Empty/insufficient note** (-40 points)
- **Missing HPI elements** (-5 points per missing element)
- **Missing attestation** (-10 points)
- **Unsupported high-scrutiny diagnosis** (-10 points per diagnosis)
- **Diagnoses without objective data** (-15 points)
- **Critical labs not discussed** (-5 points per lab)

### Score Bands

- **Green (80-100)**: Low denial risk, well-documented
- **Yellow (60-79)**: Medium risk, some gaps identified
- **Red (0-59)**: High risk, significant deficits

## Revenue Estimation

Revenue loss estimates are **heuristic**, not predictive. They use:

- Base revenue per encounter (varies by encounter type)
- Risk flag severity counts
- Denial probability multipliers (conservative)
- High-scrutiny diagnosis adjustments

**All assumptions are included in the response** for transparency.

## Limitations & Disclaimers

### This System Does NOT:

1. **Replace clinical judgment** - Providers must make all clinical decisions
2. **Guarantee outcomes** - Estimates are heuristic risk indicators
3. **Provide coding advice** - Not a substitute for certified coders
4. **Predict payer behavior** - Individual payer policies vary
5. **Ensure payment** - Many factors affect claim adjudication

### This System DOES:

1. **Identify common patterns** - Based on known denial-prone areas
2. **Suggest improvements** - Actionable documentation guidance
3. **Estimate risk** - Conservative revenue loss ranges
4. **Support quality** - Help providers document thoroughly

## Support & Feedback

For questions or issues:

- **Technical support**: Contact your CDIL administrator
- **Rule suggestions**: Submit via your organization's feedback channel
- **Security concerns**: Report immediately to security@your-org.com

## Version History

- **EDI-v1** (Current): Initial release with 6 base rules
  - Rule-001: Empty/insufficient note detection
  - Rule-002: HPI element completeness
  - Rule-003: Physician attestation
  - Rule-004: High-scrutiny diagnosis support
  - Rule-005: Objective data for diagnoses
  - Rule-006: Critical lab discussion

Future versions may add additional rules based on customer feedback and evidence.
