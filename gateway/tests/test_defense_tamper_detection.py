"""
Tests for Courtroom Defense Mode - Phase 2: Tamper Detection Simulation.

Tests:
- Simulate alteration endpoint detects tampering
- Any mutation causes verification failure
- Cross-tenant attempts return 404
- Demo scenario generates complete presentation
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil

from gateway.app.main import app
from gateway.app.db.migrate import ensure_schema
from gateway.app.services.storage import bootstrap_dev_keys
from gateway.tests.auth_helpers import create_clinician_headers


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database."""
    import gateway.app.db.migrate as migrate_module

    original_get_db_path = migrate_module.get_db_path

    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "test.db"

    migrate_module.get_db_path = lambda: temp_db_path
    ensure_schema()
    bootstrap_dev_keys()

    yield temp_db_path

    migrate_module.get_db_path = original_get_db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def client(test_db):
    """Test client with test database."""
    return TestClient(app)


def issue_test_certificate(client, tenant_id="hospital-alpha"):
    """Helper to issue a test certificate."""
    request_data = {
        "model_name": "gpt-4",
        "model_version": "2024-01-15",
        "prompt_version": "clinical-v1.0",
        "governance_policy_version": "CDOC-v1",
        "note_text": "Patient presents with headache. Vital signs stable. Assessed as tension headache.",
        "human_reviewed": True,
        "human_reviewer_id": "DR-TEST-001",
        "encounter_id": "ENC-TEST-001",
    }

    headers = create_clinician_headers(tenant_id)
    response = client.post(
        "/v1/clinical/documentation", json=request_data, headers=headers
    )

    assert response.status_code == 200
    return response.json()


