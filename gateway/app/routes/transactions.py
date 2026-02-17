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
    
    Recomputes HALO chain and verifies signature.
    Returns validation results.
    """
    # Load packet
    packet = get_transaction(transaction_id)
    if not packet:
        raise HTTPException(status_code=404, detail=f"Transaction not found: {transaction_id}")
    
    # Verify HALO chain
    halo_verification = verify_halo_chain(packet.get("halo_chain", {}))
    halo_valid = halo_verification.get("valid", False)
    
    # Verify signature
    signature_bundle = packet.get("verification", {})
    key_id = signature_bundle.get("key_id")
    
    signature_valid = False
    key_found = False
    
    if key_id:
        # Load the public key JWK
        from gateway.app.services.storage import get_key
        key = get_key(key_id)
        
        if key:
            key_found = True
            jwk = key.get("jwk")
            if jwk:
                signature_valid = verify_signature(signature_bundle, jwk)
    
    overall_valid = halo_valid and signature_valid and key_found
    
    return {
        "valid": overall_valid,
        "checks": {
            "halo_chain": "valid" if halo_valid else "invalid",
            "signature": "valid" if signature_valid else "invalid",
            "key": "found" if key_found else "missing"
        }
    }
