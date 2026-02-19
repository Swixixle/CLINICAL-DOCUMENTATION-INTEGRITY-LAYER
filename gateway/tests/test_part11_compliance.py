"""
Tests for Part 11 compliance database operations.

This test suite validates the Part 11 compliant schema implementation,
including event sourcing, hash chaining, audit trails, and defense bundles.
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path
from datetime import datetime

from gateway.app.db.part11_operations import (
    create_tenant,
    get_tenant,
    create_encounter,
    get_encounter,
    create_note,
    update_note_status,
    get_note,
    create_actor,
    create_note_version,
    get_note_versions,
    create_ai_generation,
    create_review_session,
    end_review_session,
    create_attestation,
    create_signature,
    create_audit_event,
    get_audit_events,
    verify_audit_chain,
    create_defense_bundle,
    add_bundle_item,
    get_bundle_items,
    hash_content,
    hash_with_salt,
)


@pytest.fixture
def test_db():
    """Create a temporary test database with Part 11 schema."""
    # Create temp database
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Load schemas
    schema_dir = Path(__file__).parent.parent / "app" / "db"
    
    # Load base schema
    with open(schema_dir / "schema.sql", "r") as f:
        conn.executescript(f.read())
    
    # Load Part 11 schema
    with open(schema_dir / "part11_schema.sql", "r") as f:
        conn.executescript(f.read())
    
    conn.commit()

    yield conn

    # Cleanup
    conn.close()
    os.unlink(db_path)


def test_create_and_get_tenant(test_db):
    """Test tenant creation and retrieval."""
    tenant_id = create_tenant(
        test_db,
        name="Test Hospital",
        kms_key_ref="kms://test-key",
        retention_policy={"years": 7, "legal_hold_rules": {}},
    )

    assert tenant_id is not None

    tenant = get_tenant(test_db, tenant_id)
    assert tenant is not None
    assert tenant["name"] == "Test Hospital"
    assert tenant["kms_key_ref"] == "kms://test-key"
    assert tenant["status"] == "active"


def test_create_encounter_with_hashed_patient_ref(test_db):
    """Test encounter creation with patient reference hashing."""
    # Create tenant first
    tenant_id = create_tenant(test_db, name="Test Hospital")

    # Create encounter
    encounter_id = create_encounter(
        test_db,
        tenant_id=tenant_id,
        patient_id="patient-12345",
        encounter_time_start="2024-01-01T10:00:00Z",
        encounter_time_end="2024-01-01T11:00:00Z",
        source_system="Epic",
    )

    assert encounter_id is not None

    encounter = get_encounter(test_db, encounter_id)
    assert encounter is not None
    assert encounter["tenant_id"] == tenant_id
    assert encounter["source_system"] == "Epic"
    
    # Verify patient ID is hashed, not stored in plaintext
    assert encounter["patient_ref_hash"] != "patient-12345"
    assert len(encounter["patient_ref_hash"]) == 64  # SHA-256 hex length


def test_note_lifecycle_with_versions(test_db):
    """Test note creation, versioning, and status updates."""
    # Setup
    tenant_id = create_tenant(test_db, name="Test Hospital")
    encounter_id = create_encounter(
        test_db,
        tenant_id=tenant_id,
        patient_id="patient-12345",
        encounter_time_start="2024-01-01T10:00:00Z",
    )
    actor_id = create_actor(
        test_db, tenant_id=tenant_id, actor_type="human", actor_name="Dr. Smith"
    )

    # Create note
    note_id = create_note(
        test_db, tenant_id=tenant_id, encounter_id=encounter_id, note_type="progress"
    )

    note = get_note(test_db, note_id)
    assert note["status"] == "draft"
    assert note["current_version_id"] is None

    # Create first version (AI draft)
    version1_id = create_note_version(
        test_db,
        note_id=note_id,
        created_by_actor_id=actor_id,
        source="ai_draft",
        content="Patient presents with fever and cough.",
    )

    # Create second version (human edit)
    version2_id = create_note_version(
        test_db,
        note_id=note_id,
        created_by_actor_id=actor_id,
        source="human_edit",
        content="Patient presents with fever, cough, and fatigue. Prescribed antibiotics.",
        prev_version_id=version1_id,
        diff_stats={"chars_added": 35, "chars_removed": 0, "lines_changed": 1},
    )

    # Update note to finalized with current version
    update_note_status(test_db, note_id, "finalized", version2_id)

    note = get_note(test_db, note_id)
    assert note["status"] == "finalized"
    assert note["current_version_id"] == version2_id

    # Verify version chain
    versions = get_note_versions(test_db, note_id)
    assert len(versions) == 2
    assert versions[0]["version_id"] == version1_id
    assert versions[0]["prev_version_id"] is None
    assert versions[1]["version_id"] == version2_id
    assert versions[1]["prev_version_id"] == version1_id


def test_ai_generation_tracking(test_db):
    """Test AI generation tracking."""
    # Setup
    tenant_id = create_tenant(test_db, name="Test Hospital")
    encounter_id = create_encounter(
        test_db,
        tenant_id=tenant_id,
        patient_id="patient-12345",
        encounter_time_start="2024-01-01T10:00:00Z",
    )
    note_id = create_note(
        test_db, tenant_id=tenant_id, encounter_id=encounter_id, note_type="progress"
    )
    actor_id = create_actor(test_db, tenant_id=tenant_id, actor_type="ai")
    version_id = create_note_version(
        test_db,
        note_id=note_id,
        created_by_actor_id=actor_id,
        source="ai_draft",
        content="AI generated note content",
    )

    # Create AI generation record
    generation_id = create_ai_generation(
        test_db,
        note_id=note_id,
        model_provider="openai",
        model_id="gpt-4",
        model_version="gpt-4-0125-preview",
        context_snapshot_hash=hash_content("context data"),
        output_version_id=version_id,
    )

    assert generation_id is not None

    # Verify record exists
    cursor = test_db.execute(
        "SELECT * FROM ai_generations WHERE generation_id = ?", (generation_id,)
    )
    gen = dict(cursor.fetchone())
    assert gen["model_provider"] == "openai"
    assert gen["model_id"] == "gpt-4"
    assert gen["output_version_id"] == version_id


def test_human_review_session_tracking(test_db):
    """Test human review session tracking with duration calculation."""
    # Setup
    tenant_id = create_tenant(test_db, name="Test Hospital")
    encounter_id = create_encounter(
        test_db,
        tenant_id=tenant_id,
        patient_id="patient-12345",
        encounter_time_start="2024-01-01T10:00:00Z",
    )
    note_id = create_note(
        test_db, tenant_id=tenant_id, encounter_id=encounter_id, note_type="progress"
    )
    actor_id = create_actor(
        test_db, tenant_id=tenant_id, actor_type="human", actor_name="Dr. Smith"
    )

    # Create review session
    review_id = create_review_session(
        test_db, note_id=note_id, actor_id=actor_id, ui_surface="web"
    )

    # Simulate review duration by ending session
    import time
    time.sleep(0.1)  # 100ms delay

    end_review_session(
        test_db,
        review_id=review_id,
        interaction_metrics={"scroll_depth": 0.95, "keystrokes": 42},
        red_flag=False,
    )

    # Verify session
    cursor = test_db.execute(
        "SELECT * FROM human_review_sessions WHERE review_id = ?", (review_id,)
    )
    session = dict(cursor.fetchone())
    assert session["ended_at_utc"] is not None
    assert session["duration_ms"] is not None
    assert session["duration_ms"] > 0
    assert session["red_flag"] == 0  # SQLite boolean as int


def test_attestation_and_signature(test_db):
    """Test attestation and signature creation."""
    # Setup
    tenant_id = create_tenant(test_db, name="Test Hospital")
    encounter_id = create_encounter(
        test_db,
        tenant_id=tenant_id,
        patient_id="patient-12345",
        encounter_time_start="2024-01-01T10:00:00Z",
    )
    note_id = create_note(
        test_db, tenant_id=tenant_id, encounter_id=encounter_id, note_type="progress"
    )
    actor_id = create_actor(
        test_db, tenant_id=tenant_id, actor_type="human", actor_name="Dr. Smith"
    )
    version_id = create_note_version(
        test_db,
        note_id=note_id,
        created_by_actor_id=actor_id,
        source="human_edit",
        content="Final note content",
    )

    # Create attestation
    attestation_id = create_attestation(
        test_db,
        note_id=note_id,
        version_id=version_id,
        actor_id=actor_id,
        oversight_level="line_by_line_edit",
        attestation_text="I attest that I have reviewed and approve this clinical note.",
        meaning="author",
    )

    assert attestation_id is not None

    # Create signature
    attestation_payload = f"{note_id}{version_id}{actor_id}"
    signed_hash = hash_content(attestation_payload)

    signature_id = create_signature(
        test_db,
        attestation_id=attestation_id,
        signature_type="x509",
        signed_hash=signed_hash,
        signature_blob="base64encodedSignature==",
        time_source="rfc3161_tsa",
        certificate_chain="-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
    )

    assert signature_id is not None

    # Verify signature record
    cursor = test_db.execute(
        "SELECT * FROM signatures WHERE signature_id = ?", (signature_id,)
    )
    sig = dict(cursor.fetchone())
    assert sig["attestation_id"] == attestation_id
    assert sig["signature_type"] == "x509"
    assert sig["verification_status"] == "pending"


def test_audit_event_hash_chaining(test_db):
    """Test audit event creation with hash chaining."""
    tenant_id = create_tenant(test_db, name="Test Hospital")
    actor_id = create_actor(test_db, tenant_id=tenant_id, actor_type="human")

    # Create first audit event
    event1_id = create_audit_event(
        test_db,
        tenant_id=tenant_id,
        object_type="note",
        object_id="note-123",
        action="create",
        event_payload={"note_type": "progress"},
        actor_id=actor_id,
    )

    # Create second audit event
    event2_id = create_audit_event(
        test_db,
        tenant_id=tenant_id,
        object_type="note",
        object_id="note-123",
        action="modify",
        event_payload={"field": "status", "new_value": "finalized"},
        actor_id=actor_id,
    )

    # Get events
    events = get_audit_events(test_db, tenant_id, object_id="note-123")
    assert len(events) == 2

    # Verify second event links to first
    event2 = next(e for e in events if e["event_id"] == event2_id)
    event1 = next(e for e in events if e["event_id"] == event1_id)
    
    assert event1["prev_event_hash"] is None  # First event has no previous
    assert event2["prev_event_hash"] == event1["event_hash"]  # Second links to first


def test_audit_chain_verification(test_db):
    """Test audit chain integrity verification."""
    tenant_id = create_tenant(test_db, name="Test Hospital")
    actor_id = create_actor(test_db, tenant_id=tenant_id, actor_type="human")

    # Create multiple audit events
    for i in range(5):
        create_audit_event(
            test_db,
            tenant_id=tenant_id,
            object_type="note",
            object_id=f"note-{i}",
            action="create",
            event_payload={"index": i},
            actor_id=actor_id,
        )

    # Verify chain
    result = verify_audit_chain(test_db, tenant_id)
    assert result["valid"] is True
    assert result["total_events"] == 5
    assert len(result["errors"]) == 0


def test_audit_chain_tampering_detection(test_db):
    """Test that audit chain detects tampering."""
    tenant_id = create_tenant(test_db, name="Test Hospital")
    actor_id = create_actor(test_db, tenant_id=tenant_id, actor_type="human")

    # Create audit events
    event1_id = create_audit_event(
        test_db,
        tenant_id=tenant_id,
        object_type="note",
        object_id="note-1",
        action="create",
        event_payload={"test": "data1"},
        actor_id=actor_id,
    )

    event2_id = create_audit_event(
        test_db,
        tenant_id=tenant_id,
        object_type="note",
        object_id="note-2",
        action="create",
        event_payload={"test": "data2"},
        actor_id=actor_id,
    )

    # Tamper with first event's payload (simulating attack)
    test_db.execute(
        """
        UPDATE audit_events
        SET event_payload_json = ?
        WHERE event_id = ?
        """,
        ('{"test": "tampered"}', event1_id),
    )
    test_db.commit()

    # Verify chain - should detect tampering
    result = verify_audit_chain(test_db, tenant_id)
    assert result["valid"] is False
    assert len(result["errors"]) > 0
    assert result["errors"][0]["error"] == "Hash mismatch"


def test_defense_bundle_creation(test_db):
    """Test defense bundle and item creation."""
    tenant_id = create_tenant(test_db, name="Test Hospital")
    actor_id = create_actor(test_db, tenant_id=tenant_id, actor_type="human")

    # Create defense bundle
    bundle_id = create_defense_bundle(
        test_db,
        tenant_id=tenant_id,
        requested_by_actor_id=actor_id,
        scope={
            "note_ids": ["note-1", "note-2"],
            "date_range": {"start": "2024-01-01", "end": "2024-01-31"},
        },
        verification_instructions="Verify with OpenSSL using public key",
    )

    assert bundle_id is not None

    # Add items to bundle
    item1_id = add_bundle_item(
        test_db,
        bundle_id=bundle_id,
        item_type="note_json",
        item_uri="s3://bundles/note-1.json",
        item_content='{"note_id": "note-1", "content": "..."}',
    )

    item2_id = add_bundle_item(
        test_db,
        bundle_id=bundle_id,
        item_type="audit_log",
        item_uri="s3://bundles/audit-log.json",
        item_content='[{"event_id": "e1"}, {"event_id": "e2"}]',
    )

    # Get bundle items
    items = get_bundle_items(test_db, bundle_id)
    assert len(items) == 2
    assert items[0]["item_type"] == "note_json"
    assert items[1]["item_type"] == "audit_log"


def test_patient_reference_hashing_is_consistent(test_db):
    """Test that patient reference hashing is consistent for same input."""
    tenant_id = create_tenant(test_db, name="Test Hospital")
    patient_id = "patient-12345"

    # Create two encounters with same patient ID
    encounter1_id = create_encounter(
        test_db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        encounter_time_start="2024-01-01T10:00:00Z",
    )

    encounter2_id = create_encounter(
        test_db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        encounter_time_start="2024-01-02T10:00:00Z",
    )

    # Verify same patient hash
    encounter1 = get_encounter(test_db, encounter1_id)
    encounter2 = get_encounter(test_db, encounter2_id)

    assert encounter1["patient_ref_hash"] == encounter2["patient_ref_hash"]


def test_patient_reference_hashing_is_tenant_isolated(test_db):
    """Test that patient reference hashing is tenant-isolated."""
    tenant1_id = create_tenant(test_db, name="Hospital A")
    tenant2_id = create_tenant(test_db, name="Hospital B")
    patient_id = "patient-12345"

    # Create encounters in different tenants
    encounter1_id = create_encounter(
        test_db,
        tenant_id=tenant1_id,
        patient_id=patient_id,
        encounter_time_start="2024-01-01T10:00:00Z",
    )

    encounter2_id = create_encounter(
        test_db,
        tenant_id=tenant2_id,
        patient_id=patient_id,
        encounter_time_start="2024-01-01T10:00:00Z",
    )

    # Verify different hashes (tenant is used as salt)
    encounter1 = get_encounter(test_db, encounter1_id)
    encounter2 = get_encounter(test_db, encounter2_id)

    assert encounter1["patient_ref_hash"] != encounter2["patient_ref_hash"]


def test_note_version_content_hashing(test_db):
    """Test that note version content is hashed correctly."""
    tenant_id = create_tenant(test_db, name="Test Hospital")
    encounter_id = create_encounter(
        test_db,
        tenant_id=tenant_id,
        patient_id="patient-12345",
        encounter_time_start="2024-01-01T10:00:00Z",
    )
    note_id = create_note(
        test_db, tenant_id=tenant_id, encounter_id=encounter_id, note_type="progress"
    )
    actor_id = create_actor(test_db, tenant_id=tenant_id, actor_type="human")

    content = "Patient presents with symptoms."
    expected_hash = hash_content(content)

    version_id = create_note_version(
        test_db,
        note_id=note_id,
        created_by_actor_id=actor_id,
        source="human_edit",
        content=content,
    )

    # Verify hash
    cursor = test_db.execute(
        "SELECT content_hash FROM note_versions WHERE version_id = ?", (version_id,)
    )
    row = cursor.fetchone()
    assert row["content_hash"] == expected_hash


def test_no_phi_in_audit_events(test_db):
    """Test that PHI is not stored in audit events."""
    tenant_id = create_tenant(test_db, name="Test Hospital")
    actor_id = create_actor(test_db, tenant_id=tenant_id, actor_type="human")

    # Create audit event with only references, no PHI
    event_id = create_audit_event(
        test_db,
        tenant_id=tenant_id,
        object_type="note",
        object_id="note-123",
        action="create",
        event_payload={
            "note_id": "note-123",
            "note_type": "progress",
            "note_hash": hash_content("note content"),
            # NO PHI - only hashes and references
        },
        actor_id=actor_id,
    )

    # Verify payload contains no plaintext PHI
    cursor = test_db.execute(
        "SELECT event_payload_json FROM audit_events WHERE event_id = ?", (event_id,)
    )
    row = cursor.fetchone()
    payload = row["event_payload_json"]
    
    # Payload should not contain patient names, note text, etc.
    assert "patient" not in payload.lower() or "patient_hash" in payload
    assert "content" not in payload or "content_hash" in payload
