"""
Deterministic JSON canonicalization (c14n) module.

This module provides json_c14n_v1, which produces a canonical byte representation
of JSON-compatible Python objects. The canonicalization is deterministic and 
ensures that identical logical structures always produce identical byte sequences.

This function is load-bearing for the entire protocol - any drift in canonicalization
will break signature verification and HALO chain integrity.

Canonicalization Rules (v1):
1. UTF-8 encoding
2. No whitespace outside strings
3. Dictionary keys sorted lexicographically by Unicode codepoint
4. Array order preserved as-is
5. Strings emitted with JSON escaping
6. Numbers use minimal JSON representation (no NaN/Infinity)
7. Booleans as lowercase "true"/"false"
8. Null as "null"

Supported types: dict, list, str, int, float, bool, None
Unsupported types raise ValueError

Canonical Message Ordering for Certificates (Courtroom Defense Mode):
==================================================================
The canonical message for certificate signing MUST include ALL provenance fields
in alphabetical order (enforced by sort_keys=True):

Required Fields (ALL must be signed):
- certificate_id: UUID7 certificate identifier
- chain_hash: Integrity chain hash linking to previous certificate
- governance_policy_hash: Hash of the governance policy document  
- governance_policy_version: Version identifier of governance policy
- human_attested_at_utc: ISO 8601 timestamp when human attestation occurred (or null)
- human_reviewed: Boolean flag indicating human review status
- human_reviewer_id_hash: SHA-256 hash of reviewer ID (or null if not reviewed)
- issued_at_utc: ISO 8601 timestamp when certificate was issued
- key_id: Signing key identifier for key rotation support
- model_name: Name/identifier of AI model (e.g., "gpt-4", "claude-3")
- model_version: Version of AI model used
- note_hash: SHA-256 hash of clinical note content
- nonce: UUID7 nonce for replay protection (added by signer)
- prompt_version: Version identifier of prompt template
- server_timestamp: ISO 8601 server timestamp (added by signer for replay protection)
- tenant_id: Tenant/organization identifier

Non-Deterministic Fields (MUST be server-controlled):
- nonce: Generated server-side using UUID7
- server_timestamp: Generated server-side
- issued_at_utc: Server clock time (client cannot forge)

CRITICAL: Any change to this field list or ordering will break all existing signatures.
This is a cryptographic contract. Changes require a new canonicalization version.
"""

import json
import math
from typing import Any


def json_c14n_v1(obj: Any) -> bytes:
    """
    Produce deterministic canonical JSON bytes for an object.
    
    Args:
        obj: A JSON-compatible Python object (dict, list, str, int, float, bool, None)
        
    Returns:
        UTF-8 encoded canonical JSON bytes
        
    Raises:
        ValueError: If obj contains unsupported types or non-finite numbers
        
    Examples:
        >>> json_c14n_v1({"b": 2, "a": 1})
        b'{"a":1,"b":2}'
        
        >>> json_c14n_v1([1, 2, 3])
        b'[1,2,3]'
    """
    # First validate the object
    _validate_object(obj)
    
    # Use json.dumps with specific settings for determinism
    # - separators=(',', ':') ensures no whitespace
    # - ensure_ascii=False allows Unicode to pass through (then we encode to UTF-8)
    # - sort_keys=True ensures deterministic key ordering
    # - allow_nan=False rejects NaN/Infinity
    canonical_str = json.dumps(
        obj,
        separators=(',', ':'),
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False
    )
    
    return canonical_str.encode('utf-8')


def _validate_object(obj: Any) -> None:
    """
    Recursively validate that an object contains only supported types.
    
    Args:
        obj: Object to validate
        
    Raises:
        ValueError: If obj contains unsupported types or non-finite floats
    """
    if obj is None or isinstance(obj, bool):
        # bool must be checked before int since bool is a subclass of int
        return
    elif isinstance(obj, (int, str)):
        return
    elif isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError(f"Non-finite float not allowed: {obj}")
        return
    elif isinstance(obj, dict):
        for key, value in obj.items():
            if not isinstance(key, str):
                raise ValueError(f"Dictionary keys must be strings, got {type(key).__name__}")
            _validate_object(value)
    elif isinstance(obj, list):
        for item in obj:
            _validate_object(item)
    else:
        raise ValueError(f"Unsupported type: {type(obj).__name__}")
