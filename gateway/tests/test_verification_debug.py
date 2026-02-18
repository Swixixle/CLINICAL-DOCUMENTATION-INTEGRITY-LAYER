"""
Tests for Phase 2.1 hardening - Verification debug field policies.

Tests that:
- Debug fields contain only prefixes/types, not full messages
- Failure schema is enforced consistently
- Exception messages are not leaked in API responses
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil
import json

from gateway.app.main import app
from gateway.app.db.migrate import get_db_path, ensure_schema
from gateway.app.services.storage import bootstrap_dev_keys


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database."""
    # Save original db path
    original_db = get_db_path()
    
    # Create temp directory for test db
    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "test.db"
    
    # Monkey patch the get_db_path function
    import gateway.app.db.migrate as migrate_module
    original_get_db_path = migrate_module.get_db_path
    migrate_module.get_db_path = lambda: temp_db_path
    
    # Initialize schema
    ensure_schema()
    bootstrap_dev_keys()
    
    yield temp_db_path
    
    # Cleanup
    migrate_module.get_db_path = original_get_db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def client(test_db):
    """Create a test client with temporary database."""
    with TestClient(app) as test_client:
        yield test_client


def test_debug_field_contains_no_full_exception_messages(client):
    """Test that debug fields contain exception types only, not full messages.
    
    This test ensures the "prefixes only" policy is enforced:
    - Debug fields should contain exception types (e.g., "ValueError")
    - Debug fields should NOT contain full exception messages
    - This prevents information leakage through error messages
    """
    # Create a transaction
    request = {
        "prompt": "Test prompt",
        "environment": "dev",
        "client_id": "test-client",
        "feature_tag": "test",
        "model": "gpt-4",
        "temperature": 0.5
    }
    
    create_response = client.post("/v1/ai/call", json=request)
    assert create_response.status_code == 200
    transaction_id = create_response.json()["transaction_id"]
    
    # Tamper with packet to trigger recomputation failure
    from gateway.app.services.storage import get_transaction
    from gateway.app.db.migrate import get_connection
    
    packet = get_transaction(transaction_id)
    
    # Corrupt the packet structure to trigger an exception during verification
    # Remove a required field that build_halo_chain needs
    del packet["policy_receipt"]
    
    # Store the corrupted packet
    packet_json = json.dumps(packet, sort_keys=True)
    conn = get_connection()
    try:
        conn.execute("""
            UPDATE transactions
            SET packet_json = ?
            WHERE transaction_id = ?
        """, (packet_json, transaction_id))
        conn.commit()
    finally:
        conn.close()
    
    # Verify should fail with exception
    verify_response = client.post(f"/v1/transactions/{transaction_id}/verify")
    assert verify_response.status_code == 200
    
    result = verify_response.json()
    assert result["valid"] is False
    
    # Find HALO chain failure
    halo_failures = [f for f in result["failures"] if f["check"] == "halo_chain"]
    assert len(halo_failures) > 0
    assert halo_failures[0]["error"] == "recomputation_failed"
    
    # Check debug field structure
    assert "debug" in halo_failures[0]
    debug = halo_failures[0]["debug"]
    
    # CRITICAL POLICY CHECK: Debug should contain exception type, not message
    assert "exception" in debug
    assert "message" not in debug  # Must NOT have 'message' key
    
    # Exception type should be a class name (e.g., "KeyError", "ValueError")
    exception_type = debug["exception"]
    assert isinstance(exception_type, str)
    assert len(exception_type) > 0
    
    # Exception type should not contain detailed error information
    # It should just be the exception class name
    assert "policy_receipt" not in exception_type.lower()  # No field names
    assert "missing" not in exception_type.lower()  # No error details
    

def test_failure_schema_consistency(client):
    """Test that all failures follow consistent schema.
    
    Verifies that the fail() helper enforces:
    - 'check' field (string)
    - 'error' field (string)
    - Optional 'debug' field (dict)
    - No 'message' field at top level
    """
    # Create a transaction
    request = {
        "prompt": "Test prompt",
        "environment": "dev",
        "client_id": "test-client",
        "feature_tag": "test",
        "model": "gpt-4",
        "temperature": 0.5
    }
    
    create_response = client.post("/v1/ai/call", json=request)
    assert create_response.status_code == 200
    transaction_id = create_response.json()["transaction_id"]
    
    # Tamper with both HALO and signature to get multiple failure types
    from gateway.app.services.storage import get_transaction
    from gateway.app.db.migrate import get_connection
    
    packet = get_transaction(transaction_id)
    
    # Tamper with policy_receipt (affects HALO)
    packet["policy_receipt"]["policy_change_ref"] = "TAMPERED"
    
    # Tamper with signature
    packet["verification"]["signature_b64"] = "dGFtcGVyZWQ="
    
    # Store tampered packet
    packet_json = json.dumps(packet, sort_keys=True)
    conn = get_connection()
    try:
        conn.execute("""
            UPDATE transactions
            SET packet_json = ?
            WHERE transaction_id = ?
        """, (packet_json, transaction_id))
        conn.commit()
    finally:
        conn.close()
    
    # Verify should detect both failures
    verify_response = client.post(f"/v1/transactions/{transaction_id}/verify")
    result = verify_response.json()
    
    assert result["valid"] is False
    assert len(result["failures"]) >= 2
    
    # Check each failure follows consistent schema
    for failure in result["failures"]:
        # MUST have 'check' and 'error'
        assert "check" in failure
        assert "error" in failure
        assert isinstance(failure["check"], str)
        assert isinstance(failure["error"], str)
        
        # MUST NOT have 'message' at top level (common schema drift)
        assert "message" not in failure
        
        # If 'debug' exists, it must be a dict
        if "debug" in failure:
            assert isinstance(failure["debug"], dict)
            
            # Debug should not contain 'message' key (prefixes only policy)
            assert "message" not in failure["debug"]


