"""
Tests for HALO chain (Hash-Linked Accountability Ledger).

These tests verify that the HALO chain is built correctly, produces
deterministic hashes, and properly detects tampering.
"""

import json
import pytest
from pathlib import Path

from gateway.app.services.halo import build_halo_chain, verify_halo_chain


def test_halo_build_from_sample_packet():
    """Test that HALO chain can be built from sample packet."""
    vectors_path = Path(__file__).parent / "vectors" / "halo_sample_packet.json"
    
    with open(vectors_path, 'r', encoding='utf-8') as f:
        full_packet = json.load(f)
    
    # Extract fields from the flat packet structure
    halo = build_halo_chain(
        transaction_id=full_packet["transaction_id"],
        gateway_timestamp_utc=full_packet["gateway_timestamp_utc"],
        environment=full_packet["environment"],
        client_id=full_packet["client_id"],
        intent_manifest=full_packet["intent_manifest"],
        feature_tag=full_packet["feature_tag"],
        user_ref=full_packet["user_ref"],
        prompt_hash=full_packet["prompt_hash"],
        rag_hash=full_packet["rag_hash"],
        multimodal_hash=full_packet["multimodal_hash"],
        policy_version_hash=full_packet["policy_receipt"]["policy_version_hash"],
        policy_change_ref=full_packet["policy_receipt"]["policy_change_ref"],
        rules_applied=full_packet["policy_receipt"]["rules_applied"],
        model_fingerprint=full_packet["model_fingerprint"],
        param_snapshot=full_packet["param_snapshot"],
        execution=full_packet["execution"]
    )
    
    # Verify structure
    assert halo["halo_version"] == "v1"
    assert len(halo["blocks"]) == 5
    assert len(halo["block_hashes"]) == 5
    assert halo["final_hash"] == halo["block_hashes"][4]
    
    # Verify block structure
    block1 = halo["blocks"][0]
    assert "transaction_id" in block1
    assert "gateway_timestamp_utc" in block1
    assert "environment" in block1
    assert "client_id" in block1
    assert "prev_hash" not in block1  # Genesis has no prev_hash
    
    # All other blocks should have prev_hash
    for i in range(1, 5):
        assert "prev_hash" in halo["blocks"][i]


def test_halo_verification_valid():
    """Test that a valid HALO chain passes verification."""
    vectors_path = Path(__file__).parent / "vectors" / "halo_sample_packet.json"
    
    with open(vectors_path, 'r', encoding='utf-8') as f:
        full_packet = json.load(f)
    
    # Extract fields from the flat packet structure
    halo = build_halo_chain(
        transaction_id=full_packet["transaction_id"],
        gateway_timestamp_utc=full_packet["gateway_timestamp_utc"],
        environment=full_packet["environment"],
        client_id=full_packet["client_id"],
        intent_manifest=full_packet["intent_manifest"],
        feature_tag=full_packet["feature_tag"],
        user_ref=full_packet["user_ref"],
        prompt_hash=full_packet["prompt_hash"],
        rag_hash=full_packet["rag_hash"],
        multimodal_hash=full_packet["multimodal_hash"],
        policy_version_hash=full_packet["policy_receipt"]["policy_version_hash"],
        policy_change_ref=full_packet["policy_receipt"]["policy_change_ref"],
        rules_applied=full_packet["policy_receipt"]["rules_applied"],
        model_fingerprint=full_packet["model_fingerprint"],
        param_snapshot=full_packet["param_snapshot"],
        execution=full_packet["execution"]
    )
    result = verify_halo_chain(halo)
    
    assert result["valid"] is True
    assert len(result["discrepancies"]) == 0


