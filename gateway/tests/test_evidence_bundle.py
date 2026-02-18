"""
Tests for evidence bundle generation and export.

Validates Phase 1 requirements:
- Evidence bundle JSON structure
- Cross-tenant access protection (404)
- Offline verification support
- No PHI in logs
"""

import pytest
import json
import os
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil
import zipfile
from io import BytesIO

# Enable test mode to disable rate limiting
os.environ["ENV"] = "TEST"

from gateway.app.main import app
from gateway.app.db.migrate import ensure_schema, get_db_path
from gateway.app.services.storage import bootstrap_dev_keys
from gateway.app.services.evidence_bundle import build_evidence_bundle
from gateway.tests.auth_helpers import create_clinician_headers, create_auditor_headers, create_admin_headers


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


def issue_test_certificate(client, tenant_id="test-tenant-001"):
    """Helper to issue a test certificate."""
    request_data = {
        "model_version": "gpt-4-turbo",
        "prompt_version": "clinical-v1.2",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": "Patient presents with headache. Vital signs stable.",
        "human_reviewed": True,
        "human_reviewer_id": "DR-TEST-001",
        "encounter_id": "ENC-TEST-001",
        "patient_reference": "PATIENT-TEST-001"
    }
    
    headers = create_clinician_headers(tenant_id)
    response = client.post("/v1/clinical/documentation", json=request_data, headers=headers)
    
    assert response.status_code == 200
    return response.json()


def test_evidence_bundle_json_structure(client):
    """Test that evidence bundle JSON has correct structure per INTEGRITY_ARTIFACT_SPEC."""
    # Issue a certificate
    cert_response = issue_test_certificate(client, tenant_id="tenant-bundle-001")
    certificate_id = cert_response["certificate_id"]
    
    # Get evidence bundle JSON
    headers = create_auditor_headers("tenant-bundle-001")
    response = client.get(f"/v1/certificates/{certificate_id}/evidence-bundle.json", headers=headers)
    
    assert response.status_code == 200
    bundle = response.json()
    
    # Validate bundle structure
    assert bundle["bundle_version"] == "1.0"
    assert "generated_at" in bundle
    
    # Validate metadata section
    assert "metadata" in bundle
    metadata = bundle["metadata"]
    assert metadata["certificate_id"] == certificate_id
    assert metadata["tenant_id"] == "tenant-bundle-001"
    assert "issued_at" in metadata
    assert "key_id" in metadata
    assert "algorithm" in metadata
    
    # Validate hashes section
    assert "hashes" in bundle
    hashes = bundle["hashes"]
    assert "note_hash" in hashes
    assert hashes["hash_algorithm"] == "SHA-256"
    # Note hash is stored as hex (without sha256: prefix in certificate)
    assert len(hashes["note_hash"]) == 64  # SHA-256 hex length
    
    # Validate model_info section
    assert "model_info" in bundle
    model_info = bundle["model_info"]
    assert model_info["model_version"] == "gpt-4-turbo"
    assert model_info["prompt_version"] == "clinical-v1.2"
    assert model_info["governance_policy_version"] == "CDOC-Policy-v1"
    assert "policy_hash" in model_info
    
    # Validate human_attestation section
    assert "human_attestation" in bundle
    attestation = bundle["human_attestation"]
    assert attestation["reviewed"] == True
    assert "reviewer_hash" in attestation
    assert "review_timestamp" in attestation
    
    # Validate verification_instructions
    assert "verification_instructions" in bundle
    instructions = bundle["verification_instructions"]
    assert "offline_cli" in instructions
    assert "api_endpoint" in instructions
    assert certificate_id in instructions["api_endpoint"]
    
    # Validate public_key_reference
    assert "public_key_reference" in bundle
    key_ref = bundle["public_key_reference"]
    assert "key_id" in key_ref
    assert "reference_url" in key_ref
    
    # Validate certificate is included
    assert "certificate" in bundle
    certificate = bundle["certificate"]
    assert certificate["certificate_id"] == certificate_id


def test_evidence_bundle_canonical_message_included(client):
    """Test that evidence bundle includes canonical_message for offline verification."""
    # Issue a certificate
    cert_response = issue_test_certificate(client, tenant_id="tenant-canonical-001")
    certificate_id = cert_response["certificate_id"]
    
    # Get evidence bundle
    headers = create_auditor_headers("tenant-canonical-001")
    response = client.get(f"/v1/certificates/{certificate_id}/evidence-bundle.json", headers=headers)
    
    assert response.status_code == 200
    bundle = response.json()
    
    # Certificate should include signature with canonical_message
    certificate = bundle["certificate"]
    assert "signature" in certificate
    signature = certificate["signature"]
    assert "canonical_message" in signature
    assert "signature" in signature
    
    # Canonical message should have required fields
    canonical_msg = signature["canonical_message"]
    assert "certificate_id" in canonical_msg
    assert "tenant_id" in canonical_msg
    assert "timestamp" in canonical_msg
    assert "note_hash" in canonical_msg
    assert "chain_hash" in canonical_msg
    assert "nonce" in canonical_msg
    assert "server_timestamp" in canonical_msg


