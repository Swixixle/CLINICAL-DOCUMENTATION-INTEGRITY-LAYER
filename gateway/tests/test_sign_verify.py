"""
Tests for cryptographic signing and verification.

These tests verify that messages can be signed and verified correctly,
and that tampering is properly detected.
"""

import json
import pytest
from pathlib import Path

from gateway.app.services.signer import sign_message, verify_signature


def test_sign_and_verify():
    """Test that a signed message can be verified."""
    message = {
        "transaction_id": "tx-test-001",
        "gateway_timestamp_utc": "2024-01-15T10:30:00.000Z",
        "final_hash": "sha256:abc123",
        "policy_version_hash": "sha256:policy123",
    }

    # Sign the message
    bundle = sign_message(message)

    # Verify structure
    assert bundle["alg"] == "ECDSA_SHA_256"
    assert bundle["key_id"] == "dev-key-01"
    assert bundle["message"] == message
    assert "signature_b64" in bundle
    assert "signed_at_utc" in bundle

    # Load public key
    jwk_path = Path(__file__).parent.parent / "app" / "dev_keys" / "dev_public.jwk.json"
    with open(jwk_path, "r") as f:
        jwk = json.load(f)

    # Verify signature
    is_valid = verify_signature(bundle, jwk)
    assert is_valid is True


def test_tampering_detected():
    """Test that tampering with message breaks verification."""
    message = {
        "transaction_id": "tx-test-002",
        "gateway_timestamp_utc": "2024-01-15T10:30:00.000Z",
        "final_hash": "sha256:def456",
        "policy_version_hash": "sha256:policy456",
    }

    # Sign the message
    bundle = sign_message(message)

    # Load public key
    jwk_path = Path(__file__).parent.parent / "app" / "dev_keys" / "dev_public.jwk.json"
    with open(jwk_path, "r") as f:
        jwk = json.load(f)

    # Verify original is valid
    assert verify_signature(bundle, jwk) is True

    # Tamper with message
    bundle["message"]["transaction_id"] = "TAMPERED"

    # Should fail verification
    assert verify_signature(bundle, jwk) is False


def test_signature_tampering_detected():
    """Test that tampering with signature is detected."""
    message = {
        "transaction_id": "tx-test-003",
        "gateway_timestamp_utc": "2024-01-15T10:30:00.000Z",
        "final_hash": "sha256:abc789",
        "policy_version_hash": "sha256:policy789",
    }

    # Sign the message
    bundle = sign_message(message)

    # Load public key
    jwk_path = Path(__file__).parent.parent / "app" / "dev_keys" / "dev_public.jwk.json"
    with open(jwk_path, "r") as f:
        jwk = json.load(f)

    # Verify original is valid
    assert verify_signature(bundle, jwk) is True

    # Tamper with signature (flip one bit)
    sig_bytes = bundle["signature_b64"].encode("utf-8")
    if sig_bytes[0] == ord("A"):
        tampered = "B" + bundle["signature_b64"][1:]
    else:
        tampered = "A" + bundle["signature_b64"][1:]
    bundle["signature_b64"] = tampered

    # Should fail verification
    assert verify_signature(bundle, jwk) is False


def test_deterministic_canonicalization_in_signing():
    """Test that signing uses deterministic canonicalization."""
    # Two dicts with different key order but same content
    # Using the canonical 4-field message format
    message1 = {
        "transaction_id": "tx-test-001",
        "gateway_timestamp_utc": "2024-01-15T10:30:00.000Z",
        "final_hash": "sha256:abc123",
        "policy_version_hash": "sha256:policy123",
    }
    message2 = {
        "policy_version_hash": "sha256:policy123",
        "final_hash": "sha256:abc123",
        "transaction_id": "tx-test-001",
        "gateway_timestamp_utc": "2024-01-15T10:30:00.000Z",
    }

    bundle1 = sign_message(message1)
    bundle2 = sign_message(message2)

    # Load public key
    jwk_path = Path(__file__).parent.parent / "app" / "dev_keys" / "dev_public.jwk.json"
    with open(jwk_path, "r") as f:
        jwk = json.load(f)

    # Both should verify with the same public key
    # Note: ECDSA signatures have randomness, so they won't be byte-identical
    # But both should verify correctly since canonical form is identical
    assert verify_signature(bundle1, jwk) is True
    assert verify_signature(bundle2, jwk) is True

    # Cross-verify: bundle1's signature should verify bundle2's message
    # because canonical form is identical
    bundle1_sig_with_message2 = {
        "message": message2,
        "signature_b64": bundle1["signature_b64"],
        "alg": bundle1["alg"],
        "key_id": bundle1["key_id"],
    }
    assert verify_signature(bundle1_sig_with_message2, jwk) is True


def test_verify_invalid_bundle():
    """Test that invalid bundles return False."""
    jwk_path = Path(__file__).parent.parent / "app" / "dev_keys" / "dev_public.jwk.json"
    with open(jwk_path, "r") as f:
        jwk = json.load(f)

    # Empty bundle
    assert verify_signature({}, jwk) is False

    # Missing message
    assert verify_signature({"signature_b64": "abc"}, jwk) is False

    # Missing signature
    assert (
        verify_signature(
            {
                "message": {
                    "transaction_id": "test",
                    "gateway_timestamp_utc": "2024-01-15T10:30:00.000Z",
                    "final_hash": "sha256:test",
                    "policy_version_hash": "sha256:policy",
                }
            },
            jwk,
        )
        is False
    )


def test_canonical_message_contract_enforced():
    """Test that only the 4 canonical fields are accepted in signing."""
    # Valid message with exactly 4 fields
    valid_message = {
        "transaction_id": "tx-test-001",
        "gateway_timestamp_utc": "2024-01-15T10:30:00.000Z",
        "final_hash": "sha256:abc123",
        "policy_version_hash": "sha256:policy123",
    }

    # Should succeed
    bundle = sign_message(valid_message)
    assert bundle["message"] == valid_message

    # Message with extra field
    invalid_message_extra = {
        "transaction_id": "tx-test-002",
        "gateway_timestamp_utc": "2024-01-15T10:30:00.000Z",
        "final_hash": "sha256:abc123",
        "policy_version_hash": "sha256:policy123",
        "extra_field": "should_not_be_here",
    }

    # Should raise ValueError
    with pytest.raises(ValueError, match="Message must contain exactly these fields"):
        sign_message(invalid_message_extra)

    # Message with missing field
    invalid_message_missing = {
        "transaction_id": "tx-test-003",
        "final_hash": "sha256:abc123",
        "policy_version_hash": "sha256:policy123",
    }

    # Should raise ValueError
    with pytest.raises(ValueError, match="Message must contain exactly these fields"):
        sign_message(invalid_message_missing)
