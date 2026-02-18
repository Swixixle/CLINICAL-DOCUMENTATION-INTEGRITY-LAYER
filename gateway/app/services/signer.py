"""
Cryptographic signing and verification for CDIL.

This module provides signing capabilities for certificates and accountability packets.
Uses per-tenant keys with nonce-based replay protection.

Security Updates (Hardening):
- Per-tenant key isolation (no shared keys across tenants)
- Nonce-based replay protection
- Server-controlled timestamps (client cannot forge)
- Key rotation support via key_id tracking

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
from gateway.app.services.key_registry import get_key_registry
from gateway.app.db.migrate import get_connection


def _load_private_key():
    """
    Load the dev private key (fallback for legacy operations).
    
    DEPRECATED: Use per-tenant keys from key_registry instead.
    """
    key_path = Path(__file__).parent.parent / "dev_keys" / "dev_private.pem"
    
    with open(key_path, 'rb') as f:
        private_key = serialization.load_pem_private_key(
            f.read(),
            password=None
        )
    
    return private_key


def _load_public_jwk():
    """
    Load the dev public key JWK (fallback for legacy operations).
    
    DEPRECATED: Use per-tenant keys from key_registry instead.
    """
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


def check_and_record_nonce(tenant_id: str, nonce: str) -> bool:
    """
    Check if nonce has been used and record it if not.
    
    This prevents replay attacks by ensuring each nonce is used only once per tenant.
    
    Args:
        tenant_id: Tenant identifier
        nonce: Nonce string (should be UUID4)
        
    Returns:
        True if nonce is new (recorded successfully), False if already used
    """
    conn = get_connection()
    try:
        # Check if nonce exists
        cursor = conn.execute("""
            SELECT 1 FROM used_nonces
            WHERE tenant_id = ? AND nonce = ?
        """, (tenant_id, nonce))
        
        if cursor.fetchone():
            return False  # Nonce already used (replay attack!)
        
        # Record the nonce
        used_at_utc = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        conn.execute("""
            INSERT INTO used_nonces (tenant_id, nonce, used_at_utc)
            VALUES (?, ?, ?)
        """, (tenant_id, nonce, used_at_utc))
        conn.commit()
        
        return True
        
    finally:
        conn.close()


def sign_message(message_obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sign a message object using the dev private key (legacy format).
    
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


def sign_generic_message(
    message_obj: Dict[str, Any],
    tenant_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Sign an arbitrary message object using per-tenant keys.
    
    This is the primary signing function for certificates and should be used
    for all new code. It includes:
    - Per-tenant key isolation
    - Nonce for replay protection (if tenant_id provided)
    - Server timestamp
    - Key rotation support
    
    Args:
        message_obj: Dictionary to sign (will be canonicalized)
        tenant_id: Tenant ID for per-tenant signing (optional, uses dev key if None)
        
    Returns:
        Dictionary containing:
            - algorithm: Algorithm identifier
            - key_id: Key identifier
            - canonical_message: Original message object (with nonce/timestamp if tenant_id)
            - signature: Base64-encoded signature
    """
    # If no tenant_id, use legacy dev key
    if not tenant_id:
        # Legacy path for backward compatibility
        canonical_bytes = json_c14n_v1(message_obj)
        private_key = _load_private_key()
        signature = private_key.sign(
            canonical_bytes,
            ec.ECDSA(hashes.SHA256())
        )
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        return {
            "algorithm": "ECDSA_SHA_256",
            "key_id": "dev-key-01",
            "canonical_message": message_obj,
            "signature": signature_b64
        }
    
    # Get tenant's active key
    registry = get_key_registry()
    key_data = registry.get_active_key(tenant_id)
    
    if not key_data:
        # Generate key for tenant if none exists
        key_id = registry.ensure_tenant_has_key(tenant_id)
        key_data = registry.get_active_key(tenant_id)
    
    # Add nonce and timestamp for replay protection
    from gateway.app.services.uuid7 import generate_uuid7
    enhanced_message = {
        **message_obj,
        "nonce": generate_uuid7(),
        "server_timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    }
    
    # Canonicalize the enhanced message
    canonical_bytes = json_c14n_v1(enhanced_message)
    
    # Sign with tenant's key
    private_key = key_data['private_key']
    signature = private_key.sign(
        canonical_bytes,
        ec.ECDSA(hashes.SHA256())
    )
    
    # Encode signature as base64
    signature_b64 = base64.b64encode(signature).decode('utf-8')
    
    # Record nonce to prevent replay
    nonce = enhanced_message["nonce"]
    if not check_and_record_nonce(tenant_id, nonce):
        raise ValueError(f"Nonce already used: {nonce} (replay attack detected)")
    
    return {
        "algorithm": "ECDSA_SHA_256",
        "key_id": key_data['key_id'],
        "canonical_message": enhanced_message,
        "signature": signature_b64
    }


def verify_signature(bundle: Dict[str, Any], jwk: Dict[str, str]) -> bool:
    """
    Verify a signature bundle using a JWK public key.
    
    Supports both legacy format (message/signature_b64) and new format (canonical_message/signature).
    
    Args:
        bundle: Signature bundle from sign_message() or sign_generic_message()
        jwk: JWK public key dictionary
        
    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Extract components - support both formats
        message_obj = bundle.get("message") or bundle.get("canonical_message")
        signature_b64 = bundle.get("signature_b64") or bundle.get("signature")
        
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


# Type hint fix
from typing import Optional
