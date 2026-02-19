"""
Tests for CFO Leakage Report endpoint.

Tests validate the /v1/shadow/leakage-report endpoint:
- Batch processing of notes
- Revenue aggregation
- Risk distribution
- Top rules by impact
- Top conditions by impact
- No PHI in output (hashes only)
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


@pytest.fixture
def client(test_db):
    """Create test client."""
    return TestClient(app)


def test_leakage_report_basic(client):
    """
    Test basic leakage report with batch of notes.
    """
    notes = [
        {
            "note_text": "Patient with diabetes. Continue metformin 500mg BID. A1C 7.2%. Blood glucose well controlled.",
            "encounter_type": "outpatient",
            "service_line": "medicine",
            "diagnoses": ["Diabetes"],
            "procedures": [],
            "labs": [],
            "vitals": [],
            "problem_list": [],
            "meds": [],
            "discharge_disposition": None,
        },
        {
            "note_text": "Patient with diabetes and hypertension. Continue meds.",  # High risk
            "encounter_type": "outpatient",
            "service_line": "medicine",
            "diagnoses": ["Diabetes", "Hypertension"],
            "procedures": [],
            "labs": [],
            "vitals": [],
            "problem_list": [],
            "meds": [],
            "discharge_disposition": None,
        },
        {
            "note_text": "Patient with CHF. Weight stable, no edema. Furosemide 40mg daily. BP 120/80. EF 35%. Assessment: HFrEF stable. Plan: continue GDMT.",
            "encounter_type": "outpatient",
            "service_line": "cardiology",
            "diagnoses": ["CHF"],
            "procedures": [],
            "labs": [],
            "vitals": [],
            "problem_list": [],
            "meds": [],
            "discharge_disposition": None,
        },
    ]

    headers = create_clinician_headers("test-tenant-001")
    response = client.post(
        "/v1/shadow/leakage-report", json={"notes": notes}, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Verify all required fields
    assert "total_notes" in data
    assert "total_revenue_at_risk" in data
    assert "risk_distribution" in data
    assert "top_rules_by_impact" in data
    assert "top_conditions" in data
    assert "sample_high_risk_notes" in data
    assert "generated_at" in data
    assert "tenant_id" in data

    # Verify counts
    assert data["total_notes"] == 3
    assert data["tenant_id"] == "test-tenant-001"

    # Verify risk distribution
    risk_dist = data["risk_distribution"]
    assert "low" in risk_dist
    assert "moderate" in risk_dist
    assert "high" in risk_dist
    assert "critical" in risk_dist
    assert sum(risk_dist.values()) == 3

    # Verify top rules format
    top_rules = data["top_rules_by_impact"]
    assert isinstance(top_rules, list)
    assert len(top_rules) <= 10
    if top_rules:
        assert "rule_id" in top_rules[0]
        assert "count" in top_rules[0]
        assert "total_revenue_impact" in top_rules[0]

    # Verify top conditions format
    top_conditions = data["top_conditions"]
    assert isinstance(top_conditions, list)
    if top_conditions:
        assert "condition" in top_conditions[0]
        assert "count" in top_conditions[0]
        assert "total_revenue_impact" in top_conditions[0]

    # Verify sample hashes format
    sample_hashes = data["sample_high_risk_notes"]
    assert isinstance(sample_hashes, list)
    assert len(sample_hashes) <= 20
    # Hashes should be hex strings
    for hash_val in sample_hashes:
        assert isinstance(hash_val, str)
        assert len(hash_val) == 64  # SHA-256 produces 64 hex characters


def test_leakage_report_no_phi_in_output(client):
    """
    Test that leakage report does NOT include plaintext note_text.
    Only hashes should be returned.
    """
    notes = [
        {
            "note_text": "SENSITIVE PHI DATA: Patient John Doe SSN 123-45-6789 with diabetes.",
            "encounter_type": "outpatient",
            "service_line": "medicine",
            "diagnoses": ["Diabetes"],
            "procedures": [],
            "labs": [],
            "vitals": [],
            "problem_list": [],
            "meds": [],
            "discharge_disposition": None,
        }
    ]

    headers = create_clinician_headers("test-tenant-001")
    response = client.post(
        "/v1/shadow/leakage-report", json={"notes": notes}, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Convert entire response to string and check for PHI
    response_str = str(data)
    assert "John Doe" not in response_str
    assert "123-45-6789" not in response_str
    assert "SENSITIVE PHI DATA" not in response_str


def test_leakage_report_revenue_calculation_outpatient_only(client):
    """
    Test that revenue is only calculated for outpatient encounters.
    Inpatient encounters should have $0 revenue impact per current revenue_mapping.json.
    """
    notes = [
        {
            "note_text": "Patient with diabetes. Brief note.",  # High risk
            "encounter_type": "outpatient",
            "service_line": "medicine",
            "diagnoses": ["Diabetes"],
            "procedures": [],
            "labs": [],
            "vitals": [],
            "problem_list": [],
            "meds": [],
            "discharge_disposition": None,
        },
        {
            "note_text": "Patient with diabetes. Brief note.",  # Same risk, different encounter type
            "encounter_type": "inpatient",
            "service_line": "medicine",
            "diagnoses": ["Diabetes"],
            "procedures": [],
            "labs": [],
            "vitals": [],
            "problem_list": [],
            "meds": [],
            "discharge_disposition": None,
        },
    ]

    headers = create_clinician_headers("test-tenant-001")
    response = client.post(
        "/v1/shadow/leakage-report", json={"notes": notes}, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Total revenue should be from outpatient only (high risk = 142.00)
    # Inpatient contributes 0
    assert data["total_notes"] == 2
    # Outpatient with high risk should be $142, inpatient should be $0
    assert data["total_revenue_at_risk"] == 142.0


def test_leakage_report_empty_batch(client):
    """
    Test error handling for empty batch.
    """
    headers = create_clinician_headers("test-tenant-001")
    response = client.post(
        "/v1/shadow/leakage-report", json={"notes": []}, headers=headers
    )

    assert response.status_code == 400


def test_leakage_report_high_risk_sample_limit(client):
    """
    Test that high-risk sample is limited to 20 notes.
    """
    # Create 25 high-risk notes
    notes = []
    for i in range(25):
        notes.append(
            {
                "note_text": f"Patient {i} with diabetes. Brief note.",  # High risk
                "encounter_type": "outpatient",
                "service_line": "medicine",
                "diagnoses": ["Diabetes"],
                "procedures": [],
                "labs": [],
                "vitals": [],
                "problem_list": [],
                "meds": [],
                "discharge_disposition": None,
            }
        )

    headers = create_clinician_headers("test-tenant-001")
    response = client.post(
        "/v1/shadow/leakage-report", json={"notes": notes}, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Verify sample is limited to 20
    assert len(data["sample_high_risk_notes"]) == 20


def test_leakage_report_top_rules_sorted_by_impact(client):
    """
    Test that top rules are sorted by total revenue impact (descending).
    """
    notes = []
    # Create multiple notes with different issues
    for i in range(5):
        notes.append(
            {
                "note_text": "Patient with diabetes. Continue meds.",  # Missing MEAT
                "encounter_type": "outpatient",
                "service_line": "medicine",
                "diagnoses": ["Diabetes"],
                "procedures": [],
                "labs": [],
                "vitals": [],
                "problem_list": [],
                "meds": [],
                "discharge_disposition": None,
            }
        )

    headers = create_clinician_headers("test-tenant-001")
    response = client.post(
        "/v1/shadow/leakage-report", json={"notes": notes}, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Verify top rules are sorted
    top_rules = data["top_rules_by_impact"]
    if len(top_rules) > 1:
        for i in range(len(top_rules) - 1):
            assert (
                top_rules[i]["total_revenue_impact"]
                >= top_rules[i + 1]["total_revenue_impact"]
            )
