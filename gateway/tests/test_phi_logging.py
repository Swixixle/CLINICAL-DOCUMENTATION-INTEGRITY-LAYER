"""
Tests for PHI (Protected Health Information) logging safety.

Verifies that:
- PHI does not appear in application log output
- STORE_NOTE_TEXT defaults to false
- Clinical endpoints do not log plaintext note content
- Error paths do not leak PHI
"""

import logging
import os
import pytest
from fastapi.testclient import TestClient

from gateway.app.main import app
from gateway.app.db.migrate import ensure_schema
from gateway.tests.auth_helpers import create_clinician_headers


@pytest.fixture(scope="module")
def client():
    """Create a test client with fresh database."""
    ensure_schema()
    return TestClient(app)


def test_store_note_text_defaults_to_false():
    """STORE_NOTE_TEXT env var must default to false."""
    from gateway.app.services.shadow_intake import is_store_note_text_enabled

    # Save and clear env
    original = os.environ.pop("STORE_NOTE_TEXT", None)
    try:
        # Without env var, should default to false
        assert is_store_note_text_enabled() is False
    finally:
        if original is not None:
            os.environ["STORE_NOTE_TEXT"] = original


def test_store_note_text_enabled_when_set():
    """STORE_NOTE_TEXT=true enables storage (explicit opt-in)."""
    from gateway.app.services.shadow_intake import is_store_note_text_enabled

    original = os.environ.get("STORE_NOTE_TEXT")
    try:
        os.environ["STORE_NOTE_TEXT"] = "true"
        assert is_store_note_text_enabled() is True
    finally:
        if original is None:
            os.environ.pop("STORE_NOTE_TEXT", None)
        else:
            os.environ["STORE_NOTE_TEXT"] = original


def test_clinical_endpoint_does_not_log_phi(client, caplog):
    """
    Clinical documentation endpoint must not log plaintext note text.

    This test captures log output during certificate issuance and verifies
    that the raw note content does not appear in any log record.
    """
    sensitive_note = "UNIQUE_SENSITIVE_NOTE_CONTENT_XYZ_789_PHI_TEST"

    request = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-clinical-v1",
        "prompt_version": "soap-note-v1.0",
        "governance_policy_version": "clinical-v1.0",
        "note_text": sensitive_note,
        "human_reviewed": True,
        "human_reviewer_id": "SENSITIVE_REVIEWER_ID_PHI_TEST",
    }
    headers = create_clinician_headers("hospital-phi-log-test")

    with caplog.at_level(logging.DEBUG):
        response = client.post("/v1/clinical/documentation", json=request, headers=headers)

    assert response.status_code == 200

    # Plaintext PHI must not appear in any log record
    for record in caplog.records:
        assert sensitive_note not in record.getMessage(), (
            f"PHI found in log record [{record.levelname}]: {record.getMessage()[:100]}"
        )
        assert "SENSITIVE_REVIEWER_ID_PHI_TEST" not in record.getMessage(), (
            f"Reviewer ID found in log record [{record.levelname}]: {record.getMessage()[:100]}"
        )


def test_certificate_response_does_not_contain_plaintext_phi(client):
    """
    Certificate issuance response must not return plaintext PHI.

    The response should contain only hashes, not the original note text,
    reviewer ID, or patient reference.
    """
    sensitive_note = "UNIQUE_PHI_NOTE_RESPONSE_TEST_ABC_123"
    reviewer_id = "UNIQUE_PHI_REVIEWER_RESPONSE_TEST_DEF_456"
    patient_ref = "UNIQUE_PHI_PATIENT_RESPONSE_TEST_GHI_789"

    request = {
        "model_name": "gpt-4",
        "model_version": "gpt-4-clinical-v1",
        "prompt_version": "soap-note-v1.0",
        "governance_policy_version": "clinical-v1.0",
        "note_text": sensitive_note,
        "human_reviewed": True,
        "human_reviewer_id": reviewer_id,
        "patient_reference": patient_ref,
    }
    headers = create_clinician_headers("hospital-phi-response-test")

    response = client.post("/v1/clinical/documentation", json=request, headers=headers)
    assert response.status_code == 200

    response_text = response.text
    assert sensitive_note not in response_text, "Plaintext note_text found in response"
    assert reviewer_id not in response_text, "Plaintext reviewer_id found in response"
    assert patient_ref not in response_text, "Plaintext patient_reference found in response"


def test_validation_error_does_not_leak_phi(client):
    """
    Validation errors must not echo back any request body content.

    This prevents PHI from leaking via error messages when invalid
    requests are submitted containing note text.
    """
    sensitive_note = "UNIQUE_PHI_VALIDATION_ERROR_TEST_JKL_012"

    # Send a request that will fail validation (missing required fields)
    invalid_request = {
        "note_text": sensitive_note,
        # Missing: model_name, model_version, prompt_version, governance_policy_version
    }
    headers = create_clinician_headers("hospital-phi-validation-test")

    response = client.post("/v1/clinical/documentation", json=invalid_request, headers=headers)

    # Should return a validation error (422)
    assert response.status_code == 422

    # The note text must not appear in the error response
    assert sensitive_note not in response.text, (
        "PHI found in validation error response"
    )


def test_internal_error_does_not_leak_phi(client):
    """
    Internal server errors must return generic messages, not stack traces with PHI.
    """
    # We can't easily trigger a 500 with PHI in it from outside,
    # but we can verify the error handler sanitization is in place
    # by checking that the error handler returns generic messages.
    from gateway.app.main import sanitize_error_detail

    # Verify sanitize_error_detail strips non-dict details
    result = sanitize_error_detail("SENSITIVE_PHI_NOTE: patient has condition X")
    assert "SENSITIVE_PHI_NOTE" not in str(result)
    assert result.get("error") == "internal_error"

    # Verify dict details pass through (assumed pre-sanitized)
    pre_sanitized = {"error": "not_found", "message": "Certificate not found"}
    result = sanitize_error_detail(pre_sanitized)
    assert result == pre_sanitized
