"""
Cryptographic signing and verification for ELI Sentinel.

This module provides signing capabilities for accountability packets.
In development, it uses local keys. In production, it can be extended
to use AWS KMS, GCP KMS, Azure Key Vault, or HSMs.

Signature Format:
- Algorithm: ECDSA with SHA-256 (P-256 curve)
- Message: SHA-256 hash of canonical JSON
- Encoding: Base64 of DER-encoded signature
"""

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature

from gateway.app.services.c14n import json_c14n_v1
from gateway.app.services.hashing import sha256_hex


def _load_private_key():
    """Load the dev private key."""
    key_path = Path(__file__).parent.parent / "dev_keys" / "dev_private.pem"
    
    with open(key_path, 'rb') as f:
        private_key = serialization.load_pem_private_key(
            f.read(),
            password=None
        )
    
    return private_key


def _load_public_jwk():
    """Load the dev public key JWK."""
    jwk_path = Path(__file__).parent.parent / "dev_keys" / "dev_public.jwk.json"
    
    with open(jwk_path, 'r') as f:
        return json.load(f)


def _jwk_to_public_key(jwk: Dict[str, str]):
    """Convert JWK to cryptography public key object."""
    if jwk['kty'] != 'EC' or jwk['crv'] != 'P-256':
        raise ValueError("Only EC P-256 keys are supported")
    
    # Decode base64url coordinates
    def base64url_decode(s):
        # Add padding if needed
        padding = 4 - (len(s) % 4)
        if padding != 4:
            s = s + ('=' * padding)
        return base64.urlsafe_b64decode(s)
    
    x_bytes = base64url_decode(jwk['x'])
    y_bytes = base64url_decode(jwk['y'])
    
    x = int.from_bytes(x_bytes, byteorder='big')
    y = int.from_bytes(y_bytes, byteorder='big')
    
    # Reconstruct public key
    public_numbers = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1())
    return public_numbers.public_key()


def sign_message(message_obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sign a message object using the dev private key.
    
    The canonical message contract is locked to exactly 4 fields:
    - transaction_id
    - gateway_timestamp_utc
    - final_hash
    - policy_version_hash
    
    Args:
        message_obj: Dictionary to sign (will be canonicalized)
                     Must contain exactly the 4 canonical fields above
        
    Returns:
        Dictionary containing:
            - alg: Algorithm identifier
            - key_id: Key identifier
            - message: Original message object
            - signature_b64: Base64-encoded signature
            - signed_at_utc: ISO 8601 timestamp
    """
    # Validate that message contains exactly the canonical fields
    canonical_fields = {"transaction_id", "gateway_timestamp_utc", "final_hash", "policy_version_hash"}
    message_fields = set(message_obj.keys())
    
    if message_fields != canonical_fields:
        raise ValueError(
            f"Message must contain exactly these fields: {canonical_fields}. "
            f"Got: {message_fields}"
        )
    
    # Canonicalize the message
    canonical_bytes = json_c14n_v1(message_obj)
    
    # Load private key
    private_key = _load_private_key()
    
    # Sign the canonical bytes
    signature = private_key.sign(
        canonical_bytes,
        ec.ECDSA(hashes.SHA256())
    )
    
    # Encode signature as base64
    signature_b64 = base64.b64encode(signature).decode('utf-8')
    
    # Get current UTC timestamp
    signed_at_utc = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    return {
        "alg": "ECDSA_SHA_256",
        "key_id": "dev-key-01",
        "message": message_obj,
        "signature_b64": signature_b64,
        "signed_at_utc": signed_at_utc
    }


def verify_signature(bundle: Dict[str, Any], jwk: Dict[str, str]) -> bool:
    """
    Verify a signature bundle using a JWK public key.
    
    Args:
        bundle: Signature bundle from sign_message()
        jwk: JWK public key dictionary
        
    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Extract components
        message_obj = bundle.get("message")
        signature_b64 = bundle.get("signature_b64")
        
        if not message_obj or not signature_b64:
            return False
        
        # Canonicalize the message (must match signing)
        canonical_bytes = json_c14n_v1(message_obj)
        
        # Decode signature
        signature = base64.b64decode(signature_b64)
        
        # Convert JWK to public key
        public_key = _jwk_to_public_key(jwk)
        
        # Verify signature
        public_key.verify(
            signature,
            canonical_bytes,
            ec.ECDSA(hashes.SHA256())
        )
        
        return True
        
    except (InvalidSignature, ValueError, KeyError):
        return False
