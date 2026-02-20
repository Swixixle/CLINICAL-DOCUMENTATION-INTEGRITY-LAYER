"""
Tests for ledger hashing single-source canonicalization and verifier correctness.

A7 acceptance criteria:
1. part11_operations.hash_content equals ledger_hashing.hash_content (backward compat)
2. Verifier exits 2 with missing-columns error when columns are absent
3. Verifier JSON output includes 'ordering' and 'hash_policy'
4. SQLite tamper detection returns exit 1 with a reason
"""

import json
import os
import sqlite3
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(num_events: int = 5, include_required_columns: bool = True) -> str:
    """Create a temporary SQLite DB with valid audit events. Returns db path."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = sqlite3.connect(db_path)

    if include_required_columns:
        conn.execute("""
            CREATE TABLE audit_events (
                event_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                occurred_at_utc TEXT NOT NULL,
                actor_id TEXT,
                object_type TEXT NOT NULL,
                object_id TEXT NOT NULL,
                action TEXT NOT NULL,
                event_payload_json TEXT NOT NULL,
                prev_event_hash TEXT,
                event_hash TEXT NOT NULL
            )
            """)
    else:
        # Minimal table missing required columns for A7 test 2
        conn.execute("""
            CREATE TABLE audit_events (
                event_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL
            )
            """)
        conn.commit()
        conn.close()
        return db_path

    from gateway.app.db.ledger_hashing import compute_event_hash

    prev_hash = None
    for i in range(num_events):
        event_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        obj_type = "note"
        obj_id = f"note_{i}"
        action = "create"
        payload = json.dumps({"step": i})
        event_hash = compute_event_hash(
            prev_hash, ts, obj_type, obj_id, action, payload
        )
        conn.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                "tenant_t",
                ts,
                None,
                obj_type,
                obj_id,
                action,
                payload,
                prev_hash,
                event_hash,
            ),
        )
        conn.commit()
        prev_hash = event_hash

    conn.close()
    return db_path


def _run_verifier(*extra_args: str) -> subprocess.CompletedProcess:
    """Run tools/verify_ledger_integrity.py and return the CompletedProcess."""
    return subprocess.run(
        ["python3", "tools/verify_ledger_integrity.py"] + list(extra_args),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": os.getcwd()},
    )


# ---------------------------------------------------------------------------
# A7 test 1: backward-compat hash_content re-export
# ---------------------------------------------------------------------------


def test_hash_content_backward_compat():
    """part11_operations.hash_content and ledger_hashing.hash_content are identical."""
    from gateway.app.db.ledger_hashing import hash_content as lh_hash
    from gateway.app.db.part11_operations import hash_content as ops_hash

    for payload in [
        "",
        "hello world",
        '{"key": "value", "n": 42}',
        "a" * 1000,
    ]:
        assert lh_hash(payload) == ops_hash(
            payload
        ), f"Hash mismatch for payload: {payload!r}"


# ---------------------------------------------------------------------------
# A7 test 2: verifier exits 2 when required columns are missing
# ---------------------------------------------------------------------------


def test_verifier_exits_2_on_missing_columns():
    """Verifier exits with code 2 and reports missing columns."""
    db_path = _make_db(num_events=0, include_required_columns=False)
    try:
        result = _run_verifier("--engine", "sqlite", "--db", db_path)
        assert (
            result.returncode == 2
        ), f"Expected exit 2, got {result.returncode}.\nstdout: {result.stdout}"
        data = json.loads(result.stdout)
        assert data["status"] == "ERROR"
        assert "error" in data
        assert "missing" in data["error"].lower() or "Missing" in data["error"]
    finally:
        os.unlink(db_path)


# ---------------------------------------------------------------------------
# A7 test 3: verifier JSON includes ordering and hash_policy
# ---------------------------------------------------------------------------


def test_verifier_json_includes_ordering_and_hash_policy():
    """Verifier JSON output always contains 'ordering' and 'hash_policy'."""
    db_path = _make_db(num_events=3)
    try:
        result = _run_verifier("--engine", "sqlite", "--db", db_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)

        assert "ordering" in data, "JSON must contain 'ordering'"
        assert "hash_policy" in data, "JSON must contain 'hash_policy'"
        assert "status" in data, "JSON must contain 'status'"
        assert data["status"] == "PASS"
        assert "occurred_at_utc" in data["ordering"]
        assert "SHA-256" in data["hash_policy"]
    finally:
        os.unlink(db_path)


def test_verifier_json_schema_complete():
    """Verifier JSON output has all required fields."""
    db_path = _make_db(num_events=2)
    try:
        result = _run_verifier("--engine", "sqlite", "--db", db_path)
        data = json.loads(result.stdout)

        required_keys = {
            "status",
            "engine",
            "ordering",
            "hash_policy",
            "total_events",
            "verified_events",
            "failure",
            "valid",
        }
        missing = required_keys - set(data.keys())
        assert not missing, f"JSON missing keys: {missing}"
        assert data["engine"] == "sqlite"
    finally:
        os.unlink(db_path)


# ---------------------------------------------------------------------------
# A7 test 4: SQLite tamper detection returns exit 1 with reason
# ---------------------------------------------------------------------------


def test_verifier_detects_tamper_exit_1_with_reason():
    """Tampered event causes verifier to exit 1; JSON reports the reason."""
    db_path = _make_db(num_events=5)
    try:
        # Tamper: change payload of note_2
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE audit_events SET event_payload_json = '{\"tampered\": true}'"
            " WHERE object_id = 'note_2'"
        )
        conn.commit()
        conn.close()

        result = _run_verifier("--engine", "sqlite", "--db", db_path)
        assert (
            result.returncode == 1
        ), f"Expected exit 1 (FAIL), got {result.returncode}.\nstdout: {result.stdout}"

        data = json.loads(result.stdout)
        assert data["status"] == "FAIL"
        assert data["valid"] is False
        assert len(data["errors"]) > 0

        # failure field must be populated
        assert data["failure"] is not None
        assert "reason" in data["failure"]
        assert "Hash mismatch" in data["failure"]["reason"]

        # At least one error mentions hash mismatch
        assert any("Hash mismatch" in e.get("error", "") for e in data["errors"])
    finally:
        os.unlink(db_path)


def test_verifier_detects_chain_break_exit_1():
    """Chain break causes verifier to exit 1."""
    db_path = _make_db(num_events=4)
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE audit_events SET prev_event_hash = 'badhash_xyz'"
            " WHERE object_id = 'note_3'"
        )
        conn.commit()
        conn.close()

        result = _run_verifier("--engine", "sqlite", "--db", db_path)
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert any("Chain break" in e.get("error", "") for e in data["errors"])
    finally:
        os.unlink(db_path)


# ---------------------------------------------------------------------------
# Writer/verifier round-trip: same hash for the same event
# ---------------------------------------------------------------------------


def test_writer_verifier_hash_parity():
    """
    An event written with create_audit_event passes the verifier with no errors.
    This catches any canonicalization drift between writer and verifier.
    """
    import sqlite3
    import tempfile
    from pathlib import Path

    # Build a fresh in-memory style DB with the real schema
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    schema_dir = Path(__file__).parent.parent / "app" / "db"
    with open(schema_dir / "schema.sql") as f:
        conn.executescript(f.read())
    with open(schema_dir / "part11_schema.sql") as f:
        conn.executescript(f.read())

    from gateway.app.db.part11_operations import (
        create_actor,
        create_audit_event,
        create_tenant,
    )

    tenant_id = create_tenant(conn, "parity-test")
    actor_id = create_actor(conn, tenant_id, "system")
    create_audit_event(
        conn,
        tenant_id=tenant_id,
        object_type="note",
        object_id="note-abc",
        action="create",
        event_payload={"ref": "abc"},
        actor_id=actor_id,
    )
    create_audit_event(
        conn,
        tenant_id=tenant_id,
        object_type="note",
        object_id="note-abc",
        action="finalize",
        event_payload={"ref": "abc", "v": 2},
        actor_id=actor_id,
    )
    conn.close()

    result = _run_verifier("--engine", "sqlite", "--db", db_path)
    os.unlink(db_path)

    assert (
        result.returncode == 0
    ), f"Writer/verifier parity test failed.\nstdout: {result.stdout}"
    data = json.loads(result.stdout)
    assert data["valid"] is True
    assert data["total_events"] == 2
    assert data["verified_events"] == 2
