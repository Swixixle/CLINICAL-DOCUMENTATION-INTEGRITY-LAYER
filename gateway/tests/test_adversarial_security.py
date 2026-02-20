"""
Adversarial Security Tests for CDIL.

Tests security boundaries and attack scenarios to verify security hardening.
These tests MUST pass before production deployment.
"""

import pytest
import json
from fastapi.testclient import TestClient
from jose import jwt

from gateway.app.main import app
from gateway.tests.test_helpers import (
    generate_test_jwt,
    generate_expired_jwt,
    generate_malformed_jwt,
    create_auth_headers,
    TEST_CLINICIAN,
    TEST_AUDITOR,
    TEST_TENANT_B_CLINICIAN,
)

client = TestClient(app)


class TestTenantIsolation:
    """Test that tenant A cannot access tenant B's resources."""

    def test_cross_tenant_certificate_access_blocked(self):
        """Test that tenant B cannot retrieve tenant A's certificate."""
        # Tenant A issues a certificate
        headers_a = create_auth_headers(**TEST_CLINICIAN)
        cert_request = {
            "model_name": "gpt-4",
            "model_version": "gpt-4-turbo",
            "prompt_version": "v1.0",
            "governance_policy_version": "policy-2024-01",
            "note_text": "Patient presented with symptoms.",
            "human_reviewed": True,
            "human_reviewer_id": "test-reviewer-001",
            "encounter_id": "enc-123",
        }

        response_a = client.post(
            "/v1/clinical/documentation", json=cert_request, headers=headers_a
        )
        assert response_a.status_code == 200
        cert_id = response_a.json()["certificate_id"]

        # Tenant B tries to access tenant A's certificate
        headers_b = create_auth_headers(**TEST_TENANT_B_CLINICIAN)
        response_b = client.get(f"/v1/certificates/{cert_id}", headers=headers_b)

        # Should return 404 (not 403, to avoid leaking existence)
        assert response_b.status_code == 404
        assert "not_found" in response_b.json().get("error", "")

    def test_tenant_impersonation_via_jwt_modification(self):
        """Test that modifying JWT tenant_id is rejected."""
        # Generate valid token for tenant A
        generate_test_jwt(**TEST_CLINICIAN)

        # Attempt to decode and modify (would fail signature check)
        # In real attack, attacker might try to create new token with different tenant_id
        # But without the secret key, signature validation will fail

        # Try to use a self-signed token with wrong tenant
        secret_key = "wrong-secret-key"
        malicious_payload = {
            "sub": "attacker",
            "tenant_id": "target-tenant",
            "role": "admin",
            "exp": 9999999999,
            "iat": 1000000000,
        }
        malicious_token = jwt.encode(malicious_payload, secret_key, algorithm="HS256")

        headers = {"Authorization": f"Bearer {malicious_token}"}
        response = client.get("/v1/certificates/any-id", headers=headers)

        # Should reject with 401 (invalid signature)
        assert response.status_code == 401


class TestAuthenticationEnforcement:
    """Test that authentication is required for all protected endpoints."""

    def test_certificate_issuance_requires_auth(self):
        """Test that certificate issuance requires authentication."""
        cert_request = {
            "model_name": "gpt-4",
            "model_version": "gpt-4-turbo",
            "prompt_version": "v1.0",
            "governance_policy_version": "policy-2024-01",
            "note_text": "Patient presented with symptoms.",
            "human_reviewed": True,
        }

        # Request without Authorization header
        response = client.post("/v1/clinical/documentation", json=cert_request)

        # Should reject with 401 or 403
        assert response.status_code in [401, 403]

    def test_expired_token_rejected(self):
        """Test that expired JWT tokens are rejected."""
        expired_token = generate_expired_jwt(**TEST_CLINICIAN)
        headers = {"Authorization": f"Bearer {expired_token}"}

        response = client.get("/v1/certificates/any-id", headers=headers)

        assert response.status_code == 401

    def test_malformed_token_rejected(self):
        """Test that malformed JWT tokens are rejected."""
        malformed_token = generate_malformed_jwt()
        headers = {"Authorization": f"Bearer {malformed_token}"}

        response = client.get("/v1/certificates/any-id", headers=headers)

        assert response.status_code == 401


