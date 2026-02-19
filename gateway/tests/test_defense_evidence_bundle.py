"""
Tests for Courtroom Defense Mode - Phase 3: Evidence Bundle - Litigation Mode.

Tests:
- Enhanced evidence bundle includes litigation_metadata
- Defense bundle endpoint returns ZIP with all required files
- Defense bundle README has offline verification instructions
- Public key is included in PEM format
- Canonical message is included for hash recomputation
"""

import pytest
import zipfile
from io import BytesIO
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil
import json

from gateway.app.main import app
from gateway.app.db.migrate import ensure_schema
from gateway.app.services.storage import bootstrap_dev_keys
from gateway.app.services.evidence_bundle import build_evidence_bundle, generate_defense_bundle
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
        "note_text": "Patient presents with headache. Vital signs stable.",
        "human_reviewed": True,
        "human_reviewer_id": "DR-TEST-001",
        "encounter_id": "ENC-TEST-001"
    }
    
    headers = create_clinician_headers(tenant_id)
    response = client.post("/v1/clinical/documentation", json=request_data, headers=headers)
    
    assert response.status_code == 200
    return response.json()


def test_evidence_bundle_includes_litigation_metadata():
    """
    Test that evidence bundle includes litigation_metadata section.
    """
    # Create sample certificate
    certificate = {
        "certificate_id": "TEST-CERT-001",
        "tenant_id": "hospital-alpha",
        "timestamp": "2024-01-15T10:00:00Z",
        "issued_at_utc": "2024-01-15T10:00:00Z",
        "model_name": "gpt-4",
        "model_version": "2024-01-15",
        "note_hash": "abc123hash",
        "human_reviewed": True,
        "human_attested_at_utc": "2024-01-15T10:00:00Z",
        "signature": {
            "key_id": "key-001",
            "algorithm": "ECDSA_SHA_256",
            "signature": "signature_value",
            "canonical_message": {
                "certificate_id": "TEST-CERT-001",
                "note_hash": "abc123hash",
                "human_reviewed": True
            }
        },
        "integrity_chain": {
            "chain_hash": "chain123",
            "previous_hash": None
        }
    }
    
    # Build evidence bundle
    bundle = build_evidence_bundle(certificate)
    
    # Check that litigation_metadata exists
    assert "litigation_metadata" in bundle
    
    # Check litigation_metadata structure
    lit_meta = bundle["litigation_metadata"]
    assert "verification_status" in lit_meta
    assert "verification_timestamp_utc" in lit_meta
    assert "signer_public_key_id" in lit_meta
    assert "signature_algorithm" in lit_meta
    assert "canonical_hash" in lit_meta
    assert "human_attestation_summary" in lit_meta
    assert "provenance_fields_signed" in lit_meta
    assert "chain_integrity" in lit_meta
    
    # Check chain_integrity details
    chain_int = lit_meta["chain_integrity"]
    assert chain_int["prevents_insertion"] is True
    assert chain_int["prevents_reordering"] is True


def test_litigation_metadata_human_attestation_summary():
    """
    Test that human attestation summary is generated correctly.
    """
    # Certificate with human review
    cert_reviewed = {
        "certificate_id": "TEST-001",
        "human_reviewed": True,
        "human_attested_at_utc": "2024-01-15T10:00:00Z",
        "signature": {"key_id": "key-1", "canonical_message": {}}
    }
    
    bundle_reviewed = build_evidence_bundle(cert_reviewed)
    summary_reviewed = bundle_reviewed["litigation_metadata"]["human_attestation_summary"]
    assert "Human reviewed and attested" in summary_reviewed
    assert "2024-01-15T10:00:00Z" in summary_reviewed
    
    # Certificate without human review
    cert_not_reviewed = {
        "certificate_id": "TEST-002",
        "human_reviewed": False,
        "signature": {"key_id": "key-1", "canonical_message": {}}
    }
    
    bundle_not_reviewed = build_evidence_bundle(cert_not_reviewed)
    summary_not_reviewed = bundle_not_reviewed["litigation_metadata"]["human_attestation_summary"]
    assert "Not reviewed by human" in summary_not_reviewed


