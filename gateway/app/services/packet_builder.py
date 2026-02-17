"""
Accountability Packet Builder.

This module constructs the final Accountability Packet using explicit
structured inputs and integrates HALO chain building and cryptographic signing.

The packet format is protocol-locked and must not drift from the canonical
specification.
"""

from typing import Any, Dict, List, Optional

from gateway.app.services.halo import build_halo_chain, HALO_VERSION, C14N_VERSION, SIGNING_ALG
from gateway.app.services.signer import sign_message


def build_accountability_packet(
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
    Build a complete Accountability Packet.
    
    This function assembles the canonical packet format with:
    - All top-level fields (no packet_inputs wrapper)
    - HALO chain
    - Cryptographic signature
    - Protocol version metadata
    
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
        Complete accountability packet dictionary with:
        - All transaction fields at top level
        - policy_receipt with policy details
        - execution with outcome details
        - halo_chain with tamper-evident chain
        - verification with cryptographic signature
        - protocol_metadata with version pins
    """
    # Build HALO chain
    halo_chain = build_halo_chain(
        transaction_id=transaction_id,
        gateway_timestamp_utc=gateway_timestamp_utc,
        environment=environment,
        client_id=client_id,
        intent_manifest=intent_manifest,
        feature_tag=feature_tag,
        user_ref=user_ref,
        prompt_hash=prompt_hash,
        rag_hash=rag_hash,
        multimodal_hash=multimodal_hash,
        policy_version_hash=policy_version_hash,
        policy_change_ref=policy_change_ref,
        rules_applied=rules_applied,
        model_fingerprint=model_fingerprint,
        param_snapshot=param_snapshot,
        execution=execution
    )
    
    # Build canonical message for signing (exactly 4 fields)
    canonical_message = {
        "transaction_id": transaction_id,
        "gateway_timestamp_utc": gateway_timestamp_utc,
        "final_hash": halo_chain["final_hash"],
        "policy_version_hash": policy_version_hash
    }
    
    # Sign the message
    signature_bundle = sign_message(canonical_message)
    
    # Assemble the complete packet (flat structure, no packet_inputs wrapper)
    packet = {
        # Core identifiers
        "transaction_id": transaction_id,
        "client_id": client_id,
        "environment": environment,
        "gateway_timestamp_utc": gateway_timestamp_utc,
        
        # Intent
        "intent_manifest": intent_manifest,
        "feature_tag": feature_tag,
        "user_ref": user_ref,
        
        # Model
        "model_fingerprint": model_fingerprint,
        "param_snapshot": param_snapshot,
        
        # Content hashes
        "prompt_hash": prompt_hash,
        "rag_hash": rag_hash,
        "multimodal_hash": multimodal_hash,
        
        # Policy receipt
        "policy_receipt": {
            "policy_version_hash": policy_version_hash,
            "policy_change_ref": policy_change_ref,
            "rules_applied": rules_applied
        },
        
        # Execution result
        "execution": execution,
        
        # HALO chain
        "halo_chain": halo_chain,
        
        # Verification bundle
        "verification": signature_bundle,
        
        # Protocol metadata (version pins)
        "protocol_metadata": {
            "halo_version": HALO_VERSION,
            "c14n_version": C14N_VERSION,
            "signing_alg": SIGNING_ALG
        }
    }
    
    return packet
