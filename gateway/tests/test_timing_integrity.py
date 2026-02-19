"""
Tests for timing integrity (finalization gate) feature.
"""

import pytest
from fastapi.testclient import TestClient

from gateway.tests.auth_helpers import create_clinician_headers, create_auditor_headers
from pathlib import Path
import tempfile
import shutil
from datetime import datetime, timedelta
import json

from gateway.app.main import app
from gateway.app.db.migrate import get_db_path, ensure_schema, get_connection
from gateway.app.services.storage import bootstrap_dev_keys


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database."""
    get_db_path()
    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "test.db"

    import gateway.app.db.migrate as migrate_module

    original_get_db_path = migrate_module.get_db_path
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


def test_timing_integrity_backdating_detected(client):
    """Test that backdating is detected when finalized_at > ehr_referenced_at."""
    # Issue a certificate
    request = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-test",
        "prompt_version": "v1.0",
        "governance_policy_version": "policy-v1",
        "note_text": "Test note for backdating detection",
        "human_reviewed": True,
    }

    response = client.post(
        "/v1/clinical/documentation",
        json=request,
        headers=create_clinician_headers("timing-test-hospital"),
    )
    assert response.status_code == 200

    cert_data = response.json()
    cert_id = cert_data["certificate_id"]
    certificate = cert_data["certificate"]

    # Verify certificate has finalized_at set
    assert "finalized_at" in certificate
    assert certificate["ehr_referenced_at"] is None  # Not set yet

    # Simulate backdating: set ehr_referenced_at to BEFORE finalized_at
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT certificate_json FROM certificates WHERE certificate_id = ?",
            (cert_id,),
        )
        row = cursor.fetchone()
        cert = json.loads(row["certificate_json"])

        # Set EHR reference to 1 hour before finalization (backdating scenario)
        finalized_at = datetime.fromisoformat(
            cert["finalized_at"].replace("Z", "+00:00")
        )
        ehr_referenced_at = (
            (finalized_at - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        )
        cert["ehr_referenced_at"] = ehr_referenced_at
        cert["ehr_commit_id"] = "fake-commit-123"

        conn.execute(
            "UPDATE certificates SET certificate_json = ? WHERE certificate_id = ?",
            (json.dumps(cert), cert_id),
        )
        conn.commit()
    finally:
        conn.close()

    # Verify the certificate - should fail timing check
    verify_response = client.post(
        f"/v1/certificates/{cert_id}/verify",
        headers=create_auditor_headers("timing-test-hospital"),
    )
    assert verify_response.status_code == 200

    verify_data = verify_response.json()
    assert verify_data["valid"] is False

    # Check that timing failure is present
    timing_failures = [f for f in verify_data["failures"] if f["check"] == "timing"]
    assert len(timing_failures) == 1
    assert timing_failures[0]["error"] == "finalized_after_ehr_reference"

    # Check human-friendly report
    report = verify_data["human_friendly_report"]
    assert report["status"] == "FAIL"
    assert (
        "backdating" in report["summary"].lower()
        or "timing" in report["summary"].lower()
    )
    assert (
        "backdated" in report["reason"].lower()
        or "temporal" in report["reason"].lower()
    )


def test_timing_integrity_valid_sequence(client):
    """Test that valid timing sequence passes verification."""
    # Issue a certificate
    request = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-test",
        "prompt_version": "v1.0",
        "governance_policy_version": "policy-v1",
        "note_text": "Test note for valid timing",
        "human_reviewed": True,
    }

    response = client.post(
        "/v1/clinical/documentation",
        json=request,
        headers=create_clinician_headers("timing-test-hospital"),
    )
    assert response.status_code == 200

    cert_id = response.json()["certificate_id"]

    # Set ehr_referenced_at to AFTER finalized_at (valid scenario)
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT certificate_json FROM certificates WHERE certificate_id = ?",
            (cert_id,),
        )
        row = cursor.fetchone()
        cert = json.loads(row["certificate_json"])

        # Set EHR reference to 1 hour AFTER finalization (valid scenario)
        finalized_at = datetime.fromisoformat(
            cert["finalized_at"].replace("Z", "+00:00")
        )
        ehr_referenced_at = (
            (finalized_at + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        )
        cert["ehr_referenced_at"] = ehr_referenced_at
        cert["ehr_commit_id"] = "valid-commit-456"

        conn.execute(
            "UPDATE certificates SET certificate_json = ? WHERE certificate_id = ?",
            (json.dumps(cert), cert_id),
        )
        conn.commit()
    finally:
        conn.close()

    # Verify the certificate - should pass (same tenant)
    verify_response = client.post(
        f"/v1/certificates/{cert_id}/verify",
        headers=create_auditor_headers("timing-test-hospital"),
    )
    assert verify_response.status_code == 200

    verify_data = verify_response.json()
    assert verify_data["valid"] is True

    # Check human-friendly report
    report = verify_data["human_friendly_report"]
    assert report["status"] == "PASS"


def test_timing_integrity_no_ehr_reference(client):
    """Test that certificate without ehr_referenced_at still passes."""
    # Issue a certificate
    request = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-test",
        "prompt_version": "v1.0",
        "governance_policy_version": "policy-v1",
        "note_text": "Test note without EHR reference",
        "human_reviewed": True,
    }

    response = client.post(
        "/v1/clinical/documentation",
        json=request,
        headers=create_clinician_headers("timing-no-ref-hospital"),
    )
    assert response.status_code == 200

    cert_id = response.json()["certificate_id"]

    # Verify without setting ehr_referenced_at
    verify_response = client.post(
        f"/v1/certificates/{cert_id}/verify",
        headers=create_auditor_headers("timing-no-ref-hospital"),
    )
    assert verify_response.status_code == 200

    verify_data = verify_response.json()
    assert verify_data["valid"] is True  # Should pass since ehr_referenced_at is None

    # No timing failures
    timing_failures = [f for f in verify_data["failures"] if f["check"] == "timing"]
    assert len(timing_failures) == 0


def test_certificate_includes_governance_fields(client):
    """Test that new governance fields are included in certificate."""
    request = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-test",
        "prompt_version": "v1.0",
        "governance_policy_version": "policy-v2.0",
        "note_text": "Test note for governance fields",
        "human_reviewed": True,
    }

    response = client.post(
        "/v1/clinical/documentation",
        json=request,
        headers=create_clinician_headers("timing-test-hospital"),
    )
    assert response.status_code == 200

    certificate = response.json()["certificate"]

    # Check new timing fields
    assert "finalized_at" in certificate
    assert "ehr_referenced_at" in certificate
    assert "ehr_commit_id" in certificate

    # Check new governance fields
    assert "policy_hash" in certificate
    assert "governance_summary" in certificate

    # Verify governance_summary contains useful info
    summary = certificate["governance_summary"]
    assert "policy-v2.0" in summary
    assert "gpt-4-test" in summary