def test_hash_prefixes_are_limited_to_16_chars(client):
    """Test that hash prefixes in debug are exactly 16 characters.
    
    Verifies the hash leakage policy:
    - Hash prefixes should be 16 characters (not full hash)
    - Full hashes should never appear in verification responses
    """
    # Create a transaction
    request = {
        "prompt": "Test prompt",
        "environment": "dev",
        "client_id": "test-client",
        "feature_tag": "test",
        "model": "gpt-4",
        "temperature": 0.5
    }
    
    create_response = client.post("/v1/ai/call", json=request)
    assert create_response.status_code == 200
    transaction_id = create_response.json()["transaction_id"]
    
    # Get original packet to capture full hash
    from gateway.app.services.storage import get_transaction
    from gateway.app.db.migrate import get_connection
    
    packet = get_transaction(transaction_id)
    original_final_hash = packet["halo_chain"]["final_hash"]
    
    # Verify full hash has algorithm prefix (e.g., "sha256:") and is much longer than 16 chars
    assert len(original_final_hash) > 16, f"Hash should be longer than prefix (16 chars), got {len(original_final_hash)}"
    # Typical format: "sha256:64hexchars" = 71 chars total
    assert original_final_hash.startswith("sha256:"), f"Expected sha256: prefix, got {original_final_hash[:10]}..."
    
    # Tamper with packet field to cause hash mismatch
    packet["policy_receipt"]["policy_change_ref"] = "TAMPERED"
    
    packet_json = json.dumps(packet, sort_keys=True)
    conn = get_connection()
    try:
        conn.execute("""
            UPDATE transactions
            SET packet_json = ?
            WHERE transaction_id = ?
        """, (packet_json, transaction_id))
        conn.commit()
    finally:
        conn.close()
    
    # Verify should detect hash mismatch
    verify_response = client.post(f"/v1/transactions/{transaction_id}/verify")
    result = verify_response.json()
    
    halo_failures = [f for f in result["failures"] if f["check"] == "halo_chain"]
    assert len(halo_failures) > 0
    
    failure = halo_failures[0]
    assert "debug" in failure
    assert "stored_prefix" in failure["debug"]
    assert "recomputed_prefix" in failure["debug"]
    
    # CRITICAL: Prefixes must be exactly 16 characters
    assert len(failure["debug"]["stored_prefix"]) == 16
    assert len(failure["debug"]["recomputed_prefix"]) == 16
    
    # CRITICAL: Full hash must NOT appear anywhere in the response
    result_str = json.dumps(result)
    assert original_final_hash not in result_str


def test_verify_utils_fail_helper():
    """Test the fail() helper function directly.
    
    Ensures the helper produces consistent schema and handles edge cases.
    """
    from gateway.app.routes.verify_utils import fail
    
    # Basic failure (no debug)
    f1 = fail("signature", "invalid_signature")
    assert f1 == {"check": "signature", "error": "invalid_signature"}
    
    # Failure with debug
    f2 = fail("halo_chain", "final_hash_mismatch", {"stored_prefix": "abc", "recomputed_prefix": "def"})
    assert f2 == {
        "check": "halo_chain",
        "error": "final_hash_mismatch",
        "debug": {"stored_prefix": "abc", "recomputed_prefix": "def"}
    }
    
    # Failure with None debug (should not include debug key)
    f3 = fail("signature", "key_not_found", None)
    assert f3 == {"check": "signature", "error": "key_not_found"}
    assert "debug" not in f3
    
    # Failure with empty dict debug (treated as falsy, no debug key)
    f4 = fail("halo_chain", "error_code", {})
    assert f4 == {"check": "halo_chain", "error": "error_code"}
    assert "debug" not in f4
    
    # Edge case: empty strings (should still work, though not recommended)
    f5 = fail("", "")
    assert f5 == {"check": "", "error": ""}
    
    # Verify structure always contains check and error keys
    assert "check" in f1 and "error" in f1
    assert "check" in f2 and "error" in f2
    assert "check" in f3 and "error" in f3
