"""
Transaction retrieval and verification endpoints.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from gateway.app.services.storage import get_transaction
from gateway.app.services.halo import verify_halo_chain
from gateway.app.services.signer import verify_signature

router = APIRouter(prefix="/v1/transactions", tags=["transactions"])


@router.get("/{transaction_id}")
async def get_transaction_by_id(transaction_id: str) -> Dict[str, Any]:
    """
    Retrieve a transaction by its ID.
    
    Returns the complete accountability packet.
    """
    packet = get_transaction(transaction_id)
    if not packet:
        raise HTTPException(status_code=404, detail=f"Transaction not found: {transaction_id}")
    return packet


@router.post("/{transaction_id}/verify")
async def verify_transaction(transaction_id: str) -> Dict[str, Any]:
    """
    Verify the cryptographic integrity of a transaction.
    
    Recomputes HALO chain from packet fields using explicit builder,
    compares to stored HALO, and verifies signature.
    Returns structured validation results with failures list.
    """
    from gateway.app.services.halo import build_halo_chain
    from gateway.app.services.storage import get_key
    
    # Load packet
    packet = get_transaction(transaction_id)
    if not packet:
        raise HTTPException(status_code=404, detail=f"Transaction not found: {transaction_id}")
    
    failures = []
    
    # Recompute HALO chain from packet fields
    try:
        recomputed_halo = build_halo_chain(
            transaction_id=packet["transaction_id"],
            gateway_timestamp_utc=packet["gateway_timestamp_utc"],
            environment=packet["environment"],
            client_id=packet["client_id"],
            intent_manifest=packet["intent_manifest"],
            feature_tag=packet["feature_tag"],
            user_ref=packet["user_ref"],
            prompt_hash=packet["prompt_hash"],
            rag_hash=packet.get("rag_hash"),
            multimodal_hash=packet.get("multimodal_hash"),
            policy_version_hash=packet["policy_receipt"]["policy_version_hash"],
            policy_change_ref=packet["policy_receipt"]["policy_change_ref"],
            rules_applied=packet["policy_receipt"]["rules_applied"],
            model_fingerprint=packet["model_fingerprint"],
            param_snapshot=packet["param_snapshot"],
            execution=packet["execution"]
        )
        
        # Compare recomputed HALO final hash to stored HALO final hash
        stored_final_hash = packet.get("halo_chain", {}).get("final_hash")
        recomputed_final_hash = recomputed_halo.get("final_hash")
        
        if stored_final_hash != recomputed_final_hash:
            # Hash leakage policy: return error code + prefixes only (first 16 chars)
            stored_prefix = stored_final_hash[:16] if stored_final_hash else "none"
            recomputed_prefix = recomputed_final_hash[:16] if recomputed_final_hash else "none"
            failures.append({
                "check": "halo_chain",
                "error": "final_hash_mismatch",
                "debug": {
                    "stored_prefix": stored_prefix,
                    "recomputed_prefix": recomputed_prefix
                }
            })
    except Exception as e:
        failures.append({
            "check": "halo_chain",
            "error": "recomputation_failed",
            "debug": {"message": str(e)[:100]}
        })
    
    # Verify signature using key from packet's verification.key_id
    signature_bundle = packet.get("verification", {})
    key_id = signature_bundle.get("key_id")
    
    if not key_id:
        failures.append({
            "check": "signature",
            "error": "missing_key_id"
        })
    else:
        # Look up key in database
        key = get_key(key_id)
        
        if not key:
            # Fallback to dev JWK only if environment is not prod
            if packet.get("environment") != "prod":
                from pathlib import Path
                import json
                jwk_path = Path(__file__).parent.parent / "dev_keys" / "dev_public.jwk.json"
                try:
                    with open(jwk_path, 'r') as f:
                        jwk = json.load(f)
                except:
                    failures.append({
                        "check": "signature",
                        "error": "key_not_found_and_fallback_failed"
                    })
                    jwk = None
            else:
                failures.append({
                    "check": "signature",
                    "error": "key_not_found_in_prod"
                })
                jwk = None
        else:
            jwk = key.get("jwk")
        
        if jwk:
            try:
                signature_valid = verify_signature(signature_bundle, jwk)
                if not signature_valid:
                    failures.append({
                        "check": "signature",
                        "error": "invalid_signature"
                    })
            except Exception as e:
                failures.append({
                    "check": "signature",
                    "error": "verification_failed",
                    "debug": {"message": str(e)[:100]}
                })
    
    valid = len(failures) == 0
    
    # Return structured result with both new failures list and legacy checks
    result = {
        "valid": valid,
        "failures": failures
    }
    
    # Add legacy checks field for backward compatibility
    if not failures:
        result["checks"] = {
            "halo_chain": "valid",
            "signature": "valid",
            "key": "found"
        }
    else:
        result["checks"] = {}
        for failure in failures:
            if failure["check"] == "halo_chain":
                result["checks"]["halo_chain"] = "invalid"
            elif failure["check"] == "signature":
                result["checks"]["signature"] = "invalid"
    
    return result
