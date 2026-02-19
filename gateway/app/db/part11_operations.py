"""
Part 11 Database Operations.

This module provides database operations for the Part 11 compliant schema,
including CRUD operations, audit event logging, and defense bundle creation.
"""

import sqlite3
import hashlib
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from gateway.app.db.ledger_hashing import (
    hash_content,
    compute_event_hash,
)


def get_utc_timestamp() -> str:
    """Get current UTC timestamp in ISO 8601 format."""
    from datetime import timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def generate_ulid() -> str:
    """Generate a ULID-like identifier (simplified version)."""
    import uuid

    # For MVP, use UUID v7 style (time-ordered UUID)
    # In production, use proper ULID library
    return str(uuid.uuid4())


def hash_with_salt(content: str, salt: str) -> str:
    """Hash content with salt using SHA-256."""
    return hashlib.sha256((content + salt).encode("utf-8")).hexdigest()


# ============================================================================
# TENANT OPERATIONS
# ============================================================================


def create_tenant(
    conn: sqlite3.Connection,
    name: str,
    kms_key_ref: Optional[str] = None,
    retention_policy: Optional[Dict[str, Any]] = None,
) -> str:
    """Create a new tenant."""
    tenant_id = generate_ulid()
    timestamp = get_utc_timestamp()
    retention_json = json.dumps(retention_policy) if retention_policy else None

    conn.execute(
        """
        INSERT INTO tenants (
            tenant_id, name, kms_key_ref, retention_policy_json,
            created_at_utc, updated_at_utc, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (tenant_id, name, kms_key_ref, retention_json, timestamp, timestamp, "active"),
    )
    conn.commit()
    return tenant_id


def get_tenant(conn: sqlite3.Connection, tenant_id: str) -> Optional[Dict[str, Any]]:
    """Get tenant by ID."""
    cursor = conn.execute("SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


# ============================================================================
# ENCOUNTER OPERATIONS
# ============================================================================


def create_encounter(
    conn: sqlite3.Connection,
    tenant_id: str,
    patient_id: str,
    encounter_time_start: str,
    encounter_time_end: Optional[str] = None,
    source_system: Optional[str] = None,
) -> str:
    """Create a new encounter with hashed patient reference."""
    encounter_id = generate_ulid()
    timestamp = get_utc_timestamp()

    # Hash patient ID with tenant as salt for privacy
    patient_ref_hash = hash_with_salt(patient_id, tenant_id)

    conn.execute(
        """
        INSERT INTO encounters (
            encounter_id, tenant_id, patient_ref_hash,
            encounter_time_start, encounter_time_end, source_system,
            created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            encounter_id,
            tenant_id,
            patient_ref_hash,
            encounter_time_start,
            encounter_time_end,
            source_system,
            timestamp,
        ),
    )
    conn.commit()
    return encounter_id


def get_encounter(
    conn: sqlite3.Connection, encounter_id: str
) -> Optional[Dict[str, Any]]:
    """Get encounter by ID."""
    cursor = conn.execute(
        "SELECT * FROM encounters WHERE encounter_id = ?", (encounter_id,)
    )
    row = cursor.fetchone()
    return dict(row) if row else None


# ============================================================================
# NOTE OPERATIONS
# ============================================================================


