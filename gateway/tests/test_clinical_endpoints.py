"""
Tests for clinical documentation endpoints.
"""

import pytest
from fastapi.testclient import TestClient
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
    original_db = get_db_path()
    
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
        "clinician_id": "DR-TEST-001",
        "patient_id": "PATIENT-TEST-001",
        "encounter_id": "ENC-2026-02-18-TEST",
        "ai_vendor": "openai",
        "model_version": "gpt-4-turbo",
        "prompt_version": "clinical-v1.2",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": "Patient presents with headache. Vital signs stable. Assessed as tension headache.",
        "human_reviewed": True,
        "human_editor_id": "DR-TEST-001",
        "note_type": "progress_note",
        "environment": "dev"
    }
    
    response = client.post("/v1/clinical/documentation", json=request_data)
    
    assert response.status_code == 200
    data = response.json()
    
    # Check response structure
    assert "certificate_id" in data
    assert "verification_url" in data
    assert "hash_prefix" in data
    assert "certificate" in data
    
    # Check certificate structure
    cert = data["certificate"]
    assert cert["certificate_id"] == data["certificate_id"]
    assert cert["encounter_id"] == request_data["encounter_id"]
    assert cert["model_version"] == request_data["model_version"]
    assert cert["prompt_version"] == request_data["prompt_version"]
    assert cert["governance_policy_version"] == request_data["governance_policy_version"]
    assert cert["human_reviewed"] == True
    assert "note_hash" in cert
    assert "patient_hash" in cert
    assert "timestamp" in cert
    assert "signature" in cert
    assert "final_hash" in cert
    assert "governance_checks" in cert
    
    # Check governance checks were executed
    assert len(cert["governance_checks"]) > 0
    assert "phi_filter_executed" in cert["governance_checks"]
    

def test_clinical_documentation_no_phi_stored(client):
    """Test that no PHI is stored in plaintext."""
    request_data = {
        "clinician_id": "DR-TEST-002",
        "patient_id": "PATIENT-SENSITIVE-DATA",
        "encounter_id": "ENC-TEST-002",
        "ai_vendor": "anthropic",
        "model_version": "claude-3",
        "prompt_version": "clinical-v1.0",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": "This note contains sensitive clinical information.",
        "human_reviewed": False,
        "note_type": "consultation",
        "environment": "dev"
    }
    
    response = client.post("/v1/clinical/documentation", json=request_data)
    
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
        "clinician_id": "DR-TEST-003",
        "patient_id": "PATIENT-TEST-003",
        "encounter_id": "ENC-TEST-003-A",
        "ai_vendor": "openai",
        "model_version": "gpt-4",
        "prompt_version": "clinical-v1.1",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": "Test note with review",
        "human_reviewed": True,
        "human_editor_id": "DR-REVIEWER-001",
        "environment": "dev"
    }
    
    response = client.post("/v1/clinical/documentation", json=request_with_review)
    assert response.status_code == 200
    cert = response.json()["certificate"]
    assert cert["human_reviewed"] == True
    
    # Test without human review
    request_without_review = {
        "clinician_id": "DR-TEST-003",
        "patient_id": "PATIENT-TEST-003",
        "encounter_id": "ENC-TEST-003-B",
        "ai_vendor": "openai",
        "model_version": "gpt-4",
        "prompt_version": "clinical-v1.1",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": "Test note without review",
        "human_reviewed": False,
        "environment": "dev"
    }
    
    response = client.post("/v1/clinical/documentation", json=request_without_review)
    assert response.status_code == 200
    cert = response.json()["certificate"]
    assert cert["human_reviewed"] == False


