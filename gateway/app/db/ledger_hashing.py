"""
Single-source canonical hashing module for the Part 11 audit ledger.

All hash computation for audit events MUST go through this module.
The writer (part11_operations.py) and the verifier
(tools/verify_ledger_integrity.py) both import from here to prevent
canonicalization drift.

Hash policy
-----------
  input  = (prev_event_hash or '') + occurred_at_utc + object_type
          + object_id + action + event_payload_json
  digest = SHA-256(input.encode("utf-8")).hexdigest()

Ordering used by verifier
--------------------------
  ORDER BY occurred_at_utc ASC, event_id ASC
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

# Constants exported so callers can embed them verbatim in JSON output.
HASH_POLICY = (
    "SHA-256(prev_event_hash||occurred_at_utc||object_type"
    "||object_id||action||event_payload_json)"
)
ORDERING = "occurred_at_utc ASC, event_id ASC"


def hash_content(content: str) -> str:
    """Hash a UTF-8 string with SHA-256 and return the hex digest."""

def hash_content(content: str) -> str:
    """Hash arbitrary content using SHA-256."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_event_hash(
    prev_event_hash: Optional[str],
    occurred_at_utc: str,
    object_type: str,
    object_id: str,
    action: str,
    event_payload_json: str,
) -> str:
    """
    Compute the canonical hash for one audit event.

    This is the SINGLE authoritative implementation used by both the
    database writer and the integrity verifier.  Do NOT duplicate this
    logic elsewhere.
    """
    hash_input = (
        f"{prev_event_hash or ''}"
        f"{occurred_at_utc}"
        f"{object_type}"
        f"{object_id}"
        f"{action}"
        f"{event_payload_json}"
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
