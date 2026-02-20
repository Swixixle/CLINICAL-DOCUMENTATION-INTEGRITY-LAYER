"""
Tests for clinical documentation integrity certificate endpoints.

Validates certificate issuance, retrieval, and verification for the CDIL system.
"""

import pytest
from fastapi.testclient import TestClient

from gateway.app.main import app
from gateway.app.db.migrate import ensure_schema
from gateway.tests.auth_helpers import create_clinician_headers, create_auditor_headers


@pytest.fixture(scope="module")
def client():
    """Create a test client with fresh database."""
    # Ensure schema exists
    ensure_schema()
    return TestClient(app)


def test_issue_certificate_minimal(client):
    """Test issuing a certificate with minimal required fields."""
    request = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-clinical-v1",
        "prompt_version": "soap-note-v1.0",
        "governance_policy_version": "clinical-v1.0",
        "note_text": "Patient presents with mild fever and cough. Assessment: likely viral URI. Plan: rest and fluids.",
        "human_reviewed": True,
        "human_reviewer_id": "test-reviewer-001",
    }
    headers = create_clinician_headers("hospital-alpha")

    response = client.post("/v1/clinical/documentation", json=request, headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert "certificate_id" in data
    assert "certificate" in data
    assert "verify_url" in data

    cert = data["certificate"]
    assert cert["tenant_id"] == "hospital-alpha"
    assert cert["model_version"] == "gpt-4-clinical-v1"
    assert cert["human_reviewed"] is True
    assert cert["note_hash"]  # Hash should exist
    assert len(cert["note_hash"]) == 64  # SHA-256 hex is 64 chars
    assert cert["patient_hash"] is None  # Not provided
    assert cert["reviewer_hash"] is not None  # Hashed from provided reviewer_id

    # Verify integrity chain
    assert "integrity_chain" in cert
    assert (
        "previous_hash" in cert["integrity_chain"]
    )  # May or may not be None depending on test order
    assert cert["integrity_chain"]["chain_hash"]

    # Verify signature
    assert "signature" in cert
    assert cert["signature"]["key_id"]
    assert cert["signature"]["algorithm"]
    assert cert["signature"]["signature"]


def test_issue_certificate_with_phi_fields(client):
    """Test issuing a certificate with all PHI fields (which should be hashed)."""
    request = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-clinical-v2",
        "prompt_version": "soap-note-v1.1",
        "governance_policy_version": "clinical-v2.0",
        "note_text": "Detailed clinical note with patient history and assessment.",
        "human_reviewed": True,
        "human_reviewer_id": "dr-jane-smith-12345",
        "patient_reference": "MRN-987654",
        "encounter_id": "enc-2026-02-18-001",
    }
    headers = create_clinician_headers("hospital-beta")

    response = client.post("/v1/clinical/documentation", json=request, headers=headers)
    assert response.status_code == 200

    data = response.json()
    cert = data["certificate"]

    # Verify all hashes are present
    assert cert["note_hash"]
    assert cert["patient_hash"]  # Should be hashed
    assert cert["reviewer_hash"]  # Should be hashed
    assert cert["encounter_id"] == "enc-2026-02-18-001"

    # Verify NO plaintext PHI in certificate
    cert_json = response.text
    assert "dr-jane-smith-12345" not in cert_json
    assert "MRN-987654" not in cert_json
    # Note: we can't check for note_text absence because it's only in the request, not in response


