"""Tests for verify-ledger-integrity.sh script and verify_ledger_integrity.py."""

import os
import subprocess
import sqlite3
import hashlib
import json
import tempfile
from datetime import datetime, timezone


def hash_content(content: str) -> str:
    """Hash content using SHA-256."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def create_test_database(db_path: str, num_events: int = 5) -> str:
    """Create a test database with audit events."""
    conn = sqlite3.connect(db_path)

    # Create audit_events table
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

    tenant_id = "tenant_test"
    actor_id = "actor_test"
    prev_hash = None

    for i in range(num_events):
        import uuid

        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        object_type = "note"
        object_id = f"note_{i}"
        action = "create"
        payload = {"description": f"Created note {i}"}
        payload_json = json.dumps(payload)

        # Compute event hash
        hash_input = f"{prev_hash or ''}{timestamp}{object_type}{object_id}{action}{payload_json}"
        event_hash = hash_content(hash_input)

        conn.execute(
            """
            INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                prev_hash,
                event_hash,
            ),
        )

        prev_hash = event_hash

    conn.commit()
    conn.close()

    return tenant_id


def test_verify_ledger_integrity_valid():
    """Test verification with valid audit chain."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        create_test_database(db_path, num_events=10)

        result = subprocess.run(
            ["./tools/verify-ledger-integrity.sh", "--db", db_path],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "LEDGER INTEGRITY VERIFIED" in result.stdout
        assert "10" in result.stdout  # Total events
        assert "No tampering detected" in result.stdout


def test_verify_ledger_integrity_verbose():
    """Test verification with verbose output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        create_test_database(db_path, num_events=3)

        result = subprocess.run(
            ["./tools/verify-ledger-integrity.sh", "--db", db_path, "--verbose"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Verbose messages go to stderr
        assert "Event 1/3:" in result.stderr or "Event 1/3:" in result.stdout
        assert "Event 2/3:" in result.stderr or "Event 2/3:" in result.stdout
        assert "Event 3/3:" in result.stderr or "Event 3/3:" in result.stdout
        assert "AUDIT LEDGER INTEGRITY VERIFICATION" in result.stdout


def test_verify_ledger_integrity_json_output():
    """Test verification with JSON output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        create_test_database(db_path, num_events=5)

        result = subprocess.run(
            ["./tools/verify-ledger-integrity.sh", "--db", db_path, "--json"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Parse JSON output
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["total_events"] == 5
        assert data["verified_events"] == 5
        assert len(data["errors"]) == 0


def test_verify_ledger_integrity_tampered():
    """Test verification detects tampering."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        create_test_database(db_path, num_events=5)

        # Tamper with database
        conn = sqlite3.connect(db_path)
        conn.execute("""
            UPDATE audit_events
            SET event_payload_json = '{"description": "TAMPERED"}'
            WHERE object_id = 'note_2'
        """)
        conn.commit()
        conn.close()

        result = subprocess.run(
            ["./tools/verify-ledger-integrity.sh", "--db", db_path],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "LEDGER INTEGRITY VIOLATION DETECTED" in result.stdout
        assert "Hash mismatch - event has been tampered with" in result.stdout
        assert "RECOMMENDED ACTIONS" in result.stdout


def test_verify_ledger_integrity_chain_break():
    """Test verification detects chain break."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        create_test_database(db_path, num_events=5)

        # Break the chain by modifying prev_event_hash
        conn = sqlite3.connect(db_path)
        conn.execute("""
            UPDATE audit_events
            SET prev_event_hash = 'invalid_hash_12345'
            WHERE object_id = 'note_3'
        """)
        conn.commit()
        conn.close()

        result = subprocess.run(
            ["./tools/verify-ledger-integrity.sh", "--db", db_path, "--json"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1

        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert len(data["errors"]) > 0

        # Check for chain break error
        errors = data["errors"]
        assert any("Chain break" in err["error"] for err in errors)


def test_verify_ledger_integrity_nonexistent_db():
    """Test verification with nonexistent database."""
    result = subprocess.run(
        ["./tools/verify-ledger-integrity.sh", "--db", "/nonexistent/path/db.db"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Database not found" in result.stderr


def test_verify_ledger_integrity_empty_ledger():
    """Test verification with empty ledger."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        create_test_database(db_path, num_events=0)

        result = subprocess.run(
            ["./tools/verify-ledger-integrity.sh", "--db", db_path, "--json"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["total_events"] == 0


def test_verify_ledger_integrity_help():
    """Test help output."""
    result = subprocess.run(
        ["./tools/verify-ledger-integrity.sh", "--help"], capture_output=True, text=True
    )

    assert result.returncode == 0
    assert "verify-ledger-integrity.sh" in result.stdout
    assert "Usage:" in result.stdout
    assert "Options:" in result.stdout
    assert "FDA 21 CFR Part 11" in result.stdout


def test_verify_ledger_integrity_tenant_filter():
    """Test verification with tenant filter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        tenant_id = create_test_database(db_path, num_events=5)

        result = subprocess.run(
            [
                "./tools/verify-ledger-integrity.sh",
                "--db",
                db_path,
                "--tenant",
                tenant_id,
                "--json",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["total_events"] == 5


def test_verify_ledger_integrity_engine_sqlite_explicit():
    """Test that --engine sqlite works explicitly (same as default)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        create_test_database(db_path, num_events=5)

        result = subprocess.run(
            [
                "./tools/verify-ledger-integrity.sh",
                "--engine",
                "sqlite",
                "--db",
                db_path,
                "--json",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["total_events"] == 5


def test_verify_ledger_integrity_engine_invalid():
    """Test that an invalid --engine value exits with code 3."""
    result = subprocess.run(
        ["./tools/verify-ledger-integrity.sh", "--engine", "oracle"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 3


def test_verify_ledger_integrity_postgres_missing_url():
    """Test that --engine postgres without --pg-url exits with code 2."""
    result = subprocess.run(
        ["./tools/verify-ledger-integrity.sh", "--engine", "postgres"],
        capture_output=True,
        text=True,
        env={**os.environ, "PGURL": ""},
    )
    assert result.returncode == 2
    assert "pg-url" in result.stderr.lower() or "PGURL" in result.stderr


def test_production_db_setup_sql_exists():
    """Test that deploy/production-db-setup.sql exists and contains audit_events."""
    sql_path = "deploy/production-db-setup.sql"
    assert os.path.isfile(sql_path), f"Missing: {sql_path}"

    content = open(sql_path).read()
    assert "CREATE TABLE IF NOT EXISTS audit_events" in content
    assert "event_hash" in content
    assert "prev_event_hash" in content


def test_production_db_setup_sql_schema_version_header():
    """Test that production-db-setup.sql has the required header block."""
    sql_path = "deploy/production-db-setup.sql"
    content = open(sql_path).read()

    assert "Schema Version:" in content
    assert "Compatibility:" in content
    assert "alembic upgrade head" in content


# ---------------------------------------------------------------------------
# Unit tests for tools/verify_ledger_integrity.py (Python verifier)
# ---------------------------------------------------------------------------


def _make_sqlite_db(
    db_path: str, num_events: int = 5, tenant_id: str = "t_test"
) -> None:
    """Create a SQLite test database using the canonical compute_event_hash."""
    from gateway.app.db.ledger_hashing import compute_event_hash

    import uuid

    conn = sqlite3.connect(db_path)
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
    prev_hash = None
    for i in range(num_events):
        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        obj_type, obj_id, action = "note", f"note_{i}", "create"
        payload_json = json.dumps({"seq": i})
        event_hash = compute_event_hash(
            prev_hash, timestamp, obj_type, obj_id, action, payload_json
        )
        conn.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                tenant_id,
                timestamp,
                None,
                obj_type,
                obj_id,
                action,
                payload_json,
                prev_hash,
                event_hash,
            ),
        )
        prev_hash = event_hash
    conn.commit()
    conn.close()


def test_python_verifier_pass():
    """Python verifier returns PASS for a valid chain."""
    from tools.verify_ledger_integrity import verify

    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "test.db")
        _make_sqlite_db(db, num_events=5)
        result = verify("sqlite", db, "")
        assert result["status"] == "PASS"
        assert result["valid"] is True
        assert result["total_events"] == 5
        assert result["verified_events"] == 5
        assert result["failure"] is None
        assert result["errors"] == []
        assert result["engine"] == "sqlite"


def test_python_verifier_tamper_fail():
    """Python verifier returns FAIL with failure details when event is tampered."""
    from tools.verify_ledger_integrity import verify

    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "test.db")
        _make_sqlite_db(db, num_events=5)

        conn = sqlite3.connect(db)
        conn.execute(
            "UPDATE audit_events SET event_payload_json = '{\"tampered\": true}' "
            "WHERE object_id = 'note_2'"
        )
        conn.commit()
        conn.close()

        result = verify("sqlite", db, "")
        assert result["status"] == "FAIL"
        assert result["valid"] is False
        assert result["failure"] is not None
        assert "Hash mismatch" in result["failure"]["reason"]
        assert result["failure"]["event_id"] is not None
        assert isinstance(result["failure"]["index"], int)


def test_python_verifier_chain_break_fail():
    """Python verifier returns FAIL with failure details on chain break."""
    from tools.verify_ledger_integrity import verify

    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "test.db")
        _make_sqlite_db(db, num_events=5)

        conn = sqlite3.connect(db)
        conn.execute(
            "UPDATE audit_events SET prev_event_hash = 'badhash' "
            "WHERE object_id = 'note_3'"
        )
        conn.commit()
        conn.close()

        result = verify("sqlite", db, "")
        assert result["status"] == "FAIL"
        assert result["valid"] is False
        assert result["failure"] is not None
        assert result["failure"]["event_id"] is not None


def test_python_verifier_empty_ledger():
    """Python verifier returns PASS for an empty ledger."""
    from tools.verify_ledger_integrity import verify

    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "test.db")
        _make_sqlite_db(db, num_events=0)
        result = verify("sqlite", db, "")
        assert result["status"] == "PASS"
        assert result["total_events"] == 0
        assert result["failure"] is None


def test_python_verifier_json_output_fields():
    """Python verifier JSON output contains all required fields."""
    from tools.verify_ledger_integrity import verify

    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "test.db")
        _make_sqlite_db(db, num_events=3)
        result = verify("sqlite", db, "")

    for field in (
        "status",
        "engine",
        "total_events",
        "verified_events",
        "failure",
        "errors",
    ):
        assert field in result, f"Missing required field: {field}"


def test_python_verifier_cli_pass(tmp_path):
    """Python verifier CLI exits 0 and outputs JSON for a valid chain."""
    db = str(tmp_path / "test.db")
    _make_sqlite_db(db, num_events=4)

    result = subprocess.run(
        [
            "python3",
            "tools/verify_ledger_integrity.py",
            "--engine",
            "sqlite",
            "--db",
            db,
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["status"] == "PASS"
    assert data["total_events"] == 4


def test_python_verifier_cli_fail_tamper(tmp_path):
    """Python verifier CLI exits 1 and failure field populated on tamper."""
    db = str(tmp_path / "test.db")
    _make_sqlite_db(db, num_events=4)

    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE audit_events SET event_payload_json = '{\"x\":1}' WHERE object_id='note_1'"
    )
    conn.commit()
    conn.close()

    result = subprocess.run(
        [
            "python3",
            "tools/verify_ledger_integrity.py",
            "--engine",
            "sqlite",
            "--db",
            db,
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "FAIL"
    assert data["failure"] is not None
    assert "Hash mismatch" in data["failure"]["reason"]
    assert data["failure"]["event_id"] is not None


def test_ledger_hashing_is_canonical_source():
    """ledger_hashing.compute_event_hash must match part11_operations hash logic."""
    from gateway.app.db.ledger_hashing import compute_event_hash, hash_content

    prev = "abc"
    ts = "2026-01-01T00:00:00Z"
    ot, oid, act, pj = "note", "n1", "create", '{"k": "v"}'

    # Canonical function
    h1 = compute_event_hash(prev, ts, ot, oid, act, pj)
    # Direct formula — must match identically
    h2 = hash_content(f"{prev}{ts}{ot}{oid}{act}{pj}")
    assert h1 == h2