def create_note(
    conn: sqlite3.Connection,
    tenant_id: str,
    encounter_id: str,
    note_type: str,
) -> str:
    """Create a new note."""
    note_id = generate_ulid()
    timestamp = get_utc_timestamp()

    conn.execute(
        """
        INSERT INTO notes (
            note_id, tenant_id, encounter_id, note_type,
            status, created_at_utc, updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (note_id, tenant_id, encounter_id, note_type, "draft", timestamp, timestamp),
    )
    conn.commit()
    return note_id


def update_note_status(
    conn: sqlite3.Connection,
    note_id: str,
    status: str,
    current_version_id: Optional[str] = None,
):
    """Update note status and current version."""
    timestamp = get_utc_timestamp()
    if current_version_id:
        conn.execute(
            """
            UPDATE notes
            SET status = ?, current_version_id = ?, updated_at_utc = ?
            WHERE note_id = ?
            """,
            (status, current_version_id, timestamp, note_id),
        )
    else:
        conn.execute(
            """
            UPDATE notes
            SET status = ?, updated_at_utc = ?
            WHERE note_id = ?
            """,
            (status, timestamp, note_id),
        )
    conn.commit()


def get_note(conn: sqlite3.Connection, note_id: str) -> Optional[Dict[str, Any]]:
    """Get note by ID."""
    cursor = conn.execute("SELECT * FROM notes WHERE note_id = ?", (note_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


# ============================================================================
# ACTOR OPERATIONS
# ============================================================================


def create_actor(
    conn: sqlite3.Connection,
    tenant_id: str,
    actor_type: str,
    actor_name: Optional[str] = None,
    actor_role: Optional[str] = None,
    actor_identifier: Optional[str] = None,
) -> str:
    """Create a new actor."""
    actor_id = generate_ulid()
    timestamp = get_utc_timestamp()
    actor_identifier_hash = hash_content(actor_identifier) if actor_identifier else None

    conn.execute(
        """
        INSERT INTO actors (
            actor_id, tenant_id, actor_type, actor_name,
            actor_role, actor_identifier_hash, created_at_utc, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor_id,
            tenant_id,
            actor_type,
            actor_name,
            actor_role,
            actor_identifier_hash,
            timestamp,
            "active",
        ),
    )
    conn.commit()
    return actor_id


# ============================================================================
# NOTE VERSION OPERATIONS
# ============================================================================


def create_note_version(
    conn: sqlite3.Connection,
    note_id: str,
    created_by_actor_id: str,
    source: str,
    content: str,
    content_uri: Optional[str] = None,
    prev_version_id: Optional[str] = None,
    diff_stats: Optional[Dict[str, Any]] = None,
) -> str:
    """Create a new note version with hash chaining."""
    version_id = generate_ulid()
    timestamp = get_utc_timestamp()
    content_hash = hash_content(content)
    diff_stats_json = json.dumps(diff_stats) if diff_stats else None

    conn.execute(
        """
        INSERT INTO note_versions (
            version_id, note_id, created_at_utc, created_by_actor_id,
            source, content_uri, content_hash, prev_version_id, diff_stats_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version_id,
            note_id,
            timestamp,
            created_by_actor_id,
            source,
            content_uri,
            content_hash,
            prev_version_id,
            diff_stats_json,
        ),
    )
    conn.commit()
    return version_id


def get_note_versions(conn: sqlite3.Connection, note_id: str) -> List[Dict[str, Any]]:
    """Get all versions for a note."""
    cursor = conn.execute(
        "SELECT * FROM note_versions WHERE note_id = ? ORDER BY created_at_utc",
        (note_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


# ============================================================================
# AI GENERATION OPERATIONS
# ============================================================================


def create_ai_generation(
    conn: sqlite3.Connection,
    note_id: str,
    model_provider: str,
    model_id: str,
    model_version: str,
    context_snapshot_hash: str,
    output_version_id: str,
    prompt_template_id: Optional[str] = None,
    context_snapshot_uri: Optional[str] = None,
) -> str:
    """Create AI generation record."""
    generation_id = generate_ulid()
    timestamp = get_utc_timestamp()

    conn.execute(
        """
        INSERT INTO ai_generations (
            generation_id, note_id, created_at_utc, model_provider,
            model_id, model_version, prompt_template_id,
            context_snapshot_hash, context_snapshot_uri, output_version_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            generation_id,
            note_id,
            timestamp,
            model_provider,
            model_id,
            model_version,
            prompt_template_id,
            context_snapshot_hash,
            context_snapshot_uri,
            output_version_id,
        ),
    )
    conn.commit()
    return generation_id


# ============================================================================
# HUMAN REVIEW SESSION OPERATIONS
# ============================================================================


