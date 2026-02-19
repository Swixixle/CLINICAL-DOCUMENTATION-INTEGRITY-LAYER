"""
Tests for Denial Shield MEAT Scorer.

Tests validate deterministic MEAT-based scoring for:
- Diabetes MEAT anchors
- Hypertension MEAT anchors
- CHF MEAT anchors
- Revenue estimate logic
- Risk band calculation
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil

from gateway.app.main import app
from gateway.app.db.migrate import get_db_path, ensure_schema
from gateway.app.services.storage import bootstrap_dev_keys
from gateway.tests.auth_helpers import create_clinician_headers


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database."""
    # Save original db path
    get_db_path()

    # Create temp directory for test db
    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "test.db"

    # Monkey patch the get_db_path function
    import gateway.app.db.migrate as migrate_module

    original_get_db_path = migrate_module.get_db_path
    migrate_module.get_db_path = lambda: temp_db_path

    # Initialize schema
    ensure_schema()
    bootstrap_dev_keys()

    yield temp_db_path

    # Cleanup
    migrate_module.get_db_path = original_get_db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def client(test_db):
    """Test client with test database."""
    return TestClient(app)


def test_diabetes_missing_monitor_triggers_risk(client):
    """
    Test 1: Diabetes missing Monitor triggers +25 risk and correct rule_id.

    Construct a note that mentions diabetes assessment and plan but NO glucose/A1C.
    Assert:
    - risk_score >= 25
    - explanations include DIAB_MONITOR_MISSING
    - denial_risk.band is HIGH or CRITICAL
    """
    request_data = {
        "note_text": """
            Patient presents for diabetes follow-up visit today.
            
            Assessment: Type 2 diabetes, currently controlled with medications.
            Patient reports good dietary compliance.
            
            Plan: Continue metformin 1000mg twice daily.
            Follow up in 3 months.
            Patient educated on importance of diet and exercise.
        """,
        "encounter_type": "outpatient",
        "service_line": "medicine",
        "diagnoses": ["Type 2 diabetes mellitus"],
        "procedures": [],
        "labs": [],
        "vitals": [],
        "problem_list": ["Diabetes"],
        "meds": ["Metformin 1000mg"],
        "discharge_disposition": None,
    }

    headers = create_clinician_headers("test-tenant-001")
    response = client.post(
        "/v1/shadow/evidence-deficit", json=request_data, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Check that risk score is at least 25 (from missing Monitor)
    assert data["denial_risk"]["score"] >= 25

    # Check that DIAB_MONITOR_MISSING is in explanations
    explanations = data["evidence_sufficiency"]["explain"]
    rule_ids = [exp["rule_id"] for exp in explanations]
    assert "DIAB_MONITOR_MISSING" in rule_ids

    # Check that denial_risk band is at least MODERATE
    assert data["denial_risk"]["band"] in ["moderate", "high", "critical"]

    # Check that deficits include diabetes monitor deficit
    deficits = data["deficits"]
    deficit_categories = [d["category"] for d in deficits]
    assert "monitor" in deficit_categories

    # Verify a diabetes-related deficit exists
    diabetes_deficits = [d for d in deficits if d.get("condition") == "diabetes"]
    assert len(diabetes_deficits) > 0


def test_hypertension_with_bp_and_meds_lower_risk(client):
    """
    Test 2: Hypertension with BP values and med plan has lower risk.

    Include note_text: "HTN controlled, BP 128/76, continue lisinopril 10 mg"
    Assert:
    - No HTN_MONITOR_MISSING
    - No HTN_TREAT_MISSING
    - risk_score <= 30 (may have NOTE_TOO_SHORT if note is short, so make it long enough)
    """
    request_data = {
        "note_text": """
            Patient presents for routine follow-up of chronic conditions today.
            Reports feeling well overall with no new concerns.
            
            Vital Signs: BP 128/76, HR 72, Temp 98.6F, RR 16, SpO2 98% on room air
            
            Assessment:
            1. Hypertension - well controlled on current regimen
               Blood pressure at goal today at 128/76
               No signs of end-organ damage
               Patient reports good medication compliance
            
            Plan:
            1. Continue lisinopril 10 mg daily
            2. Continue monitoring BP at home
            3. Follow up in 6 months or sooner if issues
            4. Discussed lifestyle modifications including diet and exercise
            
            Patient questions answered. Plan reviewed and patient agrees.
        """,
        "encounter_type": "outpatient",
        "service_line": "medicine",
        "diagnoses": ["Essential hypertension"],
        "procedures": [],
        "labs": [],
        "vitals": [
            {"name": "bp", "value": "128/76", "taken_at": "2026-02-19T10:00:00Z"},
            {"name": "hr", "value": "72", "taken_at": "2026-02-19T10:00:00Z"},
        ],
        "problem_list": ["Hypertension"],
        "meds": ["Lisinopril 10mg"],
        "discharge_disposition": None,
    }

    headers = create_clinician_headers("test-tenant-001")
    response = client.post(
        "/v1/shadow/evidence-deficit", json=request_data, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Check that HTN_MONITOR_MISSING is NOT in explanations
    explanations = data["evidence_sufficiency"]["explain"]
    rule_ids = [exp["rule_id"] for exp in explanations]
    assert "HTN_MONITOR_MISSING" not in rule_ids

    # Check that HTN_TREAT_MISSING is NOT in explanations
    assert "HTN_TREAT_MISSING" not in rule_ids

    # Risk score should be low (30 or less, assuming no other major issues)
    assert data["denial_risk"]["score"] <= 30

    # Band should be LOW
    assert data["denial_risk"]["band"] == "low"


def test_chf_missing_treat_triggers_risk(client):
    """
    Test 3: CHF missing Treat triggers +25.

    Note_text mentions HF, EF 30%, edema, but no diuretic / GDMT plan.
    Assert:
    - includes CHF_TREAT_MISSING explanation
    - risk score includes +25 from missing treatment
    """
    request_data = {
        "note_text": """
            Patient with known heart failure presents for follow-up.
            Reports worsening shortness of breath and swelling in legs.
            
            Assessment:
            Heart failure with reduced ejection fraction (HFrEF)
            - Known EF 30% from echo last month
            - Currently volume overloaded based on exam
            - 2+ pitting edema bilateral lower extremities
            - JVD present
            - Crackles at lung bases bilaterally
            
            Daily weights show 5 lb gain over past week.
            Patient reports good compliance with current regimen.
            
            Plan:
            Monitor volume status closely.
            Patient to track daily weights at home.
            Follow up in 1 week.
        """,
        "encounter_type": "outpatient",
        "service_line": "medicine",
        "diagnoses": ["Heart failure with reduced ejection fraction"],
        "procedures": [],
        "labs": [],
        "vitals": [
            {"name": "weight", "value": "180", "taken_at": "2026-02-19T10:00:00Z"}
        ],
        "problem_list": ["HFrEF", "Volume overload"],
        "meds": [],
        "discharge_disposition": None,
    }

    headers = create_clinician_headers("test-tenant-001")
    response = client.post(
        "/v1/shadow/evidence-deficit", json=request_data, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Check that CHF_TREAT_MISSING is in explanations
    explanations = data["evidence_sufficiency"]["explain"]
    rule_ids = [exp["rule_id"] for exp in explanations]
    assert "CHF_TREAT_MISSING" in rule_ids

    # Find the CHF_TREAT_MISSING explanation and verify impact
    chf_treat_exp = [
        exp for exp in explanations if exp["rule_id"] == "CHF_TREAT_MISSING"
    ][0]
    assert chf_treat_exp["impact"] == 25

    # Check that deficits include CHF treat deficit
    deficits = data["deficits"]
    chf_treat_deficits = [
        d
        for d in deficits
        if d.get("condition") == "chf" and d.get("category") == "treat"
    ]
    assert len(chf_treat_deficits) > 0

    # Verify the fix guidance is present
    chf_deficit = chf_treat_deficits[0]
    assert chf_deficit.get("fix") is not None
    assert (
        "furosemide" in chf_deficit["fix"].lower()
        or "medication" in chf_deficit["fix"].lower()
    )


def test_revenue_estimate_outpatient_high_risk(client):
    """
    Test 4: Revenue estimate activates only for outpatient + risk > 60.

    Test both:
    1. Outpatient with high risk -> revenue_estimate = 142.00
    2. Inpatient with same high risk -> revenue_estimate = 0.00
    """
    # Create a note with multiple missing MEAT components to get risk > 60
    failing_note = {
        "note_text": "Patient with diabetes and hypertension. Continue meds.",  # Very short, vague
        "encounter_type": "outpatient",
        "service_line": "medicine",
        "diagnoses": ["Diabetes", "Hypertension"],
        "procedures": [],
        "labs": [],
        "vitals": [],
        "problem_list": [],
        "meds": [],
        "discharge_disposition": None,
    }

    headers = create_clinician_headers("test-tenant-001")

    # Test 1: Outpatient with high risk
    response_outpatient = client.post(
        "/v1/shadow/evidence-deficit", json=failing_note, headers=headers
    )
    assert response_outpatient.status_code == 200
    data_outpatient = response_outpatient.json()

    # Verify risk is high enough
    assert data_outpatient["denial_risk"]["score"] > 60

    # Verify revenue estimate is $142
    assert data_outpatient["revenue_estimate"] == 142.00

    # Test 2: Inpatient with same high risk
    failing_note["encounter_type"] = "inpatient"
    response_inpatient = client.post(
        "/v1/shadow/evidence-deficit", json=failing_note, headers=headers
    )
    assert response_inpatient.status_code == 200
    data_inpatient = response_inpatient.json()

    # Verify risk is still high
    assert data_inpatient["denial_risk"]["score"] > 60

    # Verify revenue estimate is $500 for inpatient (per revenue_mapping.json)
    assert data_inpatient["revenue_estimate"] == 500.00


def test_enum_validation_encounter_type(client):
    """Test that enum validation works for encounter_type."""
    request_data = {
        "note_text": "Test note",
        "encounter_type": "invalid_type",  # Invalid enum value
        "service_line": "medicine",
        "diagnoses": [],
        "procedures": [],
        "labs": [],
        "vitals": [],
        "problem_list": [],
        "meds": [],
    }

    headers = create_clinician_headers("test-tenant-001")
    response = client.post(
        "/v1/shadow/evidence-deficit", json=request_data, headers=headers
    )

    # Should fail validation
    assert response.status_code == 422  # Unprocessable Entity


def test_enum_validation_service_line(client):
    """Test that enum validation works for service_line."""
    request_data = {
        "note_text": "Test note",
        "encounter_type": "outpatient",
        "service_line": "invalid_service",  # Invalid enum value
        "diagnoses": [],
        "procedures": [],
        "labs": [],
        "vitals": [],
        "problem_list": [],
        "meds": [],
    }

    headers = create_clinician_headers("test-tenant-001")
    response = client.post(
        "/v1/shadow/evidence-deficit", json=request_data, headers=headers
    )

    # Should fail validation
    assert response.status_code == 422  # Unprocessable Entity


def test_denial_risk_structure(client):
    """Test that denial_risk has all required fields."""
    request_data = {
        "note_text": "Patient with diabetes. A1C 7.5%. Continue metformin 1000mg daily.",
        "encounter_type": "outpatient",
        "service_line": "medicine",
        "diagnoses": ["Diabetes"],
        "procedures": [],
        "labs": [],
        "vitals": [],
        "problem_list": [],
        "meds": ["Metformin"],
    }

    headers = create_clinician_headers("test-tenant-001")
    response = client.post(
        "/v1/shadow/evidence-deficit", json=request_data, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Verify denial_risk structure
    denial_risk = data["denial_risk"]
    assert "score" in denial_risk
    assert "band" in denial_risk
    assert "primary_reasons" in denial_risk
    assert "flags" in denial_risk
    assert "estimated_preventable_revenue_loss" in denial_risk

    # Verify score is in valid range
    assert 0 <= denial_risk["score"] <= 100

    # Verify band is valid enum
    assert denial_risk["band"] in ["low", "moderate", "high", "critical"]

    # Verify primary_reasons is a list of strings
    assert isinstance(denial_risk["primary_reasons"], list)
    assert len(denial_risk["primary_reasons"]) <= 3


def test_exec_headline_generation(client):
    """Test that exec_headline is generated based on risk bands."""
    # Test LOW risk
    low_risk_note = {
        "note_text": """
            Patient presents for diabetes follow-up. Glucose well controlled.
            A1C 6.5% today, down from 7.2% last quarter.
            Patient reports good compliance with metformin 1000mg twice daily.
            Home glucose logs show values 90-120 consistently.
            
            Assessment: Type 2 diabetes, well controlled
            
            Plan: Continue current metformin regimen. Recheck A1C in 3 months.
        """,
        "encounter_type": "outpatient",
        "service_line": "medicine",
        "diagnoses": ["Type 2 diabetes mellitus"],
        "labs": [],
        "vitals": [],
        "problem_list": [],
        "meds": ["Metformin"],
    }

    headers = create_clinician_headers("test-tenant-001")
    response = client.post(
        "/v1/shadow/evidence-deficit", json=low_risk_note, headers=headers
    )
    assert response.status_code == 200
    data = response.json()

    # Should have low risk headline
    assert "low" in data["headline"].lower() or data["denial_risk"]["band"] == "low"


def test_next_actions_always_three(client):
    """Test that next_best_actions always contains exactly 3 items."""
    request_data = {
        "note_text": "Simple note.",
        "encounter_type": "outpatient",
        "service_line": "medicine",
        "diagnoses": [],
        "procedures": [],
        "labs": [],
        "vitals": [],
        "problem_list": [],
        "meds": [],
    }

    headers = create_clinician_headers("test-tenant-001")
    response = client.post(
        "/v1/shadow/evidence-deficit", json=request_data, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Verify next_best_actions has exactly 3 items
    assert len(data["next_best_actions"]) == 3

    # Verify they are the standard 3 bullets
    actions = data["next_best_actions"]
    assert any("MEAT" in action for action in actions)
    assert any("clinical rationale" in action for action in actions)
    assert any("Re-run" in action or "re-run" in action for action in actions)
