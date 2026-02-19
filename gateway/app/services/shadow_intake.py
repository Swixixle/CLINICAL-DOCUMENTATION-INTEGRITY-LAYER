"""
Shadow Mode Intake Service.

Handles ingestion and storage of clinical notes in shadow mode (read-only).
PHI-safe by default: only hashes stored unless explicitly configured.
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from gateway.app.db.migrate import get_db_path
from gateway.app.services.uuid7 import generate_uuid7
from gateway.app.services.hashing import sha256_hex


def is_store_note_text_enabled() -> bool:
    """Check if note text storage is explicitly enabled via configuration."""
    return os.environ.get("STORE_NOTE_TEXT", "false").lower() == "true"


def create_shadow_item(
    tenant_id: str,
    note_text: str,
    encounter_id: Optional[str] = None,
    patient_reference: Optional[str] = None,
    source_system: Optional[str] = None,
    note_type: Optional[str] = None,
    author_role: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a shadow item for read-only ingestion.

    PHI Safety: note_text is hashed but NOT stored unless STORE_NOTE_TEXT=true.

    Args:
        tenant_id: Tenant identifier from authentication
        note_text: Clinical note text
        encounter_id: Optional encounter identifier
        patient_reference: Optional patient reference
        source_system: Optional source system identifier
        note_type: Optional note type
        author_role: Optional author role

    Returns:
        Dict with shadow_id, note_hash, timestamp, tenant_id, status
    """
    # Generate shadow_id using UUID7 (time-ordered)
    shadow_id = generate_uuid7()

    # Hash the note text
    note_hash = sha256_hex(note_text.encode("utf-8"))

    # Hash patient reference if provided (PHI protection)
    if patient_reference:
        patient_reference = sha256_hex(patient_reference.encode("utf-8"))

    # Current UTC timestamp
    created_at_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Determine if we should store note text
    store_text = is_store_note_text_enabled()
    stored_note_text = note_text if store_text else None

    # Get database connection
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Insert shadow item
        cursor.execute(
            """
            INSERT INTO shadow_items (
                shadow_id, tenant_id, created_at_utc, note_hash,
                note_text, encounter_id, patient_reference,
                source_system, note_type, author_role, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                shadow_id,
                tenant_id,
                created_at_utc,
                note_hash,
                stored_note_text,
                encounter_id,
                patient_reference,
                source_system,
                note_type,
                author_role,
                "ingested",
            ),
        )

        conn.commit()

        return {
            "shadow_id": shadow_id,
            "note_hash": note_hash,
            "timestamp": created_at_utc,
            "tenant_id": tenant_id,
            "status": "ingested",
        }

    finally:
        conn.close()


def get_shadow_item(shadow_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a shadow item by ID.

    Enforces tenant isolation: returns None if shadow_id belongs to different tenant.

    Args:
        shadow_id: Shadow item identifier
        tenant_id: Tenant identifier from authentication

    Returns:
        Shadow item dict or None if not found or unauthorized
    """
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT * FROM shadow_items
            WHERE shadow_id = ? AND tenant_id = ?
        """,
            (shadow_id, tenant_id),
        )

        row = cursor.fetchone()

        if not row:
            return None

        # Convert row to dict
        return dict(row)

    finally:
        conn.close()


def list_shadow_items(
    tenant_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    status: Optional[str] = None,
    score_band: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    """
    List shadow items with optional filters.

    Enforces tenant isolation: only returns items for the authenticated tenant.

    Args:
        tenant_id: Tenant identifier from authentication
        from_date: Optional start date filter (ISO 8601)
        to_date: Optional end date filter (ISO 8601)
        status: Optional status filter
        score_band: Optional score band filter (green, yellow, red)
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        Dict with items, total, page, page_size
    """
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Build WHERE clause
        where_clauses = ["tenant_id = ?"]
        params = [tenant_id]

        if from_date:
            where_clauses.append("created_at_utc >= ?")
            params.append(from_date)

        if to_date:
            where_clauses.append("created_at_utc <= ?")
            params.append(to_date)

        if status:
            where_clauses.append("status = ?")
            params.append(status)

        if score_band:
            where_clauses.append("score_band = ?")
            params.append(score_band)

        where_sql = " AND ".join(where_clauses)

        # Get total count
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM shadow_items
            WHERE {where_sql}
        """,
            params,
        )
        total = cursor.fetchone()[0]

        # Calculate offset
        offset = (page - 1) * page_size

        # Get items for current page
        cursor.execute(
            f"""
            SELECT * FROM shadow_items
            WHERE {where_sql}
            ORDER BY created_at_utc DESC
            LIMIT ? OFFSET ?
        """,
            params + [page_size, offset],
        )

        rows = cursor.fetchall()
        items = [dict(row) for row in rows]

        # Remove note_text from response unless explicitly stored
        # (it shouldn't be in the response by default for PHI safety)
        for item in items:
            if item.get("note_text") is None:
                # Remove key entirely if NULL
                item.pop("note_text", None)

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    finally:
        conn.close()


def update_shadow_item_analysis(
    shadow_id: str,
    tenant_id: str,
    score: int,
    score_band: str,
    certificate_id: Optional[str] = None,
) -> bool:
    """
    Update shadow item with analysis results.

    Args:
        shadow_id: Shadow item identifier
        tenant_id: Tenant identifier (for authorization)
        score: Evidence score (0-100)
        score_band: Risk band (green, yellow, red)
        certificate_id: Optional linked certificate ID

    Returns:
        True if updated, False if not found or unauthorized
    """
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE shadow_items
            SET score = ?, score_band = ?, status = 'analyzed', certificate_id = ?
            WHERE shadow_id = ? AND tenant_id = ?
        """,
            (score, score_band, certificate_id, shadow_id, tenant_id),
        )

        conn.commit()

        return cursor.rowcount > 0

    finally:
        conn.close()
