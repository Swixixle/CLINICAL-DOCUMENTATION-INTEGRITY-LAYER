"""
HALO Chain (Hash-Linked Accountability Ledger) implementation.

The HALO chain is a deterministic five-block hash chain that provides
tamper-evident accountability for AI transactions. Each block includes
the hash of the previous block, making any modification detectable.

Block Structure:
1. Genesis: transaction metadata and environment
2. Intent: what the user intended to do
3. Inputs: content hashes (prompt, RAG, multimodal)
4. Policy + Model: governance snapshot
5. Output: execution result or denial

Any modification to any block breaks the chain verification.
"""

from typing import Any, Dict, List, Optional

from gateway.app.services.hashing import hash_c14n


def build_halo_chain(packet_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a HALO v1 chain from transaction inputs.
    
    Args:
        packet_inputs: Dictionary containing all required fields for the 5 blocks:
            - transaction_id
            - gateway_timestamp_utc
            - environment
            - client_id
            - intent_manifest
            - feature_tag
            - user_ref
            - prompt_hash
            - rag_hash (optional)
            - multimodal_hash (optional)
            - policy_version_hash
            - policy_change_ref
            - rules_applied
            - model_fingerprint
            - param_snapshot
            - outcome ("approved" or "denied")
            - output_hash (optional, null if denied)
            - token_usage (optional)
            - latency_ms (optional)
            - denial_reason (optional)
    
    Returns:
        Dictionary with:
            - halo_version: "v1"
            - blocks: List of 5 blocks
            - block_hashes: List of 5 hashes
            - final_hash: The hash of block 5
    """
    blocks = []
    block_hashes = []
    
    # Block 1: Genesis
    block1 = {
        "transaction_id": packet_inputs["transaction_id"],
        "gateway_timestamp_utc": packet_inputs["gateway_timestamp_utc"],
        "environment": packet_inputs["environment"],
        "client_id": packet_inputs["client_id"]
    }
    blocks.append(block1)
    h1 = hash_c14n(block1)
    block_hashes.append(h1)
    
    # Block 2: Intent
    block2 = {
        "prev_hash": h1,
        "intent_manifest": packet_inputs["intent_manifest"],
        "feature_tag": packet_inputs["feature_tag"],
        "user_ref": packet_inputs["user_ref"]
    }
    blocks.append(block2)
    h2 = hash_c14n(block2)
    block_hashes.append(h2)
    
    # Block 3: Inputs
    block3 = {
        "prev_hash": h2,
        "prompt_hash": packet_inputs["prompt_hash"],
        "rag_hash": packet_inputs.get("rag_hash"),
        "multimodal_hash": packet_inputs.get("multimodal_hash")
    }
    blocks.append(block3)
    h3 = hash_c14n(block3)
    block_hashes.append(h3)
    
    # Block 4: Policy + Model
    block4 = {
        "prev_hash": h3,
        "policy_version_hash": packet_inputs["policy_version_hash"],
        "policy_change_ref": packet_inputs["policy_change_ref"],
        "rules_applied": packet_inputs["rules_applied"],
        "model_fingerprint": packet_inputs["model_fingerprint"],
        "param_snapshot": packet_inputs["param_snapshot"]
    }
    blocks.append(block4)
    h4 = hash_c14n(block4)
    block_hashes.append(h4)
    
    # Block 5: Output
    block5 = {
        "prev_hash": h4,
        "outcome": packet_inputs["outcome"],
        "output_hash": packet_inputs.get("output_hash"),
        "token_usage": packet_inputs.get("token_usage"),
        "latency_ms": packet_inputs.get("latency_ms"),
        "denial_reason": packet_inputs.get("denial_reason")
    }
    blocks.append(block5)
    h5 = hash_c14n(block5)
    block_hashes.append(h5)
    
    return {
        "halo_version": "v1",
        "blocks": blocks,
        "block_hashes": block_hashes,
        "final_hash": h5
    }


def verify_halo_chain(halo: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify the integrity of a HALO chain.
    
    Args:
        halo: HALO chain dictionary with blocks and block_hashes
        
    Returns:
        Dictionary with:
            - valid: bool indicating if chain is valid
            - discrepancies: list of issues found (empty if valid)
                Each discrepancy includes:
                    - block_index: int
                    - field: str
                    - expected: str
                    - actual: str
    """
    discrepancies = []
    
    # Check version
    if halo.get("halo_version") != "v1":
        discrepancies.append({
            "block_index": -1,
            "field": "halo_version",
            "expected": "v1",
            "actual": halo.get("halo_version")
        })
    
    blocks = halo.get("blocks", [])
    claimed_hashes = halo.get("block_hashes", [])
    
    # Check we have 5 blocks
    if len(blocks) != 5:
        discrepancies.append({
            "block_index": -1,
            "field": "block_count",
            "expected": "5",
            "actual": str(len(blocks))
        })
        return {"valid": False, "discrepancies": discrepancies}
    
    if len(claimed_hashes) != 5:
        discrepancies.append({
            "block_index": -1,
            "field": "hash_count",
            "expected": "5",
            "actual": str(len(claimed_hashes))
        })
        return {"valid": False, "discrepancies": discrepancies}
    
    # Recompute all hashes and verify chain
    computed_hashes = []
    
    for i, block in enumerate(blocks):
        computed_hash = hash_c14n(block)
        computed_hashes.append(computed_hash)
        
        # Check if hash matches claimed hash
        if computed_hash != claimed_hashes[i]:
            discrepancies.append({
                "block_index": i,
                "field": "block_hash",
                "expected": claimed_hashes[i],
                "actual": computed_hash
            })
        
        # Check prev_hash linkage (blocks 1-4 should reference previous hash)
        if i > 0:
            expected_prev = computed_hashes[i - 1]
            actual_prev = block.get("prev_hash")
            
            if actual_prev != expected_prev:
                discrepancies.append({
                    "block_index": i,
                    "field": "prev_hash",
                    "expected": expected_prev,
                    "actual": actual_prev
                })
    
    # Check final_hash
    if halo.get("final_hash") != computed_hashes[-1]:
        discrepancies.append({
            "block_index": -1,
            "field": "final_hash",
            "expected": computed_hashes[-1],
            "actual": halo.get("final_hash")
        })
    
    return {
        "valid": len(discrepancies) == 0,
        "discrepancies": discrepancies
    }
