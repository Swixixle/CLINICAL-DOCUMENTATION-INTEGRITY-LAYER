"""Canonical ledger hash functions for FDA 21 CFR Part 11 audit event chaining.

This is the single authoritative source for audit event hash computation.
Both the ledger writer (part11_operations.py) and the standalone verifier
(tools/verify_ledger_integrity.py) import from this module so that hash
canonicalization cannot silently diverge between writer and verifier.

Hash canonicalization (stable, locale-independent, deterministic):
    hash_input = f"{prev_hash or ''}{timestamp}{obj_type}{obj_id}{action}{payload_json}"
    event_hash = SHA-256(hash_input.encode("utf-8")).hexdigest()
"""

import hashlib
from typing import Optional


def hash_content(content: str) -> str:
    """Hash arbitrary content using SHA-256."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_event_hash(
    prev_hash: Optional[str],
    timestamp: str,
    object_type: str,
    object_id: str,
    action: str,
    payload_json: str,
) -> str:
    """Compute the canonical hash for an audit event.

    This is the single canonical implementation used by both the ledger
    writer and the integrity verifier.  Changing this function changes what
    hashes are considered valid — coordinate any modification with a ledger
    migration plan.
    """
    hash_input = (
        f"{prev_hash or ''}{timestamp}{object_type}{object_id}{action}{payload_json}"
    )
    return hash_content(hash_input)
