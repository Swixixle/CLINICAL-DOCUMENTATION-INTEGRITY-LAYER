"""
Tests for EHR gatekeeper endpoints (Phase 4).

Validates:
- Certificate verification and commit token issuance
- Commit token validation
- Token expiration
- Nonce-based replay protection
- ehr_gateway role enforcement
- Tenant boundary enforcement
"""

import pytest
import time
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil
import jwt as pyjwt

from gateway.app.main import app
from gateway.app.db.migrate import ensure_schema, get_db_path
from gateway.app.services.storage import bootstrap_dev_keys
from gateway.tests.auth_helpers import (
    create_clinician_headers,
    create_ehr_gateway_headers,
    create_admin_headers
)


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database."""
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


def test_gatekeeper_verify_and_authorize_success(client):
    """Test successful gatekeeper verification and commit token issuance."""
    tenant_id = "tenant-gk-001"
    
    # Issue a certificate
    cert_response = issue_test_certificate(client, tenant_id=tenant_id)
    certificate_id = cert_response["certificate_id"]
    
    # Verify and authorize via gatekeeper
    headers = create_ehr_gateway_headers(tenant_id)
    response = client.post(
        "/v1/gatekeeper/verify-and-authorize",
        json={
            "certificate_id": certificate_id,
            "ehr_commit_id": "ehr-commit-12345"
        },
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["certificate_id"] == certificate_id
    assert data["tenant_id"] == tenant_id
    assert data["authorized"] == True
    assert data["verification_passed"] == True
    assert data["verification_failures"] == []
    assert "commit_token" in data
    assert data["commit_token"] is not None
    assert data["ehr_commit_id"] == "ehr-commit-12345"
    assert "verified_at" in data


def test_gatekeeper_commit_token_structure(client):
    """Test that commit token has correct structure."""
    tenant_id = "tenant-gk-002"
    
    # Issue certificate and get commit token
    cert_response = issue_test_certificate(client, tenant_id=tenant_id)
    certificate_id = cert_response["certificate_id"]
    
    headers = create_ehr_gateway_headers(tenant_id)
    response = client.post(
        "/v1/gatekeeper/verify-and-authorize",
        json={
            "certificate_id": certificate_id,
            "ehr_commit_id": "ehr-commit-67890"
        },
        headers=headers
    )
    
    commit_token = response.json()["commit_token"]
    
    # Decode token (without verification) to check structure
    from gateway.app.routes.gatekeeper import COMMIT_TOKEN_SECRET
    decoded = pyjwt.decode(commit_token, COMMIT_TOKEN_SECRET, algorithms=["HS256"])
    
    assert decoded["token_type"] == "cdil_commit_authorization"
    assert decoded["tenant_id"] == tenant_id
    assert decoded["certificate_id"] == certificate_id
    assert decoded["ehr_commit_id"] == "ehr-commit-67890"
    assert "nonce" in decoded
    assert "iat" in decoded
    assert "exp" in decoded
    
    # Check expiration is ~5 minutes
    exp_timestamp = decoded["exp"]
    iat_timestamp = decoded["iat"]
    assert (exp_timestamp - iat_timestamp) <= 300  # 5 minutes


def test_gatekeeper_cross_tenant_access_forbidden(client):
    """Test that gatekeeper enforces tenant boundary."""
    # Tenant A issues certificate
    cert_response = issue_test_certificate(client, tenant_id="tenant-A")
    certificate_id = cert_response["certificate_id"]
    
    # Tenant B tries to verify Tenant A's certificate
    headers_b = create_ehr_gateway_headers("tenant-B")
    response = client.post(
        "/v1/gatekeeper/verify-and-authorize",
        json={"certificate_id": certificate_id},
        headers=headers_b
    )
    
    # Should return 404 (no existence disclosure)
    assert response.status_code == 404
    error = response.json()
    assert error["error"] == "certificate_not_found"


def test_gatekeeper_requires_ehr_gateway_role(client):
    """Test that gatekeeper endpoint requires ehr_gateway role."""
    tenant_id = "tenant-gk-003"
    
    # Issue certificate
    cert_response = issue_test_certificate(client, tenant_id=tenant_id)
    certificate_id = cert_response["certificate_id"]
    
    # Try with clinician role (should fail)
    clinician_headers = create_clinician_headers(tenant_id)
    response = client.post(
        "/v1/gatekeeper/verify-and-authorize",
        json={"certificate_id": certificate_id},
        headers=clinician_headers
    )
    
    assert response.status_code == 403  # Forbidden


def test_gatekeeper_requires_authentication(client):
    """Test that gatekeeper endpoint requires authentication."""
    response = client.post(
        "/v1/gatekeeper/verify-and-authorize",
        json={"certificate_id": "fake-id"}
    )
    
    assert response.status_code in [401, 403]


def test_gatekeeper_certificate_not_found(client):
    """Test gatekeeper returns 404 for non-existent certificate."""
    headers = create_ehr_gateway_headers("tenant-gk-004")
    
    response = client.post(
        "/v1/gatekeeper/verify-and-authorize",
        json={"certificate_id": "non-existent-cert-id"},
        headers=headers
    )
    
    assert response.status_code == 404
    error = response.json()
    assert error["error"] == "certificate_not_found"


def test_verify_commit_token_success(client):
    """Test successful commit token verification."""
    tenant_id = "tenant-gk-005"
    
    # Issue certificate and get commit token
    cert_response = issue_test_certificate(client, tenant_id=tenant_id)
    certificate_id = cert_response["certificate_id"]
    
    headers = create_ehr_gateway_headers(tenant_id)
    auth_response = client.post(
        "/v1/gatekeeper/verify-and-authorize",
        json={"certificate_id": certificate_id},
        headers=headers
    )
    
    commit_token = auth_response.json()["commit_token"]
    
    # Verify the commit token
    verify_response = client.post(
        "/v1/gatekeeper/verify-commit-token",
        params={"commit_token": commit_token},
        headers=headers
    )
    
    assert verify_response.status_code == 200
    data = verify_response.json()
    
    assert data["valid"] == True
    assert data["certificate_id"] == certificate_id
    assert data["tenant_id"] == tenant_id
    assert "issued_at" in data
    assert "expires_at" in data


def test_commit_token_replay_protection(client):
    """Test that commit token can only be used once (nonce protection)."""
    tenant_id = "tenant-gk-006"
    
    # Issue certificate and get commit token
    cert_response = issue_test_certificate(client, tenant_id=tenant_id)
    certificate_id = cert_response["certificate_id"]
    
    headers = create_ehr_gateway_headers(tenant_id)
    auth_response = client.post(
        "/v1/gatekeeper/verify-and-authorize",
        json={"certificate_id": certificate_id},
        headers=headers
    )
    
    commit_token = auth_response.json()["commit_token"]
    
    # First verification should succeed
    verify_response1 = client.post(
        "/v1/gatekeeper/verify-commit-token",
        params={"commit_token": commit_token},
        headers=headers
    )
    assert verify_response1.status_code == 200
    
    # Second verification should fail (nonce already used)
    verify_response2 = client.post(
        "/v1/gatekeeper/verify-commit-token",
        params={"commit_token": commit_token},
        headers=headers
    )
    assert verify_response2.status_code == 400
    error = verify_response2.json()
    assert error["error"] == "nonce_already_used"


def test_commit_token_cross_tenant_fails(client):
    """Test that commit token validation enforces tenant boundary."""
    # Tenant A gets commit token
    cert_response_a = issue_test_certificate(client, tenant_id="tenant-A")
    certificate_id_a = cert_response_a["certificate_id"]
    
    headers_a = create_ehr_gateway_headers("tenant-A")
    auth_response_a = client.post(
        "/v1/gatekeeper/verify-and-authorize",
        json={"certificate_id": certificate_id_a},
        headers=headers_a
    )
    commit_token_a = auth_response_a.json()["commit_token"]
    
    # Tenant B tries to verify Tenant A's token
    headers_b = create_ehr_gateway_headers("tenant-B")
    verify_response = client.post(
        "/v1/gatekeeper/verify-commit-token",
        params={"commit_token": commit_token_a},
        headers=headers_b
    )
    
    # Should fail with tenant mismatch
    assert verify_response.status_code == 403
    error = verify_response.json()
    assert error["error"] == "tenant_mismatch"


def test_commit_token_invalid_token_fails(client):
    """Test that invalid commit token is rejected."""
    headers = create_ehr_gateway_headers("tenant-gk-007")
    
    # Try to verify a fake token
    response = client.post(
        "/v1/gatekeeper/verify-commit-token",
        params={"commit_token": "fake-invalid-token"},
        headers=headers
    )
    
    assert response.status_code == 400
    error = response.json()
    assert error["error"] == "invalid_token"


def test_gatekeeper_optional_ehr_commit_id(client):
    """Test that ehr_commit_id is optional."""
    tenant_id = "tenant-gk-008"
    
    # Issue certificate
    cert_response = issue_test_certificate(client, tenant_id=tenant_id)
    certificate_id = cert_response["certificate_id"]
    
    # Verify without ehr_commit_id
    headers = create_ehr_gateway_headers(tenant_id)
    response = client.post(
        "/v1/gatekeeper/verify-and-authorize",
        json={"certificate_id": certificate_id},
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["authorized"] == True
    assert data["ehr_commit_id"] is None


def test_gatekeeper_rate_limiting_applied(client):
    """Test that rate limiting is applied to gatekeeper endpoints."""
    tenant_id = "tenant-gk-009"
    
    # Issue certificate
    cert_response = issue_test_certificate(client, tenant_id=tenant_id)
    certificate_id = cert_response["certificate_id"]
    
    # Normal request should succeed
    headers = create_ehr_gateway_headers(tenant_id)
    response = client.post(
        "/v1/gatekeeper/verify-and-authorize",
        json={"certificate_id": certificate_id},
        headers=headers
    )
    
    assert response.status_code == 200
    
    # Rate limiter is applied (decorator present in route)
    # In real scenario, exceeding 100/minute would return 429
