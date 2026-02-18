"""
Verification utility functions.

Provides helpers for consistent failure reporting in verification endpoints.
"""

from typing import Dict, Any, Optional


def fail(check: str, error: str, debug: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Create a standardized failure entry for verification results.
    
    Enforces consistent schema across all verification failure paths:
    - Always includes 'check' and 'error' fields
    - Optionally includes 'debug' field with structured data
    - Prevents accidental schema drift (e.g., using 'message' instead of 'error')
    
    Args:
        check: The verification check that failed (e.g., "halo_chain", "signature")
        error: The error code (e.g., "final_hash_mismatch", "invalid_signature")
        debug: Optional debug information (must follow prefix-only policy)
    
    Returns:
        Standardized failure dictionary
    
    Examples:
        >>> fail("halo_chain", "final_hash_mismatch", {"stored_prefix": "abc", "recomputed_prefix": "def"})
        {'check': 'halo_chain', 'error': 'final_hash_mismatch', 'debug': {'stored_prefix': 'abc', 'recomputed_prefix': 'def'}}
        
        >>> fail("signature", "key_not_found")
        {'check': 'signature', 'error': 'key_not_found'}
    """
    out = {"check": check, "error": error}
    if debug:
        out["debug"] = debug
    return out