def test_certificate_chain_linkage(client):
    """Test that certificates in the same tenant are properly chained."""
    tenant_id = "hospital-gamma"
    headers = create_clinician_headers(tenant_id)

    # Issue first certificate
    request1 = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-clinical-v1",
        "prompt_version": "soap-note-v1.0",
        "governance_policy_version": "clinical-v1.0",
        "note_text": "First note for tenant gamma.",
        "human_reviewed": True,
        "human_reviewer_id": "test-reviewer-001",
    }

    response1 = client.post(
        "/v1/clinical/documentation", json=request1, headers=headers
    )
    assert response1.status_code == 200
    cert1 = response1.json()["certificate"]

    # Issue second certificate for same tenant
    request2 = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-clinical-v1",
        "prompt_version": "soap-note-v1.0",
        "governance_policy_version": "clinical-v1.0",
        "note_text": "Second note for tenant gamma.",
        "human_reviewed": True,
        "human_reviewer_id": "test-reviewer-001",
    }

    response2 = client.post(
        "/v1/clinical/documentation", json=request2, headers=headers
    )
    assert response2.status_code == 200
    cert2 = response2.json()["certificate"]

    # Verify chain linkage (previous_hash of first cert may or may not be None depending on test order)
    assert "previous_hash" in cert1["integrity_chain"]
    assert (
        cert2["integrity_chain"]["previous_hash"]
        == cert1["integrity_chain"]["chain_hash"]
    )  # Linked


def test_tenant_isolation(client):
    """Test that different tenants have isolated chains."""
    # Issue certificate for tenant delta
    request_delta = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-clinical-v1",
        "prompt_version": "soap-note-v1.0",
        "governance_policy_version": "clinical-v1.0",
        "note_text": "Note for tenant delta.",
        "human_reviewed": True,
        "human_reviewer_id": "test-reviewer-001",
    }
    headers_delta = create_clinician_headers("hospital-delta")

    response_delta = client.post(
        "/v1/clinical/documentation", json=request_delta, headers=headers_delta
    )
    assert response_delta.status_code == 200
    cert_delta = response_delta.json()["certificate"]

    # Issue certificate for tenant epsilon
    request_epsilon = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-clinical-v1",
        "prompt_version": "soap-note-v1.0",
        "governance_policy_version": "clinical-v1.0",
        "note_text": "Note for tenant epsilon.",
        "human_reviewed": True,
        "human_reviewer_id": "test-reviewer-001",
    }
    headers_epsilon = create_clinician_headers("hospital-epsilon")

    response_epsilon = client.post(
        "/v1/clinical/documentation", json=request_epsilon, headers=headers_epsilon
    )
    assert response_epsilon.status_code == 200
    cert_epsilon = response_epsilon.json()["certificate"]

    # Both should have integrity chains (previous_hash may or may not be None depending on test order)
    assert "previous_hash" in cert_delta["integrity_chain"]
    assert "previous_hash" in cert_epsilon["integrity_chain"]

    # Chain hashes should be different
    assert (
        cert_delta["integrity_chain"]["chain_hash"]
        != cert_epsilon["integrity_chain"]["chain_hash"]
    )


def test_get_certificate(client):
    """Test retrieving a certificate by ID."""
    # First issue a certificate
    request = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-clinical-v1",
        "prompt_version": "soap-note-v1.0",
        "governance_policy_version": "clinical-v1.0",
        "note_text": "Test note for retrieval.",
        "human_reviewed": True,
        "human_reviewer_id": "test-reviewer-001",
    }
    headers = create_clinician_headers("hospital-zeta")

    issue_response = client.post(
        "/v1/clinical/documentation", json=request, headers=headers
    )
    assert issue_response.status_code == 200
    certificate_id = issue_response.json()["certificate_id"]

    # Now retrieve it
    get_response = client.get(f"/v1/certificates/{certificate_id}", headers=headers)
    assert get_response.status_code == 200

    cert = get_response.json()
    assert cert["certificate_id"] == certificate_id
    assert cert["tenant_id"] == "hospital-zeta"
    assert cert["note_hash"]
    assert cert["integrity_chain"]
    assert cert["signature"]


def test_get_certificate_not_found(client):
    """Test retrieving a non-existent certificate."""
    headers = create_clinician_headers("hospital-test")
    response = client.get("/v1/certificates/nonexistent-cert-id", headers=headers)
    assert response.status_code == 404


