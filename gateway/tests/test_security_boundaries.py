"""
Security tests for CDIL threat model validation.

Tests critical security boundaries identified in THREAT_MODEL_AND_TRUST_GUARANTEES.md:
- Cross-tenant isolation (tenant boundary enforcement)
- PHI leakage prevention (zero-PHI discipline)
- Authorization enforcement
"""

import pytest
from fastapi.testclient import TestClient

from gateway.tests.auth_helpers import create_clinician_headers, create_auditor_headers
from pathlib import Path
import tempfile
import shutil
import json

from gateway.app.main import app
from gateway.app.db.migrate import get_db_path, ensure_schema
from gateway.app.services.storage import bootstrap_dev_keys


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database."""
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


def test_cross_tenant_read_isolation(client):
    """
    Test that tenant B cannot retrieve tenant A's certificates.
    
    Security requirement: X-Tenant-Id header enforcement must prevent
    cross-tenant data access.
    
    Expected behavior: 404 (not 403) to avoid revealing certificate existence.
    """
    # Issue certificate for tenant A
    request_data_a = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-clinical",
        "prompt_version": "v1.0",
        "governance_policy_version": "clinical-v1",
        "note_text": "Patient presents with symptoms requiring evaluation.",
        "human_reviewed": True,
        "encounter_id": "ENC-ALPHA-001"
    }
    
    response_a = client.post("/v1/clinical/documentation", json=request_data_a, headers=create_clinician_headers("tenant-hospital-alpha"))
    assert response_a.status_code == 200
    cert_a_id = response_a.json()["certificate_id"]
    
    # Verify tenant A can retrieve their own certificate
    get_response_a = client.get(
        f"/v1/certificates/{cert_a_id}",
        headers=create_clinician_headers("tenant-hospital-alpha")
    )
    assert get_response_a.status_code == 200
    assert get_response_a.json()["tenant_id"] == "tenant-hospital-alpha"
    
    # Attempt to retrieve tenant A's cert with tenant B's auth
    get_response_b = client.get(
        f"/v1/certificates/{cert_a_id}",
        headers=create_clinician_headers("tenant-hospital-beta")
    )
    
    # Must return 404 (not 403) to avoid revealing existence
    assert get_response_b.status_code == 404
    assert "not found" in get_response_b.json()["message"].lower()


def test_cross_tenant_verify_isolation(client):
    """
    Test that tenant B cannot verify tenant A's certificates.
    
    Security requirement: Verification endpoint must enforce tenant isolation.
    """
    # Issue certificate for tenant A
    request_data_a = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-clinical",
        "prompt_version": "v1.0",
        "governance_policy_version": "clinical-v1",
        "note_text": "Follow-up visit for chronic condition management.",
        "human_reviewed": False,
        "encounter_id": "ENC-GAMMA-001"
    }
    
    response_a = client.post("/v1/clinical/documentation", json=request_data_a, headers=create_clinician_headers("tenant-clinic-gamma"))
    assert response_a.status_code == 200
    cert_a_id = response_a.json()["certificate_id"]
    
    # Verify tenant A can verify their own certificate
    verify_response_a = client.post(
        f"/v1/certificates/{cert_a_id}/verify",
        headers=create_auditor_headers("tenant-clinic-gamma")
    )
    assert verify_response_a.status_code == 200
    assert verify_response_a.json()["valid"] == True
    
    # Attempt to verify tenant A's cert with tenant B's auth (auditor role)
    verify_response_b = client.post(
        f"/v1/certificates/{cert_a_id}/verify",
        headers=create_auditor_headers("tenant-clinic-delta")
    )
    
    # Must return 404 to avoid revealing existence
    assert verify_response_b.status_code == 404


def test_missing_tenant_header_rejected(client):
    """
    Test that requests without JWT authentication are rejected.
    
    Security requirement: All retrieval/verification endpoints must
    require authentication (JWT with tenant_id).
    """
    # Issue certificate first
    request_data = {
        "model_name": "gpt-4",
        "model_version": "gpt-4",
        "prompt_version": "v1.0",
        "governance_policy_version": "v1",
        "note_text": "Test note",
        "human_reviewed": False
    }
    
    response = client.post("/v1/clinical/documentation", json=request_data, headers=create_clinician_headers("test-tenant"))
    assert response.status_code == 200
    cert_id = response.json()["certificate_id"]
    
    # Attempt to retrieve without authentication
    get_response = client.get(f"/v1/certificates/{cert_id}")
    assert get_response.status_code == 401
    
    # Attempt to verify without authentication
    verify_response = client.post(f"/v1/certificates/{cert_id}/verify")
    assert verify_response.status_code == 401


def test_phi_pattern_detection_ssn(client):
    """
    Test that SSN patterns in note_text are rejected.
    
    Security requirement: PHI pattern detection must reject obvious PHI.
    """
    request_data = {
        "model_name": "gpt-4",
        "model_version": "gpt-4",
        "prompt_version": "v1.0",
        "governance_policy_version": "v1",
        "note_text": "Patient SSN is 123-45-6789 for insurance.",
        "human_reviewed": False
    }
    
    response = client.post("/v1/clinical/documentation", json=request_data, headers=create_clinician_headers("test-tenant"))
    assert response.status_code == 400
    assert response.json()["error"] == "phi_detected_in_note_text"
    assert "ssn" in response.json()["detected_patterns"]


def test_phi_pattern_detection_phone(client):
    """
    Test that phone number patterns in note_text are rejected.
    
    Security requirement: PHI pattern detection must reject phone numbers.
    """
    request_data = {
        "model_name": "gpt-4",
        "model_version": "gpt-4",
        "prompt_version": "v1.0",
        "governance_policy_version": "v1",
        "note_text": "Contact patient at 555-123-4567 for follow-up.",
        "human_reviewed": False
    }
    
    response = client.post("/v1/clinical/documentation", json=request_data, headers=create_clinician_headers("test-tenant"))
    assert response.status_code == 400
    assert response.json()["error"] == "phi_detected_in_note_text"
    assert "phone" in response.json()["detected_patterns"]


def test_phi_pattern_detection_email(client):
    """
    Test that email patterns in note_text are rejected.
    
    Security requirement: PHI pattern detection must reject email addresses.
    """
    request_data = {
        "model_name": "gpt-4",
        "model_version": "gpt-4",
        "prompt_version": "v1.0",
        "governance_policy_version": "v1",
        "note_text": "Patient email is john.doe@example.com for portal access.",
        "human_reviewed": False
    }
    
    response = client.post("/v1/clinical/documentation", json=request_data, headers=create_clinician_headers("test-tenant"))
    assert response.status_code == 400
    assert response.json()["error"] == "phi_detected_in_note_text"
    assert "email" in response.json()["detected_patterns"]


def test_note_text_never_persisted(client, test_db):
    """
    Test that note_text is never stored in the database.
    
    Security requirement: Zero-PHI discipline - only hashes stored.
    """
    sensitive_note_text = "Extremely sensitive clinical information about patient condition."
    
    request_data = {
        "model_name": "gpt-4",
        "model_version": "gpt-4",
        "prompt_version": "v1.0",
        "governance_policy_version": "v1",
        "note_text": sensitive_note_text,
        "human_reviewed": True,
        "patient_reference": "MRN-SENSITIVE-12345",
        "human_reviewer_id": "DR-SENSITIVE-ID"
    }
    
    response = client.post("/v1/clinical/documentation", json=request_data, headers=create_clinician_headers("test-tenant"))
    assert response.status_code == 200
    
    # Directly inspect database
    import sqlite3
    conn = sqlite3.connect(test_db)
    cursor = conn.execute("SELECT certificate_json FROM certificates")
    rows = cursor.fetchall()
    conn.close()
    
    # Check that no row contains the sensitive plaintext
    for row in rows:
        cert_json = row[0]
        assert sensitive_note_text not in cert_json, "Plaintext note_text found in database!"
        assert "MRN-SENSITIVE-12345" not in cert_json, "Plaintext patient_reference found in database!"
        assert "DR-SENSITIVE-ID" not in cert_json, "Plaintext reviewer_id found in database!"
        
        # Verify hashes ARE present
        cert_dict = json.loads(cert_json)
        assert "note_hash" in cert_dict, "note_hash missing"
        assert cert_dict["note_hash"].startswith("sha256:") or len(cert_dict["note_hash"]) == 64, "Invalid note_hash format"


def test_patient_and_reviewer_hashed(client):
    """
    Test that patient_reference and reviewer_id are hashed, not stored plaintext.
    
    Security requirement: All PHI fields must be hashed.
    """
    request_data = {
        "model_name": "gpt-4",
        "model_version": "gpt-4",
        "prompt_version": "v1.0",
        "governance_policy_version": "v1",
        "note_text": "Standard clinical assessment note.",
        "human_reviewed": True,
        "patient_reference": "MRN-HASH-TEST-001",
        "human_reviewer_id": "DR-HASH-TEST-001"
    }
    
    response = client.post("/v1/clinical/documentation", json=request_data, headers=create_clinician_headers("test-tenant"))
    assert response.status_code == 200
    
    cert = response.json()["certificate"]
    
    # Check that hashes are present
    assert "note_hash" in cert
    assert "patient_hash" in cert
    assert "reviewer_hash" in cert
    
    # Verify hashes are not the plaintext values
    assert cert["patient_hash"] != "MRN-HASH-TEST-001"
    assert cert["reviewer_hash"] != "DR-HASH-TEST-001"
    
    # Verify hash format (64 hex chars for SHA-256)
    assert len(cert["note_hash"]) == 64
    assert all(c in "0123456789abcdef" for c in cert["note_hash"])


def test_chain_integrity_per_tenant(client):
    """
    Test that integrity chains are tenant-specific and don't cross-link.
    
    Security requirement: Tenant isolation in chain linkage.
    """
    # Issue first cert for tenant A
    request_a1 = {
        "model_name": "gpt-4",
        "model_version": "gpt-4",
        "prompt_version": "v1.0",
        "governance_policy_version": "v1",
        "note_text": "First note for alpha.",
        "human_reviewed": False
    }
    
    response_a1 = client.post("/v1/clinical/documentation", json=request_a1, headers=create_clinician_headers("tenant-chain-alpha"))
    assert response_a1.status_code == 200
    cert_a1 = response_a1.json()["certificate"]
    
    # First cert should have null previous_hash
    assert cert_a1["integrity_chain"]["previous_hash"] is None
    
    # Issue first cert for tenant B
    request_b1 = {
        "model_name": "gpt-4",
        "model_version": "gpt-4",
        "prompt_version": "v1.0",
        "governance_policy_version": "v1",
        "note_text": "First note for beta.",
        "human_reviewed": False
    }
    
    response_b1 = client.post("/v1/clinical/documentation", json=request_b1, headers=create_clinician_headers("tenant-chain-beta"))
    assert response_b1.status_code == 200
    cert_b1 = response_b1.json()["certificate"]
    
    # Tenant B's first cert should also have null previous_hash (independent chain)
    assert cert_b1["integrity_chain"]["previous_hash"] is None
    
    # Issue second cert for tenant A
    request_a2 = {
        "model_name": "gpt-4",
        "model_version": "gpt-4",
        "prompt_version": "v1.0",
        "governance_policy_version": "v1",
        "note_text": "Second note for alpha.",
        "human_reviewed": False
    }
    
    response_a2 = client.post("/v1/clinical/documentation", json=request_a2, headers=create_clinician_headers("tenant-chain-alpha"))
    assert response_a2.status_code == 200
    cert_a2 = response_a2.json()["certificate"]
    
    # Second cert for A should link to first cert for A
    assert cert_a2["integrity_chain"]["previous_hash"] == cert_a1["integrity_chain"]["chain_hash"]
    
    # Verify it does NOT link to tenant B's chain
    assert cert_a2["integrity_chain"]["previous_hash"] != cert_b1["integrity_chain"]["chain_hash"]


def test_signature_verification_valid(client):
    """
    Test that valid certificates pass signature verification.
    
    Security requirement: Cryptographic integrity validation.
    """
    request_data = {
        "model_name": "gpt-4",
        "model_version": "gpt-4",
        "prompt_version": "v1.0",
        "governance_policy_version": "v1",
        "note_text": "Test note for signature verification.",
        "human_reviewed": True
    }
    
    response = client.post("/v1/clinical/documentation", json=request_data, headers=create_clinician_headers("tenant-sig-test"))
    assert response.status_code == 200
    cert_id = response.json()["certificate_id"]
    
    # Verify certificate (same tenant, auditor role required)
    verify_response = client.post(
        f"/v1/certificates/{cert_id}/verify",
        headers=create_auditor_headers("tenant-sig-test")
    )
    
    assert verify_response.status_code == 200
    verify_result = verify_response.json()
    
    assert verify_result["valid"] == True
    assert verify_result["certificate_id"] == cert_id
    assert len(verify_result["failures"]) == 0


def test_query_certificates_tenant_isolation(client):
    """
    Test that certificate queries are tenant-scoped.
    
    Security requirement: Query endpoints must enforce tenant isolation.
    """
    # Issue cert for tenant A
    request_a = {
        "model_name": "gpt-4",
        "model_version": "gpt-4",
        "prompt_version": "v1.0",
        "governance_policy_version": "v1",
        "note_text": "Note for alpha.",
        "human_reviewed": False
    }
    
    response_a = client.post("/v1/clinical/documentation", json=request_a, headers=create_clinician_headers("tenant-query-alpha"))
    assert response_a.status_code == 200
    cert_a_id = response_a.json()["certificate_id"]
    
    # Issue cert for tenant B
    request_b = {
        "model_name": "gpt-4",
        "model_version": "gpt-4",
        "prompt_version": "v1.0",
        "governance_policy_version": "v1",
        "note_text": "Note for beta.",
        "human_reviewed": False
    }
    
    response_b = client.post("/v1/clinical/documentation", json=request_b, headers=create_clinician_headers("tenant-query-beta"))
    assert response_b.status_code == 200
    cert_b_id = response_b.json()["certificate_id"]
    
    # Query as tenant A (auditor role required)
    query_a = client.post(
        "/v1/certificates/query",
        headers=create_auditor_headers("tenant-query-alpha")
    )
    assert query_a.status_code == 200
    results_a = query_a.json()
    
    # Should only return tenant A's certificates
    assert results_a["returned_count"] == 1
    assert results_a["certificates"][0]["certificate_id"] == cert_a_id
    assert all(c["tenant_id"] == "tenant-query-alpha" for c in results_a["certificates"])
    
    # Query as tenant B (auditor role required)
    query_b = client.post(
        "/v1/certificates/query",
        headers=create_auditor_headers("tenant-query-beta")
    )
    assert query_b.status_code == 200
    results_b = query_b.json()
    
    # Should only return tenant B's certificates
    assert results_b["returned_count"] == 1
    assert results_b["certificates"][0]["certificate_id"] == cert_b_id
    assert all(c["tenant_id"] == "tenant-query-beta" for c in results_b["certificates"])
