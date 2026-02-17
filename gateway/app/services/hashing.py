"""
Hashing utilities for the ELI Sentinel protocol.

Provides standardized hashing functions used throughout the system for
creating tamper-evident identifiers and content hashes.
"""

import hashlib
from typing import Any

from gateway.app.services.c14n import json_c14n_v1


def sha256_hex(data: bytes) -> str:
    """
    Compute SHA-256 hash and return as lowercase hexadecimal string.
    
    Args:
        data: Raw bytes to hash
        
    Returns:
        Lowercase hexadecimal SHA-256 hash (64 characters)
        
    Example:
        >>> sha256_hex(b"hello")
        '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
    """
    return hashlib.sha256(data).hexdigest()


def sha256_prefixed(data: bytes) -> str:
    """
    Compute SHA-256 hash with 'sha256:' prefix.
    
    This format is used throughout the protocol to make hash algorithm
    explicit in all identifiers.
    
    Args:
        data: Raw bytes to hash
        
    Returns:
        Prefixed hash string like 'sha256:abc123...'
        
    Example:
        >>> sha256_prefixed(b"hello")
        'sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
    """
    return f"sha256:{sha256_hex(data)}"


def hash_c14n(obj: Any) -> str:
    """
    Hash a JSON-compatible object using canonical representation.
    
    This is the primary function for creating content hashes in the protocol.
    It combines deterministic canonicalization with SHA-256 hashing.
    
    Args:
        obj: JSON-compatible Python object
        
    Returns:
        Prefixed hash of canonical representation
        
    Example:
        >>> hash_c14n({"b": 2, "a": 1})
        'sha256:...'
    """
    canonical_bytes = json_c14n_v1(obj)
    return sha256_prefixed(canonical_bytes)
