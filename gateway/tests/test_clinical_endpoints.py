"""
Tests for clinical documentation endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from gateway.tests.auth_helpers import create_clinician_headers
from pathlib import Path
import tempfile
import shutil

from gateway.app.main import app
from gateway.app.db.migrate import get_db_path, ensure_schema
from gateway.app.services.storage import bootstrap_dev_keys


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


def test_clinical_documentation_certificate_generation(client):
    """Test generating a clinical documentation integrity certificate."""
    request_data = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-turbo",
        "prompt_version": "clinical-v1.2",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": "Patient presents with headache. Vital signs stable. Assessed as tension headache.",
        "human_reviewed": True,
        "human_reviewer_id": "DR-TEST-001",
        "encounter_id": "ENC-2026-02-18-TEST",
        "patient_reference": "PATIENT-TEST-001",
    }

    headers = create_clinician_headers("test-tenant-001")
    response = client.post(
        "/v1/clinical/documentation", json=request_data, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert "certificate_id" in data
    assert "verify_url" in data
    assert "certificate" in data

    # Check certificate structure
    cert = data["certificate"]
    assert cert["certificate_id"] == data["certificate_id"]
    assert cert["encounter_id"] == request_data["encounter_id"]
    assert cert["model_version"] == request_data["model_version"]
    assert cert["prompt_version"] == request_data["prompt_version"]
    assert (
        cert["governance_policy_version"] == request_data["governance_policy_version"]
    )
    assert cert["human_reviewed"]
    assert "note_hash" in cert
    assert "patient_hash" in cert
    assert "timestamp" in cert
    assert "signature" in cert
    assert "integrity_chain" in cert

    # Check integrity chain
    assert "chain_hash" in cert["integrity_chain"]


def test_clinical_documentation_no_phi_stored(client):
    """Test that no PHI is stored in plaintext."""
    request_data = {
        "model_name": "claude-3",
        "model_version": "claude-3",
        "prompt_version": "clinical-v1.0",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": "This note contains sensitive clinical information.",
        "human_reviewed": False,
        "encounter_id": "ENC-TEST-002",
        "patient_reference": "PATIENT-SENSITIVE-DATA",
    }

    headers = create_clinician_headers("test-tenant-002")
    response = client.post(
        "/v1/clinical/documentation", json=request_data, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    # Verify no raw PHI in response
    response_str = str(data)
    assert "PATIENT-SENSITIVE-DATA" not in response_str
    assert "This note contains sensitive clinical information" not in response_str

    # Verify hashes are present (not raw data)
    cert = data["certificate"]
    assert len(cert["note_hash"]) == 64  # SHA-256 hex length
    assert len(cert["patient_hash"]) == 64  # SHA-256 hex length


def test_clinical_documentation_human_review_tracking(client):
    """Test human review flag tracking."""
    # Test with human review
    request_with_review = {
        "model_name": "gpt-4",
        "model_version": "gpt-4",
        "prompt_version": "clinical-v1.1",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": "Test note with review",
        "human_reviewed": True,
        "human_reviewer_id": "DR-REVIEWER-001",
        "encounter_id": "ENC-TEST-003-A",
        "patient_reference": "PATIENT-TEST-003",
    }

    headers = create_clinician_headers("test-tenant-003")
    response = client.post(
        "/v1/clinical/documentation", json=request_with_review, headers=headers
    )
    assert response.status_code == 200
    cert = response.json()["certificate"]
    assert cert["human_reviewed"]

    # Test without human review
    request_without_review = {
        "model_name": "gpt-4",
        "model_version": "gpt-4",
        "prompt_version": "clinical-v1.1",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": "Test note without review",
        "human_reviewed": False,
        "encounter_id": "ENC-TEST-003-B",
        "patient_reference": "PATIENT-TEST-003",
    }

    response = client.post(
        "/v1/clinical/documentation", json=request_without_review, headers=headers
    )
    assert response.status_code == 200
    cert = response.json()["certificate"]
    assert not cert["human_reviewed"]


def test_mock_summarizer_endpoint(client):
    """Test mock AI summarizer endpoint."""
    request_data = {
        "clinical_text": "Patient complains of chest pain. ECG normal. No signs of MI.",
        "note_type": "emergency_note",
        "ai_model": "gpt-4-turbo",
    }

    response = client.post("/v1/mock/summarize", json=request_data)

    assert response.status_code == 200
    data = response.json()

    assert "summary" in data
    assert "model_used" in data
    assert "prompt_version" in data
    assert "governance_policy_version" in data

    assert data["model_used"] == request_data["ai_model"]
    assert len(data["summary"]) > 0


def test_clinical_documentation_governance_metadata(client):
    """Test that governance metadata is properly included."""
    request_data = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-turbo",
        "prompt_version": "clinical-v1.2",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": "Test note for governance",
        "human_reviewed": True,
        "human_reviewer_id": "DR-TEST-004",
        "encounter_id": "ENC-TEST-004",
        "patient_reference": "PATIENT-TEST-004",
    }

    headers = create_clinician_headers("test-tenant-004")
    response = client.post(
        "/v1/clinical/documentation", json=request_data, headers=headers
    )

    assert response.status_code == 200
    data = response.json()

    cert = data["certificate"]
    # Check that certificate contains governance fields
    assert (
        cert["governance_policy_version"] == request_data["governance_policy_version"]
    )
    assert cert["model_version"] == request_data["model_version"]
    assert cert["prompt_version"] == request_data["prompt_version"]


def test_clinical_documentation_different_note_types(client):
    """Test certificate generation for different scenarios."""
    scenarios = [
        "progress_note",
        "consultation",
        "discharge_summary",
        "admission_note",
        "procedure_note",
    ]

    headers = create_clinician_headers("test-tenant-005")

    for idx, scenario in enumerate(scenarios):
        request_data = {
            "model_name": "gpt-4",
            "model_version": "gpt-4",
            "prompt_version": "clinical-v1.0",
            "governance_policy_version": "CDOC-Policy-v1",
            "note_text": f"This is a {scenario} generated by AI.",
            "human_reviewed": True,
            "human_reviewer_id": "DR-TEST-005",
            "encounter_id": f"ENC-{scenario}",
            "patient_reference": f"PATIENT-{scenario}",
        }

        response = client.post(
            "/v1/clinical/documentation", json=request_data, headers=headers
        )

        assert response.status_code == 200, f"Failed for scenario: {scenario}"
        data = response.json()
        assert data["certificate"]["encounter_id"] == f"ENC-{scenario}"


def test_clinical_documentation_hash_consistency(client):
    """Test that identical notes produce identical hashes."""
    note_text = "Identical clinical note for hash testing."
    patient_ref = "PATIENT-HASH-TEST"

    headers = create_clinician_headers("test-tenant-006")

    request_data = {
        "model_name": "gpt-4",
        "model_version": "gpt-4",
        "prompt_version": "clinical-v1.0",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": note_text,
        "human_reviewed": False,
        "encounter_id": "ENC-HASH-TEST-1",
        "patient_reference": patient_ref,
    }

    # Generate first certificate
    response1 = client.post(
        "/v1/clinical/documentation", json=request_data, headers=headers
    )
    assert response1.status_code == 200
    cert1 = response1.json()["certificate"]

    # Generate second certificate with same note and patient
    request_data["encounter_id"] = "ENC-HASH-TEST-2"  # Different encounter
    response2 = client.post(
        "/v1/clinical/documentation", json=request_data, headers=headers
    )
    assert response2.status_code == 200
    cert2 = response2.json()["certificate"]

    # Hashes should be identical for same inputs
    assert cert1["note_hash"] == cert2["note_hash"]
    assert cert1["patient_hash"] == cert2["patient_hash"]

    # But certificates should be different (different encounter, timestamp, etc.)
    assert cert1["certificate_id"] != cert2["certificate_id"]


def test_clinical_documentation_required_fields(client):
    """Test that required fields are validated."""
    # Missing model_version (required field)
    incomplete_request = {
        "prompt_version": "clinical-v1.0",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": "Test note",
        "human_reviewed": False,
    }

    headers = create_clinician_headers("test-tenant-007")
    response = client.post(
        "/v1/clinical/documentation", json=incomplete_request, headers=headers
    )
    assert response.status_code == 422  # Validation error
