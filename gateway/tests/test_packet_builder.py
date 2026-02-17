"""
Tests for packet builder and cross-tool determinism.

These tests verify that:
1. The packet builder assembles packets correctly
2. Packets can be serialized, deserialized, and recomputed deterministically
3. The complete workflow maintains cryptographic integrity
"""

import json
import pytest
from pathlib import Path

from gateway.app.services.packet_builder import build_accountability_packet
from gateway.app.services.halo import verify_halo_chain, build_halo_chain
from gateway.app.services.signer import verify_signature


def test_build_accountability_packet():
    """Test that accountability packet is built correctly."""
    execution = {
        "outcome": "approved",
        "output_hash": "sha256:output123",
        "token_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "latency_ms": 500,
        "denial_reason": None
    }
    
    packet = build_accountability_packet(
        transaction_id="tx-test-001",
        gateway_timestamp_utc="2024-01-15T10:30:00.000Z",
        environment="production",
        client_id="client-test-01",
        intent_manifest="text-generation",
        feature_tag="test-feature",
        user_ref="user-123",
        prompt_hash="sha256:prompt123",
        rag_hash=None,
        multimodal_hash=None,
        policy_version_hash="sha256:policy123",
        policy_change_ref="change-001",
        rules_applied=["rule1", "rule2"],
        model_fingerprint="gpt-4",
        param_snapshot={"temperature": 0.7},
        execution=execution
    )
    
    # Verify top-level structure
    assert packet["transaction_id"] == "tx-test-001"
    assert packet["client_id"] == "client-test-01"
    assert packet["environment"] == "production"
    assert packet["gateway_timestamp_utc"] == "2024-01-15T10:30:00.000Z"
    
    # Verify intent fields
    assert packet["intent_manifest"] == "text-generation"
    assert packet["feature_tag"] == "test-feature"
    assert packet["user_ref"] == "user-123"
    
    # Verify model fields
    assert packet["model_fingerprint"] == "gpt-4"
    assert packet["param_snapshot"] == {"temperature": 0.7}
    
    # Verify content hashes
    assert packet["prompt_hash"] == "sha256:prompt123"
    assert packet["rag_hash"] is None
    assert packet["multimodal_hash"] is None
    
    # Verify policy receipt
    assert "policy_receipt" in packet
    assert packet["policy_receipt"]["policy_version_hash"] == "sha256:policy123"
    assert packet["policy_receipt"]["policy_change_ref"] == "change-001"
    assert packet["policy_receipt"]["rules_applied"] == ["rule1", "rule2"]
    
    # Verify execution
    assert "execution" in packet
    assert packet["execution"]["outcome"] == "approved"
    
    # Verify HALO chain
    assert "halo_chain" in packet
    assert packet["halo_chain"]["halo_version"] == "v1"
    assert len(packet["halo_chain"]["blocks"]) == 5
    
    # Verify verification bundle
    assert "verification" in packet
    assert packet["verification"]["alg"] == "ECDSA_SHA_256"
    assert "signature_b64" in packet["verification"]
    
    # Verify protocol metadata
    assert "protocol_metadata" in packet
    assert packet["protocol_metadata"]["halo_version"] == "v1"
    assert packet["protocol_metadata"]["c14n_version"] == "json_c14n_v1"
    assert packet["protocol_metadata"]["signing_alg"] == "ECDSA_SHA_256"


def test_packet_no_wrapper():
    """Test that packet has no packet_inputs wrapper."""
    execution = {
        "outcome": "approved",
        "output_hash": "sha256:output123",
        "token_usage": None,
        "latency_ms": 100,
        "denial_reason": None
    }
    
    packet = build_accountability_packet(
        transaction_id="tx-test-002",
        gateway_timestamp_utc="2024-01-15T10:30:00.000Z",
        environment="production",
        client_id="client-test-02",
        intent_manifest="text-generation",
        feature_tag="test-feature",
        user_ref="user-123",
        prompt_hash="sha256:prompt123",
        rag_hash=None,
        multimodal_hash=None,
        policy_version_hash="sha256:policy123",
        policy_change_ref="change-001",
        rules_applied=["rule1"],
        model_fingerprint="gpt-4",
        param_snapshot={"temperature": 0.7},
        execution=execution
    )
    
    # Ensure no packet_inputs key exists
    assert "packet_inputs" not in packet
    
    # Ensure all fields are at top level
    assert "transaction_id" in packet
    assert "intent_manifest" in packet
    assert "prompt_hash" in packet