def test_defense_bundle_endpoint_returns_zip(client):
    """
    Test that defense bundle endpoint returns a valid ZIP file.
    """
    # Issue certificate
    cert_response = issue_test_certificate(client, tenant_id="hospital-alpha")
    cert_id = cert_response["certificate_id"]
    
    # Request defense bundle
    headers = create_clinician_headers("hospital-alpha")
    response = client.get(f"/v1/certificates/{cert_id}/defense-bundle", headers=headers)
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    
    # Verify it's a valid ZIP
    zip_buffer = BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, 'r') as zf:
        # Check required files are present
        file_list = zf.namelist()
        assert "certificate.json" in file_list
        assert "canonical_message.json" in file_list
        assert "verification_report.json" in file_list
        assert "public_key.pem" in file_list
        assert "README.txt" in file_list


def test_defense_bundle_canonical_message_is_complete(client):
    """
    Test that canonical_message.json in defense bundle is complete.
    """
    # Issue certificate
    cert_response = issue_test_certificate(client, tenant_id="hospital-alpha")
    cert_id = cert_response["certificate_id"]
    
    # Request defense bundle
    headers = create_clinician_headers("hospital-alpha")
    response = client.get(f"/v1/certificates/{cert_id}/defense-bundle", headers=headers)
    
    assert response.status_code == 200
    
    # Extract and check canonical_message.json
    zip_buffer = BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, 'r') as zf:
        canonical_json = zf.read("canonical_message.json").decode('utf-8')
        canonical_message = json.loads(canonical_json)
        
        # Should have all required provenance fields
        assert "certificate_id" in canonical_message
        assert "note_hash" in canonical_message
        assert "model_name" in canonical_message
        assert "model_version" in canonical_message
        assert "human_reviewed" in canonical_message
        assert "tenant_id" in canonical_message
        assert "issued_at_utc" in canonical_message
        
        # Should have replay protection fields
        assert "nonce" in canonical_message
        assert "server_timestamp" in canonical_message
        
        # Should have key_id
        assert "key_id" in canonical_message


def test_defense_bundle_public_key_is_pem_format(client):
    """
    Test that public_key.pem is in valid PEM format.
    """
    # Issue certificate
    cert_response = issue_test_certificate(client, tenant_id="hospital-alpha")
    cert_id = cert_response["certificate_id"]
    
    # Request defense bundle
    headers = create_clinician_headers("hospital-alpha")
    response = client.get(f"/v1/certificates/{cert_id}/defense-bundle", headers=headers)
    
    assert response.status_code == 200
    
    # Extract and check public_key.pem
    zip_buffer = BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, 'r') as zf:
        public_key_pem = zf.read("public_key.pem").decode('utf-8')
        
        # Check PEM format
        assert "-----BEGIN PUBLIC KEY-----" in public_key_pem
        assert "-----END PUBLIC KEY-----" in public_key_pem
        assert len(public_key_pem) > 100  # Should have actual key data


def test_defense_bundle_readme_has_verification_instructions(client):
    """
    Test that README.txt contains offline verification instructions.
    """
    # Issue certificate
    cert_response = issue_test_certificate(client, tenant_id="hospital-alpha")
    cert_id = cert_response["certificate_id"]
    
    # Request defense bundle
    headers = create_clinician_headers("hospital-alpha")
    response = client.get(f"/v1/certificates/{cert_id}/defense-bundle", headers=headers)
    
    assert response.status_code == 200
    
    # Extract and check README.txt
    zip_buffer = BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, 'r') as zf:
        readme = zf.read("README.txt").decode('utf-8')
        
        # Check for key sections
        assert "COURTROOM DEFENSE BUNDLE" in readme
        assert "OFFLINE VERIFICATION" in readme
        assert "MANUAL METHOD" in readme
        assert "AUTOMATED METHOD" in readme
        assert "LEGAL INTERPRETATION" in readme
        assert "FOR EXPERT WITNESSES" in readme
        
        # Check for technical details
        assert "SHA-256" in readme
        assert "ECDSA" in readme
        assert "P-256" in readme
        
        # Check for legal guidance
        assert "cryptographically" in readme.lower()
        assert "signature" in readme.lower()
        assert "tamper" in readme.lower() or "alter" in readme.lower()