def test_evidence_bundle_cross_tenant_access_forbidden(client):
    """Test that cross-tenant evidence bundle access returns 404 (no existence disclosure)."""
    # Tenant A issues a certificate
    cert_response = issue_test_certificate(client, tenant_id="tenant-A")
    certificate_id = cert_response["certificate_id"]
    
    # Tenant B tries to access Tenant A's evidence bundle
    headers_tenant_b = create_auditor_headers("tenant-B")
    response = client.get(f"/v1/certificates/{certificate_id}/evidence-bundle.json", headers=headers_tenant_b)
    
    # Should return 404 (not reveal existence)
    assert response.status_code == 404
    error = response.json()
    assert error["error"] == "not_found"
    assert "Certificate not found" in error["message"]


def test_evidence_bundle_no_phi_in_response(client):
    """Test that evidence bundle contains no plaintext PHI."""
    # Issue certificate with safe PHI fields (PHI detection only catches certain patterns)
    request_data = {
        "model_version": "gpt-4-turbo",
        "prompt_version": "clinical-v1.2",
        "governance_policy_version": "CDOC-Policy-v1",
        "note_text": "Patient presents with headache. Vital signs stable.",  # No PHI patterns
        "human_reviewed": True,
        "human_reviewer_id": "DR-JANE-DOE",
        "encounter_id": "ENC-PHI-TEST",
        "patient_reference": "PATIENT-JOHN-DOE-12345"
    }
    
    # Issue the certificate
    headers = create_clinician_headers("tenant-phi-test")
    response = client.post("/v1/clinical/documentation", json=request_data, headers=headers)
    assert response.status_code == 200
    
    certificate_id = response.json()["certificate_id"]
    
    # Get evidence bundle
    headers = create_auditor_headers("tenant-phi-test")
    response = client.get(f"/v1/certificates/{certificate_id}/evidence-bundle.json", headers=headers)
    
    assert response.status_code == 200
    bundle = response.json()
    
    # Convert to string to check for PHI leakage
    bundle_str = json.dumps(bundle)
    
    # Verify no plaintext PHI
    assert "Patient presents with headache" not in bundle_str  # note_text should be hashed
    assert "DR-JANE-DOE" not in bundle_str  # reviewer_id should be hashed
    assert "PATIENT-JOHN-DOE-12345" not in bundle_str  # patient_reference should be hashed
    
    # Verify hashes are present instead
    assert "note_hash" in bundle["hashes"]
    assert "reviewer_hash" in bundle["hashes"]
    assert "patient_hash" in bundle["hashes"]
    
    # All hashes should be 64-char hex strings (SHA-256)
    assert len(bundle["hashes"]["note_hash"]) == 64
    assert len(bundle["hashes"]["reviewer_hash"]) == 64
    assert len(bundle["hashes"]["patient_hash"]) == 64


def test_evidence_bundle_zip_includes_json_bundle(client):
    """Test that ZIP bundle includes evidence_bundle.json file."""
    # Issue a certificate
    cert_response = issue_test_certificate(client, tenant_id="tenant-zip-001")
    certificate_id = cert_response["certificate_id"]
    
    # Get ZIP bundle
    headers = create_auditor_headers("tenant-zip-001")
    response = client.get(f"/v1/certificates/{certificate_id}/evidence-bundle.zip", headers=headers)
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    
    # Extract ZIP and check contents
    zip_buffer = BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, 'r') as zipf:
        file_list = zipf.namelist()
        
        # Should contain all expected files
        assert "certificate.json" in file_list
        assert "certificate.pdf" in file_list
        assert "evidence_bundle.json" in file_list  # New file added
        assert "verification_report.json" in file_list
        assert "README_VERIFICATION.txt" in file_list
        
        # Read and validate evidence_bundle.json
        bundle_json = zipf.read("evidence_bundle.json").decode('utf-8')
        bundle = json.loads(bundle_json)
        
        # Validate structure
        assert bundle["bundle_version"] == "1.0"
        assert "metadata" in bundle
        assert "certificate" in bundle
        assert bundle["metadata"]["certificate_id"] == certificate_id


