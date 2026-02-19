"""
Tests for deterministic JSON canonicalization.

These tests verify that json_c14n_v1 produces consistent, deterministic output
and properly handles edge cases including rejection of non-finite numbers.
"""

import json
import pytest
from pathlib import Path

from gateway.app.services.c14n import json_c14n_v1


def test_c14n_vectors():
    """Test canonicalization against standardized test vectors."""
    vectors_path = Path(__file__).parent / "vectors" / "c14n_vectors.json"

    with open(vectors_path, "r", encoding="utf-8") as f:
        vectors = json.load(f)

    for vector in vectors:
        name = vector["name"]
        input_obj = vector["input"]
        expected = vector["expected"]

        result = json_c14n_v1(input_obj).decode("utf-8")

        assert result == expected, (
            f"Vector '{name}' failed:\n"
            f"  Expected: {expected}\n"
            f"  Got:      {result}"
        )


def test_reject_nan():
    """Test that NaN is rejected."""
    with pytest.raises(ValueError, match="Non-finite"):
        json_c14n_v1({"value": float("nan")})


def test_reject_infinity():
    """Test that Infinity is rejected."""
    with pytest.raises(ValueError, match="Non-finite"):
        json_c14n_v1({"value": float("inf")})


def test_reject_negative_infinity():
    """Test that -Infinity is rejected."""
    with pytest.raises(ValueError, match="Non-finite"):
        json_c14n_v1({"value": float("-inf")})


def test_reject_unsupported_type():
    """Test that unsupported types are rejected."""
    with pytest.raises(ValueError, match="Unsupported type"):
        json_c14n_v1({"value": set([1, 2, 3])})


def test_reject_non_string_keys():
    """Test that non-string dictionary keys are rejected."""
    # Python allows this but it's not JSON-compatible
    invalid_dict = {1: "value"}
    with pytest.raises((ValueError, TypeError)):
        json_c14n_v1(invalid_dict)


def test_determinism():
    """Test that identical inputs always produce identical outputs."""
    obj1 = {"z": 1, "a": 2, "items": [3, 2, 1]}
    obj2 = {"a": 2, "z": 1, "items": [3, 2, 1]}

    result1 = json_c14n_v1(obj1)
    result2 = json_c14n_v1(obj2)

    assert result1 == result2


def test_utf8_encoding():
    """Test that output is properly UTF-8 encoded."""
    obj = {"emoji": "🎉", "chinese": "你好"}
    result = json_c14n_v1(obj)

    # Should be bytes
    assert isinstance(result, bytes)

    # Should decode as UTF-8
    decoded = result.decode("utf-8")
    assert "🎉" in decoded
    assert "你好" in decoded