def test_mock_summarizer_endpoint(client):
    """Test mock AI summarizer endpoint."""
    request_data = {
        "clinical_text": "Patient complains of chest pain. ECG normal. No signs of MI.",
        "note_type": "emergency_note",
        "ai_model": "gpt-4-turbo"
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
        "clinician_id": "DR-TEST-004",
        "patient_id": "PATIENT-TEST-004",
        "encounter_id": "ENC-TEST-004",
        "ai_vendor": "openai",
        "model_version": "gpt-4-turbo",
        "prompt_version": "clinical-v1.2",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": "Test note for governance",
        "human_reviewed": True,
        "human_editor_id": "DR-TEST-004",
        "note_type": "discharge_summary",
        "environment": "dev"
    }
    
    response = client.post("/v1/clinical/documentation", json=request_data)
    
    assert response.status_code == 200
    data = response.json()
    
    cert = data["certificate"]
    assert "governance_checks" in cert
    assert isinstance(cert["governance_checks"], list)
    
    # Verify expected governance checks
    expected_checks = [
        "phi_filter_executed",
        "hallucination_scan_executed",
        "bias_filter_executed"
    ]
    
    for check in expected_checks:
        assert check in cert["governance_checks"]


def test_clinical_documentation_different_note_types(client):
    """Test certificate generation for different note types."""
    note_types = [
        "progress_note",
        "consultation",
        "discharge_summary",
        "admission_note",
        "procedure_note"
    ]
    
    for note_type in note_types:
        request_data = {
            "clinician_id": "DR-TEST-005",
            "patient_id": f"PATIENT-{note_type}",
            "encounter_id": f"ENC-{note_type}",
            "ai_vendor": "openai",
            "model_version": "gpt-4",
            "prompt_version": "clinical-v1.0",
            "governance_policy_version": "CDOC-Policy-v1",
            "note_text": f"This is a {note_type} generated by AI.",
            "human_reviewed": True,
            "human_editor_id": "DR-TEST-005",
            "note_type": note_type,
            "environment": "dev"
        }
        
        response = client.post("/v1/clinical/documentation", json=request_data)
        
        assert response.status_code == 200, f"Failed for note_type: {note_type}"
        data = response.json()
        assert data["certificate"]["encounter_id"] == f"ENC-{note_type}"


def test_clinical_documentation_hash_consistency(client):
    """Test that identical notes produce identical hashes."""
    note_text = "Identical clinical note for hash testing."
    patient_id = "PATIENT-HASH-TEST"
    
    request_data = {
        "clinician_id": "DR-TEST-006",
        "patient_id": patient_id,
        "encounter_id": "ENC-HASH-TEST-1",
        "ai_vendor": "openai",
        "model_version": "gpt-4",
        "prompt_version": "clinical-v1.0",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": note_text,
        "human_reviewed": False,
        "environment": "dev"
    }
    
    # Generate first certificate
    response1 = client.post("/v1/clinical/documentation", json=request_data)
    assert response1.status_code == 200
    cert1 = response1.json()["certificate"]
    
    # Generate second certificate with same note and patient
    request_data["encounter_id"] = "ENC-HASH-TEST-2"  # Different encounter
    response2 = client.post("/v1/clinical/documentation", json=request_data)
    assert response2.status_code == 200
    cert2 = response2.json()["certificate"]
    
    # Hashes should be identical for same inputs
    assert cert1["note_hash"] == cert2["note_hash"]
    assert cert1["patient_hash"] == cert2["patient_hash"]
    
    # But certificates should be different (different encounter, timestamp, etc.)
    assert cert1["certificate_id"] != cert2["certificate_id"]


def test_clinical_documentation_required_fields(client):
    """Test that required fields are validated."""
    # Missing clinician_id
    incomplete_request = {
        "patient_id": "PATIENT-TEST",
        "encounter_id": "ENC-TEST",
        "ai_vendor": "openai",
        "model_version": "gpt-4",
        "prompt_version": "clinical-v1.0",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": "Test note",
        "human_reviewed": False,
        "environment": "dev"
    }
    
    response = client.post("/v1/clinical/documentation", json=incomplete_request)
    assert response.status_code == 422  # Validation error