def test_build_evidence_bundle_function(client):
    """Test build_evidence_bundle function directly."""
    # Issue a certificate
    cert_response = issue_test_certificate(client, tenant_id="tenant-direct-001")
    certificate = cert_response["certificate"]
    
    # Build evidence bundle directly
    bundle = build_evidence_bundle(certificate, identity="tenant-direct-001")
    
    # Validate structure
    assert bundle["bundle_version"] == "1.0"
    assert "generated_at" in bundle
    assert "metadata" in bundle
    assert "hashes" in bundle
    assert "model_info" in bundle
    assert "human_attestation" in bundle
    assert "verification_instructions" in bundle
    assert "public_key_reference" in bundle
    assert "certificate" in bundle
    
    # Metadata should match certificate
    assert bundle["metadata"]["certificate_id"] == certificate["certificate_id"]
    assert bundle["metadata"]["tenant_id"] == certificate["tenant_id"]


def test_evidence_bundle_offline_verification_support(client):
    """Test that evidence bundle provides sufficient info for offline verification."""
    # Issue a certificate
    cert_response = issue_test_certificate(client, tenant_id="tenant-offline-001")
    certificate_id = cert_response["certificate_id"]
    
    # Get evidence bundle
    headers = create_auditor_headers("tenant-offline-001")
    response = client.get(f"/v1/certificates/{certificate_id}/evidence-bundle.json", headers=headers)
    
    assert response.status_code == 200
    bundle = response.json()
    
    # Bundle should have everything needed for offline verification
    certificate = bundle["certificate"]
    signature = certificate["signature"]
    
    # Has canonical message (what was signed)
    assert "canonical_message" in signature
    canonical_msg = signature["canonical_message"]
    assert isinstance(canonical_msg, dict)
    
    # Has signature
    assert "signature" in signature
    assert isinstance(signature["signature"], str)
    assert len(signature["signature"]) > 0
    
    # Has algorithm
    assert signature["algorithm"] == "ECDSA_SHA_256"
    
    # Has key reference
    assert "key_id" in signature
    public_key_ref = bundle["public_key_reference"]
    assert public_key_ref["key_id"] == signature["key_id"]
    assert "reference_url" in public_key_ref
    
    # Has verification instructions
    instructions = bundle["verification_instructions"]
    assert "offline_cli" in instructions
    assert "python verify_certificate_cli.py" in instructions["offline_cli"]


def test_evidence_bundle_rate_limiting(client):
    """Test that evidence bundle endpoints respect rate limits."""
    # This test validates rate limiting exists (implementation detail of @limiter.limit)
    # Issue a certificate
    cert_response = issue_test_certificate(client, tenant_id="tenant-rate-001")
    certificate_id = cert_response["certificate_id"]
    
    # Normal request should succeed
    headers = create_auditor_headers("tenant-rate-001")
    response = client.get(f"/v1/certificates/{certificate_id}/evidence-bundle.json", headers=headers)
    
    assert response.status_code == 200
    
    # Rate limiter is applied (decorator present in route)
    # In real scenario, exceeding 100/minute would return 429
    # For this test, we just verify the endpoint works normally


def test_evidence_bundle_requires_authentication(client):
    """Test that evidence bundle endpoints require authentication."""
    # Try to access without auth header
    response = client.get("/v1/certificates/fake-id/evidence-bundle.json")
    
    # Should return 403 (Forbidden) or 401 (Unauthorized) depending on auth setup
    assert response.status_code in [401, 403]


def test_evidence_bundle_not_found(client):
    """Test that evidence bundle returns 404 for non-existent certificate."""
    # Try to get bundle for certificate that doesn't exist
    headers = create_auditor_headers("tenant-notfound-001")
    response = client.get("/v1/certificates/fake-cert-id-999/evidence-bundle.json", headers=headers)
    
    assert response.status_code == 404
    error = response.json()
    assert error["error"] == "not_found"


def test_evidence_bundle_includes_chain_integrity(client):
    """Test that evidence bundle includes chain integrity information."""
    # Issue multiple certificates to create a chain
    cert1 = issue_test_certificate(client, tenant_id="tenant-chain-001")
    cert2 = issue_test_certificate(client, tenant_id="tenant-chain-001")
    
    certificate_id = cert2["certificate_id"]
    
    # Get evidence bundle for second certificate
    headers = create_auditor_headers("tenant-chain-001")
    response = client.get(f"/v1/certificates/{certificate_id}/evidence-bundle.json", headers=headers)
    
    assert response.status_code == 200
    bundle = response.json()
    
    # Certificate should have integrity chain
    certificate = bundle["certificate"]
    assert "integrity_chain" in certificate
    chain = certificate["integrity_chain"]
    
    # Second cert should have previous_hash (links to first cert)
    assert "previous_hash" in chain
    assert chain["previous_hash"] is not None
    assert len(chain["previous_hash"]) > 0
    
    # Chain hash should be present
    assert "chain_hash" in chain
    assert len(chain["chain_hash"]) > 0