def create_review_session(
    conn: sqlite3.Connection,
    note_id: str,
    actor_id: str,
    ui_surface: Optional[str] = None,
) -> str:
    """Create human review session."""
    review_id = generate_ulid()
    timestamp = get_utc_timestamp()

    conn.execute(
        """
        INSERT INTO human_review_sessions (
            review_id, note_id, actor_id, started_at_utc, ui_surface
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (review_id, note_id, actor_id, timestamp, ui_surface),
    )
    conn.commit()
    return review_id


def end_review_session(
    conn: sqlite3.Connection,
    review_id: str,
    interaction_metrics: Optional[Dict[str, Any]] = None,
    red_flag: bool = False,
    red_flag_reason: Optional[str] = None,
):
    """End a review session and compute duration."""
    timestamp = get_utc_timestamp()
    metrics_json = json.dumps(interaction_metrics) if interaction_metrics else None

    # Get start time to compute duration
    cursor = conn.execute(
        "SELECT started_at_utc FROM human_review_sessions WHERE review_id = ?",
        (review_id,),
    )
    row = cursor.fetchone()
    if row:
        start_time = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
    else:
        duration_ms = None

    conn.execute(
        """
        UPDATE human_review_sessions
        SET ended_at_utc = ?, duration_ms = ?, interaction_metrics_json = ?,
            red_flag = ?, red_flag_reason = ?
        WHERE review_id = ?
        """,
        (timestamp, duration_ms, metrics_json, red_flag, red_flag_reason, review_id),
    )
    conn.commit()


# ============================================================================
# ATTESTATION & SIGNATURE OPERATIONS
# ============================================================================


def create_attestation(
    conn: sqlite3.Connection,
    note_id: str,
    version_id: str,
    actor_id: str,
    oversight_level: str,
    attestation_text: str,
    meaning: str,
    reason_for_change: Optional[str] = None,
) -> str:
    """Create attestation record."""
    attestation_id = generate_ulid()
    timestamp = get_utc_timestamp()

    conn.execute(
        """
        INSERT INTO attestations (
            attestation_id, note_id, version_id, actor_id,
            oversight_level, attestation_text, attested_at_utc,
            meaning, reason_for_change
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attestation_id,
            note_id,
            version_id,
            actor_id,
            oversight_level,
            attestation_text,
            timestamp,
            meaning,
            reason_for_change,
        ),
    )
    conn.commit()
    return attestation_id


def create_signature(
    conn: sqlite3.Connection,
    attestation_id: str,
    signature_type: str,
    signed_hash: str,
    signature_blob: str,
    time_source: str,
    certificate_chain: Optional[str] = None,
) -> str:
    """Create signature record."""
    signature_id = generate_ulid()
    timestamp = get_utc_timestamp()

    conn.execute(
        """
        INSERT INTO signatures (
            signature_id, attestation_id, signature_type, signed_hash,
            signature_blob, certificate_chain, signature_time_utc,
            time_source, verification_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signature_id,
            attestation_id,
            signature_type,
            signed_hash,
            signature_blob,
            certificate_chain,
            timestamp,
            time_source,
            "pending",
        ),
    )
    conn.commit()
    return signature_id


# ============================================================================
# AUDIT EVENT OPERATIONS
# ============================================================================


def create_audit_event(
    conn: sqlite3.Connection,
    tenant_id: str,
    object_type: str,
    object_id: str,
    action: str,
    event_payload: Dict[str, Any],
    actor_id: Optional[str] = None,
) -> str:
    """Create audit event with hash chaining."""
    event_id = generate_ulid()
    timestamp = get_utc_timestamp()
    payload_json = json.dumps(event_payload)

    # Get previous event hash for chain
    cursor = conn.execute(
        """
        SELECT event_hash FROM audit_events
        WHERE tenant_id = ?
        ORDER BY occurred_at_utc DESC
        LIMIT 1
        """,
        (tenant_id,),
    )
    row = cursor.fetchone()
    prev_event_hash = row[0] if row else None

    # Compute this event's hash via the shared canonical function
    event_hash = compute_event_hash(
        prev_event_hash, timestamp, object_type, object_id, action, payload_json
    )

    conn.execute(
        """
        INSERT INTO audit_events (
            event_id, tenant_id, occurred_at_utc, actor_id,
            object_type, object_id, action, event_payload_json,
            prev_event_hash, event_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            tenant_id,
            timestamp,
            actor_id,
            object_type,
            object_id,
            action,
            payload_json,
            prev_event_hash,
            event_hash,
        ),
    )
    conn.commit()
    return event_id