def test_verify_certificate_valid(client):
    """Test verifying a valid, untampered certificate."""
    # Issue a certificate
    request = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-clinical-v1",
        "prompt_version": "soap-note-v1.0",
        "governance_policy_version": "clinical-v1.0",
        "note_text": "Note for verification test.",
        "human_reviewed": True,
        "human_reviewer_id": "test-reviewer-001",
    }
    headers = create_clinician_headers("hospital-eta")

    issue_response = client.post(
        "/v1/clinical/documentation", json=request, headers=headers
    )
    assert issue_response.status_code == 200
    certificate_id = issue_response.json()["certificate_id"]

    # Verify it (requires auditor role)
    auditor_headers = create_auditor_headers("hospital-eta")
    verify_response = client.post(
        f"/v1/certificates/{certificate_id}/verify", headers=auditor_headers
    )
    assert verify_response.status_code == 200

    result = verify_response.json()
    assert result["certificate_id"] == certificate_id
    assert result["valid"] is True
    assert result["failures"] == []


def test_verify_certificate_tampered(client):
    """Test verifying a tampered certificate (simulated by manual DB modification)."""
    import json
    from gateway.app.db.migrate import get_connection

    # Issue a certificate
    request = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-clinical-v1",
        "prompt_version": "soap-note-v1.0",
        "governance_policy_version": "clinical-v1.0",
        "note_text": "Note for tampering test.",
        "human_reviewed": True,
        "human_reviewer_id": "test-reviewer-001",
    }
    headers = create_clinician_headers("hospital-theta")

    issue_response = client.post(
        "/v1/clinical/documentation", json=request, headers=headers
    )
    assert issue_response.status_code == 200
    certificate_id = issue_response.json()["certificate_id"]

    # Tamper with the certificate in the database
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT certificate_json FROM certificates WHERE certificate_id = ?
        """,
            (certificate_id,),
        )
        row = cursor.fetchone()
        cert_dict = json.loads(row["certificate_json"])

        # Tamper: change the note_hash
        cert_dict["note_hash"] = "0" * 64

        # Update in database
        conn.execute(
            """
            UPDATE certificates SET certificate_json = ? WHERE certificate_id = ?
        """,
            (json.dumps(cert_dict, sort_keys=True), certificate_id),
        )
        conn.commit()
    finally:
        conn.close()

    # Verify the tampered certificate (requires auditor role)
    auditor_headers = create_auditor_headers("hospital-theta")
    verify_response = client.post(
        f"/v1/certificates/{certificate_id}/verify", headers=auditor_headers
    )
    assert verify_response.status_code == 200

    result = verify_response.json()
    assert result["certificate_id"] == certificate_id
    assert result["valid"] is False
    assert len(result["failures"]) > 0

    # Check that failure includes proper structure (check/error/debug)
    failure = result["failures"][0]
    assert "check" in failure
    assert "error" in failure


def test_verify_certificate_not_found(client):
    """Test verifying a non-existent certificate."""
    headers = create_auditor_headers("hospital-test")
    response = client.post(
        "/v1/certificates/nonexistent-cert-id/verify", headers=headers
    )
    assert response.status_code == 404


def test_no_plaintext_phi_in_storage(client):
    """Test that no plaintext PHI is stored in the database."""
    import json
    from gateway.app.db.migrate import get_connection

    # Issue a certificate with PHI
    request = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-clinical-v1",
        "prompt_version": "soap-note-v1.0",
        "governance_policy_version": "clinical-v1.0",
        "note_text": "SENSITIVE_NOTE_CONTENT_12345",
        "human_reviewed": True,
        "human_reviewer_id": "SENSITIVE_REVIEWER_ID_67890",
        "patient_reference": "SENSITIVE_PATIENT_MRN_11111",
    }
    headers = create_clinician_headers("hospital-iota")

    issue_response = client.post(
        "/v1/clinical/documentation", json=request, headers=headers
    )
    assert issue_response.status_code == 200
    certificate_id = issue_response.json()["certificate_id"]

    # Retrieve the raw certificate JSON from database
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT certificate_json FROM certificates WHERE certificate_id = ?
        """,
            (certificate_id,),
        )
        row = cursor.fetchone()
        cert_json = row["certificate_json"]
    finally:
        conn.close()

    # Verify NO plaintext PHI in stored JSON
    assert "SENSITIVE_NOTE_CONTENT_12345" not in cert_json
    assert "SENSITIVE_REVIEWER_ID_67890" not in cert_json
    assert "SENSITIVE_PATIENT_MRN_11111" not in cert_json

    # Verify hashes ARE present
    cert_dict = json.loads(cert_json)
    assert cert_dict["note_hash"]
    assert cert_dict["reviewer_hash"]
    assert cert_dict["patient_hash"]


