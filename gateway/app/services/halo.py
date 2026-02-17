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

# Protocol version constants
HALO_VERSION = "v1"
C14N_VERSION = "json_c14n_v1"
SIGNING_ALG = "ECDSA_SHA_256"


def build_halo_chain(
    transaction_id: str,
    gateway_timestamp_utc: str,
    environment: str,
    client_id: str,
    intent_manifest: str,
    feature_tag: str,
    user_ref: str,
    prompt_hash: str,
    rag_hash: Optional[str],
    multimodal_hash: Optional[str],
    policy_version_hash: str,
    policy_change_ref: str,
    rules_applied: List[str],
    model_fingerprint: str,
    param_snapshot: Dict[str, Any],
    execution: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build a HALO v1 chain from explicit transaction parameters.
    
    Args:
        transaction_id: Unique transaction identifier
        gateway_timestamp_utc: ISO 8601 UTC timestamp
        environment: Environment name (production, staging, dev)
        client_id: Client identifier
        intent_manifest: Intent type (e.g., "text-generation")
        feature_tag: Feature tag (e.g., "customer-support")
        user_ref: User reference
        prompt_hash: SHA-256 hash of prompt content
        rag_hash: SHA-256 hash of RAG content (optional)
        multimodal_hash: SHA-256 hash of multimodal content (optional)
        policy_version_hash: SHA-256 hash of policy version
        policy_change_ref: Policy change reference ID
        rules_applied: List of policy rules that were applied
        model_fingerprint: Model identifier/fingerprint
        param_snapshot: Dictionary of model parameters
        execution: Dictionary with execution details:
            - outcome: "approved" or "denied"
            - output_hash: SHA-256 hash of output (optional)
            - token_usage: Token usage stats (optional)
            - latency_ms: Latency in milliseconds (optional)
            - denial_reason: Reason for denial (optional)
    
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
        "transaction_id": transaction_id,
        "gateway_timestamp_utc": gateway_timestamp_utc,
        "environment": environment,
        "client_id": client_id
    }
    blocks.append(block1)
    h1 = hash_c14n(block1)
    block_hashes.append(h1)
    
    # Block 2: Intent
    block2 = {
        "prev_hash": h1,
        "intent_manifest": intent_manifest,
        "feature_tag": feature_tag,
        "user_ref": user_ref
    }
    blocks.append(block2)
    h2 = hash_c14n(block2)
    block_hashes.append(h2)
    
    # Block 3: Inputs
    block3 = {
        "prev_hash": h2,
        "prompt_hash": prompt_hash,
        "rag_hash": rag_hash,
        "multimodal_hash": multimodal_hash
    }
    blocks.append(block3)
    h3 = hash_c14n(block3)
    block_hashes.append(h3)
    
    # Block 4: Policy + Model
    block4 = {
        "prev_hash": h3,
        "policy_version_hash": policy_version_hash,
        "policy_change_ref": policy_change_ref,
        "rules_applied": rules_applied,
        "model_fingerprint": model_fingerprint,
        "param_snapshot": param_snapshot
    }
    blocks.append(block4)
    h4 = hash_c14n(block4)
    block_hashes.append(h4)
    
    # Block 5: Output
    block5 = {
        "prev_hash": h4,
        "outcome": execution["outcome"],
        "output_hash": execution.get("output_hash"),
        "token_usage": execution.get("token_usage"),
        "latency_ms": execution.get("latency_ms"),
        "denial_reason": execution.get("denial_reason")
    }
    blocks.append(block5)
    h5 = hash_c14n(block5)
    block_hashes.append(h5)
    
    return {
        "halo_version": HALO_VERSION,
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