def test_halo_determinism():
    """Test that identical inputs produce identical HALO chains."""
    vectors_path = Path(__file__).parent / "vectors" / "halo_sample_packet.json"
    
    with open(vectors_path, 'r', encoding='utf-8') as f:
        full_packet = json.load(f)
    
    # Extract fields from the flat packet structure
    halo1 = build_halo_chain(
        transaction_id=full_packet["transaction_id"],
        gateway_timestamp_utc=full_packet["gateway_timestamp_utc"],
        environment=full_packet["environment"],
        client_id=full_packet["client_id"],
        intent_manifest=full_packet["intent_manifest"],
        feature_tag=full_packet["feature_tag"],
        user_ref=full_packet["user_ref"],
        prompt_hash=full_packet["prompt_hash"],
        rag_hash=full_packet["rag_hash"],
        multimodal_hash=full_packet["multimodal_hash"],
        policy_version_hash=full_packet["policy_receipt"]["policy_version_hash"],
        policy_change_ref=full_packet["policy_receipt"]["policy_change_ref"],
        rules_applied=full_packet["policy_receipt"]["rules_applied"],
        model_fingerprint=full_packet["model_fingerprint"],
        param_snapshot=full_packet["param_snapshot"],
        execution=full_packet["execution"]
    )
    halo2 = build_halo_chain(
        transaction_id=full_packet["transaction_id"],
        gateway_timestamp_utc=full_packet["gateway_timestamp_utc"],
        environment=full_packet["environment"],
        client_id=full_packet["client_id"],
        intent_manifest=full_packet["intent_manifest"],
        feature_tag=full_packet["feature_tag"],
        user_ref=full_packet["user_ref"],
        prompt_hash=full_packet["prompt_hash"],
        rag_hash=full_packet["rag_hash"],
        multimodal_hash=full_packet["multimodal_hash"],
        policy_version_hash=full_packet["policy_receipt"]["policy_version_hash"],
        policy_change_ref=full_packet["policy_receipt"]["policy_change_ref"],
        rules_applied=full_packet["policy_receipt"]["rules_applied"],
        model_fingerprint=full_packet["model_fingerprint"],
        param_snapshot=full_packet["param_snapshot"],
        execution=full_packet["execution"]
    )
    
    assert halo1["final_hash"] == halo2["final_hash"]
    assert halo1["block_hashes"] == halo2["block_hashes"]


def test_halo_tampering_block_content():
    """Test that tampering with block content is detected."""
    vectors_path = Path(__file__).parent / "vectors" / "halo_sample_packet.json"
    
    with open(vectors_path, 'r', encoding='utf-8') as f:
        full_packet = json.load(f)
    
    # Extract fields from the flat packet structure
    halo = build_halo_chain(
        transaction_id=full_packet["transaction_id"],
        gateway_timestamp_utc=full_packet["gateway_timestamp_utc"],
        environment=full_packet["environment"],
        client_id=full_packet["client_id"],
        intent_manifest=full_packet["intent_manifest"],
        feature_tag=full_packet["feature_tag"],
        user_ref=full_packet["user_ref"],
        prompt_hash=full_packet["prompt_hash"],
        rag_hash=full_packet["rag_hash"],
        multimodal_hash=full_packet["multimodal_hash"],
        policy_version_hash=full_packet["policy_receipt"]["policy_version_hash"],
        policy_change_ref=full_packet["policy_receipt"]["policy_change_ref"],
        rules_applied=full_packet["policy_receipt"]["rules_applied"],
        model_fingerprint=full_packet["model_fingerprint"],
        param_snapshot=full_packet["param_snapshot"],
        execution=full_packet["execution"]
    )
    
    # Tamper with block 2 (intent)
    halo["blocks"][1]["feature_tag"] = "TAMPERED"
    
    result = verify_halo_chain(halo)
    
    assert result["valid"] is False
    assert len(result["discrepancies"]) > 0
    
    # Should detect mismatch in block 1's hash
    block_1_discrepancies = [d for d in result["discrepancies"] if d["block_index"] == 1]
    assert len(block_1_discrepancies) > 0


def test_halo_tampering_hash():
    """Test that tampering with a hash value is detected."""
    vectors_path = Path(__file__).parent / "vectors" / "halo_sample_packet.json"
    
    with open(vectors_path, 'r', encoding='utf-8') as f:
        full_packet = json.load(f)
    
    # Extract fields from the flat packet structure
    halo = build_halo_chain(
        transaction_id=full_packet["transaction_id"],
        gateway_timestamp_utc=full_packet["gateway_timestamp_utc"],
        environment=full_packet["environment"],
        client_id=full_packet["client_id"],
        intent_manifest=full_packet["intent_manifest"],
        feature_tag=full_packet["feature_tag"],
        user_ref=full_packet["user_ref"],
        prompt_hash=full_packet["prompt_hash"],
        rag_hash=full_packet["rag_hash"],
        multimodal_hash=full_packet["multimodal_hash"],
        policy_version_hash=full_packet["policy_receipt"]["policy_version_hash"],
        policy_change_ref=full_packet["policy_receipt"]["policy_change_ref"],
        rules_applied=full_packet["policy_receipt"]["rules_applied"],
        model_fingerprint=full_packet["model_fingerprint"],
        param_snapshot=full_packet["param_snapshot"],
        execution=full_packet["execution"]
    )
    
    # Tamper with a hash
    original_hash = halo["block_hashes"][2]
    halo["block_hashes"][2] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    
    result = verify_halo_chain(halo)
    
    assert result["valid"] is False
    assert len(result["discrepancies"]) > 0
    
    # Should detect hash mismatch for block 2
    block_2_discrepancies = [d for d in result["discrepancies"] 
                             if d["block_index"] == 2 and d["field"] == "block_hash"]
    assert len(block_2_discrepancies) > 0