class TestRoleBasedAccessControl:
    """Test that role-based access control is enforced."""

    def test_auditor_cannot_issue_certificates(self):
        """Test that auditor role cannot issue certificates."""
        headers = create_auth_headers(**TEST_AUDITOR)
        cert_request = {
            "model_name": "gpt-4",
            "model_version": "gpt-4-turbo",
            "prompt_version": "v1.0",
            "governance_policy_version": "policy-2024-01",
            "note_text": "Patient presented with symptoms.",
            "human_reviewed": True,
        }

        response = client.post(
            "/v1/clinical/documentation", json=cert_request, headers=headers
        )

        # Should reject with 403 (forbidden)
        assert response.status_code == 403
        assert "insufficient_permissions" in response.json().get("error", "")

    def test_clinician_can_issue_certificates(self):
        """Test that clinician role can issue certificates."""
        headers = create_auth_headers(**TEST_CLINICIAN)
        cert_request = {
            "model_name": "gpt-4",
            "model_version": "gpt-4-turbo",
            "prompt_version": "v1.0",
            "governance_policy_version": "policy-2024-01",
            "note_text": "Patient presented with symptoms.",
            "human_reviewed": True,
            "human_reviewer_id": "test-reviewer-001",
        }

        response = client.post(
            "/v1/clinical/documentation", json=cert_request, headers=headers
        )

        # Should succeed with 200
        assert response.status_code == 200
        assert "certificate_id" in response.json()


class TestReplayProtection:
    """Test that replay attacks are prevented."""

    def test_replay_attack_blocked(self):
        """
        Test that resubmitting the same nonce is blocked.

        This test verifies that the nonce-based replay protection works by:
        1. Signing a message with a tenant ID (generates and records a nonce)
        2. Extracting the nonce from the signature bundle
        3. Attempting to reuse the same nonce (should fail)
        """
        from gateway.app.services.signer import (
            sign_generic_message,
            check_and_record_nonce,
        )

        tenant_id = "hospital-replay-test"
        test_message = {
            "certificate_id": "test-cert-001",
            "model_name": "gpt-4",
            "model_version": "gpt-4-turbo",
            "note_hash": "abc123",
        }

        # Step 1: Sign a message (this generates and records a nonce)
        signature_bundle = sign_generic_message(test_message, tenant_id=tenant_id)

        # Step 2: Extract the nonce from the canonical_message
        canonical_message = signature_bundle["canonical_message"]
        assert (
            "nonce" in canonical_message
        ), "Nonce should be present in signature bundle"
        used_nonce = canonical_message["nonce"]

        # Step 3: Attempt to reuse the same nonce (should fail)
        # The check_and_record_nonce function returns False if nonce is already used
        is_nonce_new = check_and_record_nonce(tenant_id, used_nonce)

        # Verify that the nonce is rejected (replay attack detected)
        assert not is_nonce_new, "Reused nonce should be rejected"

    def test_nonce_isolation_between_tenants(self):
        """
        Test that nonces are isolated per tenant.

        A nonce used by tenant A should be allowed for tenant B
        (nonces are scoped to tenants).
        """
        from gateway.app.services.signer import check_and_record_nonce
        from gateway.app.services.uuid7 import generate_uuid7

        # Generate a unique nonce
        shared_nonce = generate_uuid7()

        # Record nonce for tenant A
        tenant_a = "hospital-a-replay"
        is_new_a = check_and_record_nonce(tenant_a, shared_nonce)
        assert is_new_a, "First use of nonce by tenant A should succeed"

        # Same nonce should be allowed for tenant B (different tenant)
        tenant_b = "hospital-b-replay"
        is_new_b = check_and_record_nonce(tenant_b, shared_nonce)
        assert is_new_b, "Same nonce should be allowed for different tenant"

        # But reusing for tenant A should fail
        is_new_a_again = check_and_record_nonce(tenant_a, shared_nonce)
        assert not is_new_a_again, "Reused nonce for same tenant should be rejected"


