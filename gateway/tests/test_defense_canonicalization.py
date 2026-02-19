"""
Tests for Courtroom Defense Mode - Canonicalization and Provenance Hardening.

Phase 1: Provenance Hardening Tests
- Identical payload produces identical hash
- Single character mutation produces different hash
- All required provenance fields are present in canonical message
- Canonical message is deterministic
"""

import pytest
from gateway.app.services.c14n import json_c14n_v1
from gateway.app.services.hashing import sha256_hex


def test_identical_payload_produces_identical_hash():
    """
    Test that same payload always produces identical hash.

    This is critical for signature verification - any non-determinism
    would break verification.
    """
    payload = {
        "certificate_id": "01HXYZ-test",
        "tenant_id": "hospital-alpha",
        "note_hash": "abc123",
        "model_name": "gpt-4",
        "model_version": "2024-01-15",
        "timestamp": "2024-01-15T10:00:00Z",
    }

    # Canonicalize twice
    canonical_1 = json_c14n_v1(payload)
    canonical_2 = json_c14n_v1(payload)

    # Should be byte-identical
    assert canonical_1 == canonical_2

    # Hashes should match
    hash_1 = sha256_hex(canonical_1)
    hash_2 = sha256_hex(canonical_2)
    assert hash_1 == hash_2


def test_single_character_mutation_changes_hash():
    """
    Test that even a single character change produces different hash.

    This ensures tamper detection - any alteration to the canonical
    message will be detected.
    """
    original_payload = {
        "certificate_id": "01HXYZ-test",
        "tenant_id": "hospital-alpha",
        "note_hash": "abc123",
        "model_name": "gpt-4",
        "model_version": "2024-01-15",
    }

    # Create mutated payload (change one character in note_hash)
    mutated_payload = original_payload.copy()
    mutated_payload["note_hash"] = "abc124"  # Changed last digit

    # Canonicalize both
    canonical_original = json_c14n_v1(original_payload)
    canonical_mutated = json_c14n_v1(mutated_payload)

    # Canonical bytes should differ
    assert canonical_original != canonical_mutated

    # Hashes should differ
    hash_original = sha256_hex(canonical_original)
    hash_mutated = sha256_hex(canonical_mutated)
    assert hash_original != hash_mutated


def test_key_order_does_not_matter():
    """
    Test that different key ordering produces same canonical form.

    This ensures canonicalization is truly order-independent.
    """
    payload_1 = {"z_field": "last", "a_field": "first", "m_field": "middle"}

    payload_2 = {"a_field": "first", "m_field": "middle", "z_field": "last"}

    canonical_1 = json_c14n_v1(payload_1)
    canonical_2 = json_c14n_v1(payload_2)

    # Should be identical (keys sorted alphabetically)
    assert canonical_1 == canonical_2

    # Should produce: {"a_field":"first","m_field":"middle","z_field":"last"}
    expected = b'{"a_field":"first","m_field":"middle","z_field":"last"}'
    assert canonical_1 == expected


def test_whitespace_does_not_matter():
    """
    Test that whitespace in input dict doesn't affect canonical form.

    Canonicalization strips all whitespace outside strings.
    """
    # Both should produce same canonical form regardless of Python formatting
    payload = {"field": "value", "number": 42}

    canonical = json_c14n_v1(payload)

    # No whitespace in output (compact JSON)
    assert b" " not in canonical
    assert b"\n" not in canonical
    assert b"\t" not in canonical


