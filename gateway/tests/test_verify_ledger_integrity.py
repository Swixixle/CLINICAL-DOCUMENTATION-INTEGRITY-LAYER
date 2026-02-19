"""Tests for verify-ledger-integrity.sh script."""

import os
import subprocess
import sqlite3
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest


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
        
        conn.execute("""
            INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (event_id, tenant_id, timestamp, actor_id, object_type, object_id, action, payload_json, prev_hash, event_hash))
        
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
            text=True
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
            text=True
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
            text=True
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
            text=True
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
            text=True
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
        text=True
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
            text=True
        )
        
        assert result.returncode == 0
        
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["total_events"] == 0


def test_verify_ledger_integrity_help():
    """Test help output."""
    result = subprocess.run(
        ["./tools/verify-ledger-integrity.sh", "--help"],
        capture_output=True,
        text=True
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
            ["./tools/verify-ledger-integrity.sh", "--db", db_path, "--tenant", tenant_id, "--json"],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["total_events"] == 5