def test_defense_bundle_cross_tenant_returns_404(client):
    """
    Test that requesting defense bundle for another tenant's certificate returns 404.
    """
    # Issue certificate for tenant A
    cert_response = issue_test_certificate(client, tenant_id="hospital-alpha")
    cert_id = cert_response["certificate_id"]
    
    # Try to access from tenant B
    headers = create_clinician_headers("hospital-bravo")
    response = client.get(f"/v1/certificates/{cert_id}/defense-bundle", headers=headers)
    
    # Should return 404
    assert response.status_code == 404


def test_defense_bundle_nonexistent_certificate_returns_404(client):
    """
    Test that requesting defense bundle for nonexistent certificate returns 404.
    """
    headers = create_clinician_headers("hospital-alpha")
    response = client.get("/v1/certificates/NONEXISTENT-CERT/defense-bundle", headers=headers)
    
    assert response.status_code == 404


def test_defense_bundle_requires_authentication(client):
    """
    Test that defense bundle endpoint requires authentication.
    """
    # No auth headers
    response = client.get("/v1/certificates/SOME-CERT/defense-bundle")
    
    assert response.status_code in [401, 403]


def test_generate_defense_bundle_function():
    """
    Test the generate_defense_bundle function directly.
    """
    certificate = {
        "certificate_id": "TEST-001",
        "tenant_id": "hospital-test",
        "issued_at_utc": "2024-01-15T10:00:00Z",
        "model_name": "gpt-4",
        "human_reviewed": True,
        "signature": {
            "key_id": "key-001",
            "canonical_message": {
                "certificate_id": "TEST-001",
                "note_hash": "hash123"
            }
        }
    }
    
    public_key_pem = """-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...
-----END PUBLIC KEY-----"""
    
    verification_report = {
        "status": "VALID",
        "verified_at": "2024-01-15T11:00:00Z"
    }
    
    # Generate bundle
    zip_bytes = generate_defense_bundle(certificate, public_key_pem, verification_report)
    
    # Should return bytes
    assert isinstance(zip_bytes, bytes)
    assert len(zip_bytes) > 0
    
    # Should be valid ZIP
    zip_buffer = BytesIO(zip_bytes)
    with zipfile.ZipFile(zip_buffer, 'r') as zf:
        file_list = zf.namelist()
        assert len(file_list) == 5  # All 5 files present


def test_defense_bundle_verification_report_included(client):
    """
    Test that verification_report.json is included and has valid structure.
    """
    # Issue certificate
    cert_response = issue_test_certificate(client, tenant_id="hospital-alpha")
    cert_id = cert_response["certificate_id"]
    
    # Request defense bundle
    headers = create_clinician_headers("hospital-alpha")
    response = client.get(f"/v1/certificates/{cert_id}/defense-bundle", headers=headers)
    
    assert response.status_code == 200
    
    # Extract and check verification_report.json
    zip_buffer = BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, 'r') as zf:
        verify_json = zf.read("verification_report.json").decode('utf-8')
        verify_report = json.loads(verify_json)
        
        # Should have verification results
        assert "valid" in verify_report or "status" in verify_report
        # Should have some verification info (either checks, summary, human_friendly_report, or failures)
        assert ("checks" in verify_report or "summary" in verify_report or 
                "human_friendly_report" in verify_report or "failures" in verify_report)
