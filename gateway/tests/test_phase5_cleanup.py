"""
Tests for Phase 5 security cleanup - no legacy signing fallback.

Validates that:
- Signing without tenant_id raises ValueError
- All routes properly provide tenant_id
- No legacy dev key fallback path exists
"""

import pytest
from gateway.app.services.signer import sign_generic_message


def test_sign_without_tenant_id_raises_error():
    """Test that signing without tenant_id raises ValueError."""
    message = {"test": "data", "field": "value"}

    # Should raise ValueError when tenant_id is None
    with pytest.raises(ValueError) as exc_info:
        sign_generic_message(message, tenant_id=None)

    error_message = str(exc_info.value)
    assert "tenant_id is required" in error_message
    assert "Legacy fallback" in error_message


def test_sign_with_empty_tenant_id_raises_error():
    """Test that signing with empty tenant_id raises ValueError."""
    message = {"test": "data", "field": "value"}

    # Should raise ValueError when tenant_id is empty string
    with pytest.raises(ValueError) as exc_info:
        sign_generic_message(message, tenant_id="")

    error_message = str(exc_info.value)
    assert "tenant_id is required" in error_message


def test_sign_with_valid_tenant_id_succeeds():
    """Test that signing with valid tenant_id succeeds."""
    from pathlib import Path
    import tempfile
    import shutil
    from gateway.app.db.migrate import ensure_schema
    from gateway.app.services.storage import bootstrap_dev_keys

    # Setup test database
    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "test.db"

    import gateway.app.db.migrate as migrate_module

    original_get_db_path = migrate_module.get_db_path
    migrate_module.get_db_path = lambda: temp_db_path

    try:
        ensure_schema()
        bootstrap_dev_keys()

        message = {
            "certificate_id": "test-cert-001",
            "tenant_id": "test-tenant",
            "timestamp": "2026-02-18T10:00:00Z",
        }

        # Should succeed with valid tenant_id
        result = sign_generic_message(message, tenant_id="test-tenant")

        assert "signature" in result
        assert "key_id" in result
        assert "algorithm" in result
        assert result["algorithm"] == "ECDSA_SHA_256"
        assert "canonical_message" in result

        # Canonical message should have nonce and server_timestamp
        canonical = result["canonical_message"]
        assert "nonce" in canonical
        assert "server_timestamp" in canonical

    finally:
        migrate_module.get_db_path = original_get_db_path
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_clinical_endpoint_provides_tenant_id():
    """Test that clinical certificate issuance endpoint provides tenant_id."""
    from fastapi.testclient import TestClient
    from pathlib import Path
    import tempfile
    import shutil

    from gateway.app.main import app
    from gateway.app.db.migrate import ensure_schema
    from gateway.app.services.storage import bootstrap_dev_keys
    from gateway.tests.auth_helpers import create_clinician_headers

    # Setup test database
    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "test.db"

    import gateway.app.db.migrate as migrate_module

    original_get_db_path = migrate_module.get_db_path
    migrate_module.get_db_path = lambda: temp_db_path

    try:
        ensure_schema()
        bootstrap_dev_keys()

        client = TestClient(app)

        # Issue a certificate - this should work because clinical endpoint provides tenant_id
        request_data = {
            "model_name": "gpt-4",
            "model_version": "gpt-4-turbo",
            "prompt_version": "clinical-v1.2",
            "governance_policy_version": "CDOC-Policy-v1",
            "note_text": "Test note content",
            "human_reviewed": True,
            "human_reviewer_id": "test-reviewer-001",
            "encounter_id": "ENC-TEST",
        }

        headers = create_clinician_headers("test-tenant-phase5")
        response = client.post(
            "/v1/clinical/documentation", json=request_data, headers=headers
        )

        # Should succeed (no ValueError about missing tenant_id)
        assert response.status_code == 200
        data = response.json()
        assert "certificate_id" in data
        assert "certificate" in data

        # Certificate should have per-tenant signature
        cert = data["certificate"]
        assert "signature" in cert
        assert cert["signature"]["key_id"] != "dev-key-01"  # Not the legacy dev key

    finally:
        migrate_module.get_db_path = original_get_db_path
        shutil.rmtree(temp_dir, ignore_errors=True)
