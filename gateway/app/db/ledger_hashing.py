"""
Single-source canonical hashing module for the Part 11 audit ledger.

All hash computation for audit events MUST go through this module.
The writer (part11_operations.py) and the verifier
(tools/verify_ledger_integrity.py) both import from here to prevent
canonicalization drift.

Hash canonicalization (stable, locale-independent, deterministic):
    hash_input = f"{prev_hash or ''}{timestamp}{obj_type}{obj_id}{action}{payload_json}"
    event_hash = SHA-256(hash_input.encode("utf-8")).hexdigest()

Ordering used by verifier:
    ORDER BY occurred_at_utc ASC, event_id ASC
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
    writer and the integrity verifier. Do NOT duplicate this logic elsewhere.
    """
    hash_input = (
        f"{prev_hash or ''}{timestamp}{object_type}{object_id}{action}{payload_json}"
    )
    return hash_content(hash_input)