def get_audit_events(
    conn: sqlite3.Connection,
    tenant_id: str,
    object_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Get audit events for tenant or specific object."""
    if object_id:
        cursor = conn.execute(
            """
            SELECT * FROM audit_events
            WHERE tenant_id = ? AND object_id = ?
            ORDER BY occurred_at_utc DESC
            LIMIT ?
            """,
            (tenant_id, object_id, limit),
        )
    else:
        cursor = conn.execute(
            """
            SELECT * FROM audit_events
            WHERE tenant_id = ?
            ORDER BY occurred_at_utc DESC
            LIMIT ?
            """,
            (tenant_id, limit),
        )
    return [dict(row) for row in cursor.fetchall()]


def verify_audit_chain(conn: sqlite3.Connection, tenant_id: str) -> Dict[str, Any]:
    """Verify audit event hash chain integrity."""
    cursor = conn.execute(
        """
        SELECT event_id, occurred_at_utc, object_type, object_id, action,
               event_payload_json, prev_event_hash, event_hash
        FROM audit_events
        WHERE tenant_id = ?
        ORDER BY occurred_at_utc
        """,
        (tenant_id,),
    )

    events = cursor.fetchall()
    if not events:
        return {"valid": True, "total_events": 0, "errors": []}

    errors = []
    for i, event in enumerate(events):
        (
            event_id,
            timestamp,
            obj_type,
            obj_id,
            action,
            payload_json,
            prev_hash,
            event_hash,
        ) = event

        # Recompute hash via shared canonical function
        computed_hash = compute_event_hash(
            prev_hash, timestamp, obj_type, obj_id, action, payload_json
        )

        if computed_hash != event_hash:
            errors.append(
                {
                    "event_id": event_id,
                    "index": i,
                    "error": "Hash mismatch",
                    "expected": event_hash,
                    "computed": computed_hash,
                }
            )

        # Verify chain linkage
        if i > 0:
            prev_event = events[i - 1]
            if prev_hash != prev_event[7]:  # prev_event[7] is event_hash
                errors.append(
                    {
                        "event_id": event_id,
                        "index": i,
                        "error": "Chain break",
                        "prev_hash": prev_hash,
                        "expected": prev_event[7],
                    }
                )

    return {
        "valid": len(errors) == 0,
        "total_events": len(events),
        "errors": errors,
    }


# ============================================================================
# DEFENSE BUNDLE OPERATIONS
# ============================================================================


def create_defense_bundle(
    conn: sqlite3.Connection,
    tenant_id: str,
    requested_by_actor_id: str,
    scope: Dict[str, Any],
    verification_instructions: Optional[str] = None,
) -> str:
    """Create defense bundle export record."""
    bundle_id = generate_ulid()
    timestamp = get_utc_timestamp()
    scope_json = json.dumps(scope)

    # Compute manifest hash (simplified - in production include all items)
    manifest_hash = hash_content(f"{bundle_id}{timestamp}{scope_json}")

    conn.execute(
        """
        INSERT INTO defense_bundles (
            bundle_id, tenant_id, created_at_utc, requested_by_actor_id,
            scope_json, bundle_manifest_hash, verification_instructions
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            bundle_id,
            tenant_id,
            timestamp,
            requested_by_actor_id,
            scope_json,
            manifest_hash,
            verification_instructions,
        ),
    )
    conn.commit()
    return bundle_id


def add_bundle_item(
    conn: sqlite3.Connection,
    bundle_id: str,
    item_type: str,
    item_uri: str,
    item_content: str,
) -> str:
    """Add item to defense bundle."""
    bundle_item_id = generate_ulid()
    timestamp = get_utc_timestamp()
    item_hash = hash_content(item_content)

    conn.execute(
        """
        INSERT INTO bundle_items (
            bundle_item_id, bundle_id, item_type, item_uri,
            item_hash, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (bundle_item_id, bundle_id, item_type, item_uri, item_hash, timestamp),
    )
    conn.commit()
    return bundle_item_id


def get_bundle_items(conn: sqlite3.Connection, bundle_id: str) -> List[Dict[str, Any]]:
    """Get all items in a defense bundle."""
    cursor = conn.execute(
        "SELECT * FROM bundle_items WHERE bundle_id = ?", (bundle_id,)
    )
    return [dict(row) for row in cursor.fetchall()]