def test_required_provenance_fields_canonicalization():
    """
    Test that all required provenance fields for Courtroom Defense Mode
    are properly canonicalized.

    This verifies the expanded canonical message format.
    """
    full_provenance = {
        "certificate_id": "01HXYZ-test",
        "chain_hash": "chain_hash_value",
        "governance_policy_hash": "policy_hash_value",
        "governance_policy_version": "v1.0.0",
        "human_attested_at_utc": "2024-01-15T10:00:00Z",
        "human_reviewed": True,
        "human_reviewer_id_hash": "reviewer_hash_value",
        "issued_at_utc": "2024-01-15T10:00:00Z",
        "key_id": "key-123",
        "model_name": "gpt-4",
        "model_version": "2024-01-15",
        "note_hash": "note_hash_value",
        "nonce": "nonce-uuid7",
        "prompt_version": "v2.0.0",
        "server_timestamp": "2024-01-15T10:00:01Z",
        "tenant_id": "hospital-alpha",
    }

    # Should canonicalize without error
    canonical = json_c14n_v1(full_provenance)

    # Should be deterministic
    canonical_2 = json_c14n_v1(full_provenance)
    assert canonical == canonical_2

    # Keys should be alphabetically sorted in output
    canonical_str = canonical.decode("utf-8")

    # Verify some key ordering (certificate_id should come before tenant_id)
    cert_id_pos = canonical_str.index('"certificate_id"')
    tenant_id_pos = canonical_str.index('"tenant_id"')
    assert cert_id_pos < tenant_id_pos

    # Verify all fields are present in canonical form
    required_fields = [
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
        "note_hash",
        "nonce",
        "prompt_version",
        "server_timestamp",
        "tenant_id",
    ]

    for field in required_fields:
        assert f'"{field}"' in canonical_str


def test_null_values_canonicalize_correctly():
    """
    Test that null/None values are properly canonicalized as "null".

    Important for optional fields like human_attested_at_utc when
    human_reviewed is false.
    """
    payload = {
        "field_with_value": "value",
        "field_with_null": None,
        "boolean_field": False,
    }

    canonical = json_c14n_v1(payload)
    canonical_str = canonical.decode("utf-8")

    # Should contain "null" not "None"
    assert '"field_with_null":null' in canonical_str
    assert "None" not in canonical_str

    # Boolean should be lowercase
    assert '"boolean_field":false' in canonical_str


def test_nested_structures_canonicalize():
    """
    Test that nested dictionaries and lists are properly canonicalized.
    """
    payload = {
        "metadata": {"version": "1.0", "author": "system"},
        "tags": ["tag2", "tag1", "tag3"],
    }

    canonical = json_c14n_v1(payload)

    # Should be deterministic
    canonical_2 = json_c14n_v1(payload)
    assert canonical == canonical_2

    canonical_str = canonical.decode("utf-8")

    # Nested dict keys should be sorted
    assert '"metadata":{"author":"system","version":"1.0"}' in canonical_str

    # List order should be preserved (not sorted)
    assert '["tag2","tag1","tag3"]' in canonical_str


def test_unicode_handling():
    """
    Test that Unicode characters are properly handled in canonicalization.
    """
    payload = {
        "message": "Hello 世界",  # Chinese characters
        "emoji": "🔒",  # Emoji
        "accents": "Café",  # Accents
    }

    canonical = json_c14n_v1(payload)

    # Should be UTF-8 encoded
    assert isinstance(canonical, bytes)

    # Should decode back correctly
    canonical_str = canonical.decode("utf-8")
    assert "Hello 世界" in canonical_str
    assert "🔒" in canonical_str
    assert "Café" in canonical_str


def test_invalid_types_rejected():
    """
    Test that unsupported types are rejected.
    """

    # Test with custom object
    class CustomObject:
        pass

    payload = {"field": CustomObject()}

    with pytest.raises(ValueError, match="Unsupported type"):
        json_c14n_v1(payload)

    # Test with NaN
    payload_nan = {"field": float("nan")}

    with pytest.raises(ValueError, match="Non-finite float"):
        json_c14n_v1(payload_nan)


def test_empty_payload():
    """
    Test that empty payload canonicalizes correctly.
    """
    payload = {}

    canonical = json_c14n_v1(payload)

    assert canonical == b"{}"


def test_determinism_across_iterations():
    """
    Test that canonicalization is deterministic across multiple iterations.

    Run canonicalization 100 times and verify all outputs are identical.
    """
    payload = {
        "certificate_id": "test-cert",
        "tenant_id": "test-tenant",
        "note_hash": "hash123",
        "timestamp": "2024-01-15T10:00:00Z",
        "nested": {"field1": "value1", "field2": "value2"},
    }

    results = [json_c14n_v1(payload) for _ in range(100)]

    # All results should be identical
    first_result = results[0]
    for result in results[1:]:
        assert result == first_result