def test_canonical_message_signed_fields_contract(client):
    """
    Verify the canonical_message.json contract:
    - patient_hash is NOT in the canonical message (not directly signed)
    - previous_hash is NOT in the canonical message (indirectly protected via chain_hash)
    - all expected signed fields ARE present
    - chain_hash IS signed (which indirectly protects previous_hash)
    - no unexpected extra fields are present
    """
    import json
    from gateway.app.db.migrate import get_connection

    request = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-clinical-v1",
        "prompt_version": "soap-note-v1.0",
        "governance_policy_version": "clinical-v1.0",
        "note_text": "Note for canonical message contract test.",
        "human_reviewed": True,
        "human_reviewer_id": "test-reviewer-contract",
        "patient_reference": "MRN-contract-test-999",
    }
    headers = create_clinician_headers("hospital-contract-test")

    response = client.post("/v1/clinical/documentation", json=request, headers=headers)
    assert response.status_code == 200

    certificate_id = response.json()["certificate_id"]

    # Retrieve the full stored certificate (includes canonical_message)
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT certificate_json FROM certificates WHERE certificate_id = ?",
            (certificate_id,),
        )
        row = cursor.fetchone()
        cert_dict = json.loads(row["certificate_json"])
    finally:
        conn.close()

    canonical_message = cert_dict["signature"]["canonical_message"]

    # patient_hash is stored in the certificate but MUST NOT be in canonical_message
    assert cert_dict["patient_hash"] is not None, (
        "patient_hash should be in the certificate"
    )
    assert "patient_hash" not in canonical_message, (
        "patient_hash must NOT be in canonical_message (it is not directly signed)"
    )

    # previous_hash is in integrity_chain but MUST NOT be directly in canonical_message;
    # it is indirectly protected: previous_hash feeds into chain_hash, which IS signed
    assert "previous_hash" not in canonical_message, (
        "previous_hash must NOT be directly in canonical_message; "
        "it is indirectly protected via chain_hash"
    )

    # chain_hash MUST be signed (it is what protects previous_hash indirectly)
    assert "chain_hash" in canonical_message, (
        "chain_hash must be in canonical_message (it indirectly protects previous_hash)"
    )

    # All expected signed fields must be present
    expected_signed_fields = {
        "certificate_id",
        "chain_hash",
        "governance_policy_hash",
        "governance_policy_version",
        "human_attested_at_utc",
        "human_reviewed",
        "human_reviewer_id_hash",
        "issued_at_utc",
        "key_id",
        "model_name",
        "model_version",
        "nonce",
        "note_hash",
        "prompt_version",
        "server_timestamp",
        "tenant_id",
    }
    missing = expected_signed_fields - set(canonical_message.keys())
    assert not missing, (
        f"Canonical message is missing expected signed fields: {missing}"
    )

    # No unexpected extra fields (canonical message contract is fixed)
    extra = set(canonical_message.keys()) - expected_signed_fields
    assert not extra, (
        f"Canonical message contains unexpected extra fields: {extra}. "
        "Update docs/BUNDLE_SPEC.md and docs/CONTRACT_SNAPSHOT.md if intentional."
    )