def test_simulate_alteration_detects_tampering(client):
    """
    Test that simulate-alteration endpoint detects when note content is modified.
    """
    # Issue a certificate
    cert_response = issue_test_certificate(client, tenant_id="hospital-alpha")
    cert_id = cert_response["certificate_id"]

    # Simulate alteration with modified note text
    altered_request = {
        "certificate_id": cert_id,
        "modified_note_text": "Patient presents with SEVERE headache and visual disturbances.",
    }

    headers = create_clinician_headers("hospital-alpha")
    response = client.post(
        "/v1/defense/simulate-alteration", json=altered_request, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Should detect tampering
    assert data["tamper_detected"] is True
    assert data["reason"] == "NOTE_HASH_MISMATCH"
    assert data["verification_failed"] is True

    # Hashes should differ
    assert data["original_hash"] != data["modified_hash"]

    # Summary should indicate tampering
    assert (
        "Tampering detected" in data["summary"]
        or "tampering detected" in data["summary"]
    )


def test_simulate_alteration_no_tampering_if_identical(client):
    """
    Test that no tampering is detected if modified text is identical to original.
    """
    # Issue a certificate with known note text
    original_note = "Patient presents with headache. Vital signs stable. Assessed as tension headache."

    request_data = {
        "model_name": "gpt-4",
        "model_version": "2024-01-15",
        "prompt_version": "clinical-v1.0",
        "governance_policy_version": "CDOC-v1",
        "note_text": original_note,
        "human_reviewed": True,
        "human_reviewer_id": "DR-TEST-002",
        "encounter_id": "ENC-TEST-002",
    }

    headers = create_clinician_headers("hospital-alpha")
    cert_response = client.post(
        "/v1/clinical/documentation", json=request_data, headers=headers
    )
    assert cert_response.status_code == 200
    cert_id = cert_response.json()["certificate_id"]

    # Simulate alteration with IDENTICAL text
    altered_request = {
        "certificate_id": cert_id,
        "modified_note_text": original_note,  # Same as original
    }

    response = client.post(
        "/v1/defense/simulate-alteration", json=altered_request, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Should NOT detect tampering (identical content)
    assert data["tamper_detected"] is False
    assert data["reason"] == "NO_TAMPERING_DETECTED"

    # Hashes should match
    assert data["original_hash"] == data["modified_hash"]


def test_simulate_alteration_single_character_change_detected(client):
    """
    Test that even a single character change is detected.
    """
    # Issue a certificate
    original_note = "Patient has headache"

    request_data = {
        "model_name": "gpt-4",
        "model_version": "2024-01-15",
        "prompt_version": "clinical-v1.0",
        "governance_policy_version": "CDOC-v1",
        "note_text": original_note,
        "human_reviewed": False,
        "encounter_id": "ENC-TEST-003",
    }

    headers = create_clinician_headers("hospital-alpha")
    cert_response = client.post(
        "/v1/clinical/documentation", json=request_data, headers=headers
    )
    assert cert_response.status_code == 200
    cert_id = cert_response.json()["certificate_id"]

    # Change single character: "headache" -> "Headache" (capital H)
    modified_note = "Patient has Headache"

    altered_request = {"certificate_id": cert_id, "modified_note_text": modified_note}

    response = client.post(
        "/v1/defense/simulate-alteration", json=altered_request, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Should detect tampering from single character change
    assert data["tamper_detected"] is True
    assert data["original_hash"] != data["modified_hash"]


def test_simulate_alteration_cross_tenant_returns_404(client):
    """
    Test that attempting to simulate alteration on another tenant's certificate returns 404.
    """
    # Issue certificate for tenant A
    cert_response = issue_test_certificate(client, tenant_id="hospital-alpha")
    cert_id = cert_response["certificate_id"]

    # Try to access it from tenant B
    altered_request = {
        "certificate_id": cert_id,
        "modified_note_text": "Attempting cross-tenant access",
    }

    headers = create_clinician_headers("hospital-bravo")  # Different tenant
    response = client.post(
        "/v1/defense/simulate-alteration", json=altered_request, headers=headers
    )

    # Should return 404 (tenant isolation)
    assert response.status_code == 404
    response_data = response.json()
    # Check for error message (may be in 'detail' or directly in 'message')
    if "detail" in response_data:
        if isinstance(response_data["detail"], dict):
            assert "not found" in response_data["detail"]["message"].lower()
        else:
            assert "not found" in str(response_data["detail"]).lower()
    else:
        assert "not found" in str(response_data).lower()


def test_simulate_alteration_nonexistent_certificate_returns_404(client):
    """
    Test that simulating alteration on nonexistent certificate returns 404.
    """
    altered_request = {
        "certificate_id": "NONEXISTENT-CERT-ID",
        "modified_note_text": "Some text",
    }

    headers = create_clinician_headers("hospital-alpha")
    response = client.post(
        "/v1/defense/simulate-alteration", json=altered_request, headers=headers
    )

    assert response.status_code == 404


def test_demo_scenario_generates_complete_presentation(client):
    """
    Test that demo scenario endpoint generates a complete tamper-evident presentation.
    """
    headers = create_clinician_headers("hospital-alpha")
    response = client.get("/v1/defense/demo-scenario", headers=headers)

    assert response.status_code == 200
    data = response.json()

    # Check structure
    assert "demo_version" in data
    assert "scenario" in data
    assert "presentation_notes" in data

    # Check scenario steps
    scenario = data["scenario"]
    assert "step_1_original_certificate" in scenario
    assert "step_2_original_verification" in scenario
    assert "step_3_simulated_alteration" in scenario
    assert "step_4_tamper_verification" in scenario
    assert "step_5_summary" in scenario

    # Check step 1: Original certificate
    cert = scenario["step_1_original_certificate"]
    assert cert["certificate_id"] == "DEMO-CERT-001"
    assert cert["human_reviewed"] is True

    # Check step 2: Original verification (valid)
    verification = scenario["step_2_original_verification"]
    assert verification["status"] == "VALID"

    # Check step 3: Simulated alteration
    alteration = scenario["step_3_simulated_alteration"]
    assert "original_hash" in alteration
    assert "altered_hash" in alteration
    assert alteration["hash_match"] is False

    # Check step 4: Tamper verification (failed)
    tamper_check = scenario["step_4_tamper_verification"]
    assert tamper_check["status"] == "INVALID"
    assert "altered" in tamper_check["message"].lower()

    # Check step 5: Summary
    summary = scenario["step_5_summary"]
    assert "key_points" in summary
    assert "legal_implications" in summary
    assert len(summary["key_points"]) > 0

    # Check presentation notes
    notes = data["presentation_notes"]
    assert "audience" in notes
    assert "key_message" in notes


def test_demo_scenario_respects_tenant_context(client):
    """
    Test that demo scenario includes the authenticated tenant's ID.
    """
    # Request as tenant A
    headers_a = create_clinician_headers("hospital-alpha")
    response_a = client.get("/v1/defense/demo-scenario", headers=headers_a)
    assert response_a.status_code == 200
    assert response_a.json()["tenant_id"] == "hospital-alpha"

    # Request as tenant B
    headers_b = create_clinician_headers("hospital-bravo")
    response_b = client.get("/v1/defense/demo-scenario", headers=headers_b)
    assert response_b.status_code == 200
    assert response_b.json()["tenant_id"] == "hospital-bravo"


def test_simulate_alteration_with_whitespace_changes(client):
    """
    Test that whitespace changes (which don't affect medical meaning) are detected.

    Even formatting changes alter the hash, ensuring ANY modification is caught.
    """
    original_note = "Patient presents with headache."

    request_data = {
        "model_name": "gpt-4",
        "model_version": "2024-01-15",
        "prompt_version": "clinical-v1.0",
        "governance_policy_version": "CDOC-v1",
        "note_text": original_note,
        "human_reviewed": False,
        "encounter_id": "ENC-TEST-004",
    }

    headers = create_clinician_headers("hospital-alpha")
    cert_response = client.post(
        "/v1/clinical/documentation", json=request_data, headers=headers
    )
    assert cert_response.status_code == 200
    cert_id = cert_response.json()["certificate_id"]

    # Add extra whitespace
    modified_note = "Patient  presents  with  headache."  # Double spaces

    altered_request = {"certificate_id": cert_id, "modified_note_text": modified_note}

    response = client.post(
        "/v1/defense/simulate-alteration", json=altered_request, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Even whitespace changes should be detected
    assert data["tamper_detected"] is True


def test_simulate_alteration_requires_authentication(client):
    """
    Test that simulate-alteration endpoint requires authentication.
    """
    altered_request = {
        "certificate_id": "SOME-CERT-ID",
        "modified_note_text": "Some text",
    }

    # No auth headers
    response = client.post("/v1/defense/simulate-alteration", json=altered_request)

    # Should return 401 or 403
    assert response.status_code in [401, 403]


def test_demo_scenario_requires_authentication(client):
    """
    Test that demo-scenario endpoint requires authentication.
    """
    # No auth headers
    response = client.get("/v1/defense/demo-scenario")

    # Should return 401 or 403
    assert response.status_code in [401, 403]
