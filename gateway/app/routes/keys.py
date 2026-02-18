"""
Key management endpoints for verifier bootstrap.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any

from gateway.app.services.storage import list_keys, get_key

router = APIRouter(prefix="/v1/keys", tags=["keys"])


@router.get("")
async def list_public_keys() -> List[Dict[str, Any]]:
    """
    List all available public keys.
    
    Returns list of keys with key_id, jwk, and status.
    """
    keys = list_keys()
    return keys


@router.get("/{key_id}")
async def get_public_key(key_id: str) -> Dict[str, Any]:
    """
    Get a specific public key by key_id.
    
    Returns JWK public key object only (not wrapped).
    """
    key = get_key(key_id)
    if not key:
        raise HTTPException(status_code=404, detail=f"Key not found: {key_id}")
    return key["jwk"]