def test_cross_tool_determinism():
    """
    Test: Cross-Tool Determinism Guarantee
    
    This test ensures that:
    1. A packet can be serialized to JSON
    2. The JSON can be deserialized
    3. HALO can be recomputed from the deserialized data
    4. The signature can be verified
    5. The final_hash remains identical throughout
    """
    # Step 1: Build the original packet
    execution = {
        "outcome": "approved",
        "output_hash": "sha256:output123",
        "token_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "latency_ms": 500,
        "denial_reason": None
    }
    
    original_packet = build_accountability_packet(
        transaction_id="tx-determinism-001",
        gateway_timestamp_utc="2024-01-15T10:30:00.000Z",
        environment="production",
        client_id="client-test-01",
        intent_manifest="text-generation",
        feature_tag="test-feature",
        user_ref="user-123",
        prompt_hash="sha256:prompt123",
        rag_hash=None,
        multimodal_hash=None,
        policy_version_hash="sha256:policy123",
        policy_change_ref="change-001",
        rules_applied=["rule1", "rule2"],
        model_fingerprint="gpt-4",
        param_snapshot={"temperature": 0.7},
        execution=execution
    )
    
    original_final_hash = original_packet["halo_chain"]["final_hash"]
    
    # Step 2: Serialize to JSON
    serialized = json.dumps(original_packet, sort_keys=True)
    
    # Step 3: Deserialize from JSON
    deserialized_packet = json.loads(serialized)
    
    # Step 4: Recompute HALO chain from deserialized data
    recomputed_halo = build_halo_chain(
        transaction_id=deserialized_packet["transaction_id"],
        gateway_timestamp_utc=deserialized_packet["gateway_timestamp_utc"],
        environment=deserialized_packet["environment"],
        client_id=deserialized_packet["client_id"],
        intent_manifest=deserialized_packet["intent_manifest"],
        feature_tag=deserialized_packet["feature_tag"],
        user_ref=deserialized_packet["user_ref"],
        prompt_hash=deserialized_packet["prompt_hash"],
        rag_hash=deserialized_packet["rag_hash"],
        multimodal_hash=deserialized_packet["multimodal_hash"],
        policy_version_hash=deserialized_packet["policy_receipt"]["policy_version_hash"],
        policy_change_ref=deserialized_packet["policy_receipt"]["policy_change_ref"],
        rules_applied=deserialized_packet["policy_receipt"]["rules_applied"],
        model_fingerprint=deserialized_packet["model_fingerprint"],
        param_snapshot=deserialized_packet["param_snapshot"],
        execution=deserialized_packet["execution"]
    )
    
    # Step 5: Verify that final_hash is identical
    assert recomputed_halo["final_hash"] == original_final_hash
    assert recomputed_halo["final_hash"] == deserialized_packet["halo_chain"]["final_hash"]
    
    # Step 6: Verify the HALO chain integrity
    verification_result = verify_halo_chain(recomputed_halo)
    assert verification_result["valid"] is True
    
    # Step 7: Verify the signature
    jwk_path = Path(__file__).parent.parent / "app" / "dev_keys" / "dev_public.jwk.json"
    with open(jwk_path, 'r') as f:
        jwk = json.load(f)
    
    signature_valid = verify_signature(deserialized_packet["verification"], jwk)
    assert signature_valid is True
    
    # Step 8: Verify canonical message matches
    expected_message = {
        "transaction_id": deserialized_packet["transaction_id"],
        "gateway_timestamp_utc": deserialized_packet["gateway_timestamp_utc"],
        "final_hash": deserialized_packet["halo_chain"]["final_hash"],
        "policy_version_hash": deserialized_packet["policy_receipt"]["policy_version_hash"]
    }
    assert deserialized_packet["verification"]["message"] == expected_message


def test_protocol_version_pins():
    """Test that protocol version pins are included in packet."""
    execution = {
        "outcome": "approved",
        "output_hash": "sha256:output123",
        "token_usage": None,
        "latency_ms": 100,
        "denial_reason": None
    }
    
    packet = build_accountability_packet(
        transaction_id="tx-test-003",
        gateway_timestamp_utc="2024-01-15T10:30:00.000Z",
        environment="production",
        client_id="client-test-03",
        intent_manifest="text-generation",
        feature_tag="test-feature",
        user_ref="user-123",
        prompt_hash="sha256:prompt123",
        rag_hash=None,
        multimodal_hash=None,
        policy_version_hash="sha256:policy123",
        policy_change_ref="change-001",
        rules_applied=["rule1"],
        model_fingerprint="gpt-4",
        param_snapshot={"temperature": 0.7},
        execution=execution
    )
    
    # Verify protocol metadata exists
    assert "protocol_metadata" in packet
    metadata = packet["protocol_metadata"]
    
    # Verify all version pins are present
    assert "halo_version" in metadata
    assert "c14n_version" in metadata
    assert "signing_alg" in metadata
    
    # Verify values match constants
    assert metadata["halo_version"] == "v1"
    assert metadata["c14n_version"] == "json_c14n_v1"
    assert metadata["signing_alg"] == "ECDSA_SHA_256"


def test_packet_with_denied_outcome():
    """Test packet building for denied transactions."""
    execution = {
        "outcome": "denied",
        "output_hash": None,
        "token_usage": None,
        "latency_ms": 50,
        "denial_reason": "Model not approved"
    }
    
    packet = build_accountability_packet(
        transaction_id="tx-denied-001",
        gateway_timestamp_utc="2024-01-15T10:30:00.000Z",
        environment="production",
        client_id="client-test-04",
        intent_manifest="text-generation",
        feature_tag="test-feature",
        user_ref="user-123",
        prompt_hash="sha256:prompt123",
        rag_hash=None,
        multimodal_hash=None,
        policy_version_hash="sha256:policy123",
        policy_change_ref="change-001",
        rules_applied=["model-not-approved"],
        model_fingerprint="gpt-5-preview",
        param_snapshot={"temperature": 0.7},
        execution=execution
    )
    
    # Verify execution outcome
    assert packet["execution"]["outcome"] == "denied"
    assert packet["execution"]["denial_reason"] == "Model not approved"
    assert packet["execution"]["output_hash"] is None
    
    # Verify HALO chain is still valid
    verification_result = verify_halo_chain(packet["halo_chain"])
    assert verification_result["valid"] is True
    
    # Verify signature is still valid
    jwk_path = Path(__file__).parent.parent / "app" / "dev_keys" / "dev_public.jwk.json"
    with open(jwk_path, 'r') as f:
        jwk = json.load(f)
    
    signature_valid = verify_signature(packet["verification"], jwk)
    assert signature_valid is True