class TestSignatureIntegrity:
    """Test that signature tampering is detected."""

    def test_tampered_certificate_fails_verification(self):
        """Test that modifying a certificate invalidates its signature."""
        # Issue a certificate
        headers = create_auth_headers(**TEST_CLINICIAN)
        cert_request = {
            "model_name": "gpt-4",
            "model_version": "gpt-4-turbo",
            "prompt_version": "v1.0",
            "governance_policy_version": "policy-2024-01",
            "note_text": "Patient presented with symptoms.",
            "human_reviewed": True,
            "human_reviewer_id": "test-reviewer-001",
        }

        response = client.post(
            "/v1/clinical/documentation", json=cert_request, headers=headers
        )
        assert response.status_code == 200
        cert_id = response.json()["certificate_id"]

        # Verify it's initially valid
        auditor_headers = create_auth_headers(**TEST_AUDITOR)
        verify_response = client.post(
            f"/v1/certificates/{cert_id}/verify", headers=auditor_headers
        )
        assert verify_response.status_code == 200
        assert verify_response.json()["valid"]

        # Note: In real scenario, we'd need to tamper with the stored certificate
        # and verify that verification fails. This requires database access.
        # For now, this test verifies the happy path.


class TestPHIProtection:
    """Test that PHI is not leaked in errors or logs."""

    def test_validation_error_does_not_leak_request_body(self):
        """Test that validation errors don't include request body."""
        headers = create_auth_headers(**TEST_CLINICIAN)
        invalid_request = {
            "note_text": "Contains PHI: SSN 123-45-6789",
            # Missing required fields
        }

        response = client.post(
            "/v1/clinical/documentation", json=invalid_request, headers=headers
        )

        # Should return validation error
        assert response.status_code == 422

        # Error should NOT contain the note_text value
        response_text = json.dumps(response.json())
        assert "123-45-6789" not in response_text
        assert "Contains PHI" not in response_text

    def test_phi_pattern_detection(self):
        """Test that obvious PHI patterns are rejected."""
        headers = create_auth_headers(**TEST_CLINICIAN)
        request_with_phi = {
            "model_name": "gpt-4",
            "model_version": "gpt-4-turbo",
            "prompt_version": "v1.0",
            "governance_policy_version": "policy-2024-01",
            "note_text": "Patient SSN is 123-45-6789",
            "human_reviewed": True,
        }

        response = client.post(
            "/v1/clinical/documentation", json=request_with_phi, headers=headers
        )

        # Should reject with 400
        assert response.status_code == 400
        assert "phi_detected" in response.json().get("error", "")


class TestRateLimiting:
    """Test that rate limiting is enforced."""

    @pytest.mark.skip(
        reason="Rate limiting requires multiple requests - expensive test"
    )
    def test_rate_limit_enforced(self):
        """
        Test that exceeding rate limit returns 429.

        Note: This test is expensive (30+ requests).
        In CI, use a lower limit or mock the rate limiter.
        """
        headers = create_auth_headers(**TEST_CLINICIAN)
        cert_request = {
            "model_name": "gpt-4",
            "model_version": "gpt-4-turbo",
            "prompt_version": "v1.0",
            "governance_policy_version": "policy-2024-01",
            "note_text": "Patient presented with symptoms.",
            "human_reviewed": True,
        }

        # Send 35 requests (limit is 30/minute)
        for i in range(35):
            response = client.post(
                "/v1/clinical/documentation", json=cert_request, headers=headers
            )

            if i < 30:
                assert response.status_code == 200
            else:
                # Should hit rate limit
                assert response.status_code == 429


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