def test_halo_tampering_prev_hash():
    """Test that tampering with prev_hash linkage is detected."""
    vectors_path = Path(__file__).parent / "vectors" / "halo_sample_packet.json"
    
    with open(vectors_path, 'r', encoding='utf-8') as f:
        full_packet = json.load(f)
    
    # Extract fields from the flat packet structure
    halo = build_halo_chain(
        transaction_id=full_packet["transaction_id"],
        gateway_timestamp_utc=full_packet["gateway_timestamp_utc"],
        environment=full_packet["environment"],
        client_id=full_packet["client_id"],
        intent_manifest=full_packet["intent_manifest"],
        feature_tag=full_packet["feature_tag"],
        user_ref=full_packet["user_ref"],
        prompt_hash=full_packet["prompt_hash"],
        rag_hash=full_packet["rag_hash"],
        multimodal_hash=full_packet["multimodal_hash"],
        policy_version_hash=full_packet["policy_receipt"]["policy_version_hash"],
        policy_change_ref=full_packet["policy_receipt"]["policy_change_ref"],
        rules_applied=full_packet["policy_receipt"]["rules_applied"],
        model_fingerprint=full_packet["model_fingerprint"],
        param_snapshot=full_packet["param_snapshot"],
        execution=full_packet["execution"]
    )
    
    # Tamper with prev_hash in block 3
    halo["blocks"][2]["prev_hash"] = "sha256:fake"
    
    result = verify_halo_chain(halo)
    
    assert result["valid"] is False
    assert len(result["discrepancies"]) > 0


def test_halo_chain_linkage():
    """Test that each block correctly links to previous."""
    vectors_path = Path(__file__).parent / "vectors" / "halo_sample_packet.json"
    
    with open(vectors_path, 'r', encoding='utf-8') as f:
        full_packet = json.load(f)
    
    # Extract fields from the flat packet structure
    halo = build_halo_chain(
        transaction_id=full_packet["transaction_id"],
        gateway_timestamp_utc=full_packet["gateway_timestamp_utc"],
        environment=full_packet["environment"],
        client_id=full_packet["client_id"],
        intent_manifest=full_packet["intent_manifest"],
        feature_tag=full_packet["feature_tag"],
        user_ref=full_packet["user_ref"],
        prompt_hash=full_packet["prompt_hash"],
        rag_hash=full_packet["rag_hash"],
        multimodal_hash=full_packet["multimodal_hash"],
        policy_version_hash=full_packet["policy_receipt"]["policy_version_hash"],
        policy_change_ref=full_packet["policy_receipt"]["policy_change_ref"],
        rules_applied=full_packet["policy_receipt"]["rules_applied"],
        model_fingerprint=full_packet["model_fingerprint"],
        param_snapshot=full_packet["param_snapshot"],
        execution=full_packet["execution"]
    )
    
    # Verify linkage: each block's prev_hash should match previous block's hash
    for i in range(1, 5):
        assert halo["blocks"][i]["prev_hash"] == halo["block_hashes"][i - 1]


def test_halo_denied_outcome():
    """Test HALO chain for denied transaction."""
    execution = {
        "outcome": "denied",
        "output_hash": None,
        "token_usage": None,
        "latency_ms": 50,
        "denial_reason": "Model not in approved list"
    }
    
    halo = build_halo_chain(
        transaction_id="tx-denied-001",
        gateway_timestamp_utc="2024-01-15T10:30:00.000Z",
        environment="production",
        client_id="client-alpha-01",
        intent_manifest="text-generation",
        feature_tag="customer-support",
        user_ref="user-12345",
        prompt_hash="sha256:abc123",
        rag_hash=None,
        multimodal_hash=None,
        policy_version_hash="sha256:policy123",
        policy_change_ref="change-001",
        rules_applied=["model-not-approved"],
        model_fingerprint="gpt-4-turbo",
        param_snapshot={"temperature": 0.7},
        execution=execution
    )
    
    assert halo["blocks"][4]["outcome"] == "denied"
    assert halo["blocks"][4]["denial_reason"] == "Model not in approved list"
    assert halo["blocks"][4]["output_hash"] is None
    
    result = verify_halo_chain(halo)
    assert result["valid"] is True
