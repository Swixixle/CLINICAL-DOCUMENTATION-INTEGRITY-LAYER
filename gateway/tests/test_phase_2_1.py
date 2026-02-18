"""
Phase 2.1 hardening patch tests.

Tests for:
- Denied execution with denial_reason
- Network access policy enforcement
- Tool permissions allowlist
- Verification tampering detection
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


def test_denied_execution_includes_denial_reason(client):
    """Test that denied transactions include denial_reason field."""
    request = {
        "prompt": "Test prompt",
        "environment": "prod",
        "client_id": "test-client",
        "feature_tag": "billing",
        "model": "gpt-4",
        "temperature": 0.7  # Wrong temperature for billing - will be denied
    }
    
    response = client.post("/v1/ai/call", json=request)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "denied"
    
    # Retrieve the transaction to check the packet
    transaction_id = data["transaction_id"]
    packet_response = client.get(f"/v1/transactions/{transaction_id}")
    assert packet_response.status_code == 200
    
    packet = packet_response.json()
    
    # Check execution fields
    assert packet["execution"]["outcome"] == "denied"
    assert "denial_reason" in packet["execution"]
    assert packet["execution"]["denial_reason"] is not None
    assert len(packet["execution"]["denial_reason"]) > 0
    
    # Check policy_receipt has decision
    assert packet["policy_receipt"]["decision"] == "denied"
    
    # Ensure HALO and signature are still present (denied transactions are signed)
    assert "halo_chain" in packet
    assert "verification" in packet
    assert packet["verification"]["signature_b64"] is not None


def test_network_access_denied_in_prod_for_billing(client):
    """Test that network_access=True is denied for billing in prod."""
    request = {
        "prompt": "Calculate billing",
        "environment": "prod",
        "client_id": "test-client",
        "feature_tag": "billing",
        "model": "gpt-4",
        "temperature": 0.0,  # Correct temperature
        "network_access": True  # Should be denied
    }
    
    response = client.post("/v1/ai/call", json=request)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "denied"
    
    # Check the packet for denial_reason mentioning network access
    transaction_id = data["transaction_id"]
    packet_response = client.get(f"/v1/transactions/{transaction_id}")
    packet = packet_response.json()
    
    assert "network" in packet["execution"]["denial_reason"].lower()


def test_network_access_allowed_for_non_billing(client):
    """Test that network_access=True is allowed for non-billing features."""
    request = {
        "prompt": "Search the web",
        "environment": "prod",
        "client_id": "test-client",
        "feature_tag": "customer-support",
        "model": "gpt-4",
        "temperature": 0.7,
        "network_access": True  # Should be allowed for non-billing
    }
    
    response = client.post("/v1/ai/call", json=request)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "completed"


def test_forbidden_tool_denied(client):
    """Test that forbidden tools are denied."""
    request = {
        "prompt": "Use a forbidden tool",
        "environment": "prod",
        "client_id": "test-client",
        "feature_tag": "general",
        "model": "gpt-4",
        "temperature": 0.7,
        "tool_permissions": ["web_search", "forbidden_tool"]  # forbidden_tool not in allowlist
    }
    
    response = client.post("/v1/ai/call", json=request)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "denied"
    
    # Check denial reason mentions forbidden tool
    transaction_id = data["transaction_id"]
    packet_response = client.get(f"/v1/transactions/{transaction_id}")
    packet = packet_response.json()
    
    assert "forbidden_tool" in packet["execution"]["denial_reason"]


def test_allowed_tools_approved(client):
    """Test that allowed tools are approved."""
    request = {
        "prompt": "Use allowed tools",
        "environment": "prod",
        "client_id": "test-client",
        "feature_tag": "general",
        "model": "gpt-4",
        "temperature": 0.7,
        "tool_permissions": ["web_search", "calculator"]  # Both in allowlist
    }
    
    response = client.post("/v1/ai/call", json=request)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "completed"


def test_verify_detects_packet_field_tampering(client):
    """Test that verification detects packet field tampering.
    
    policy_receipt feeds into HALO block 4; tampering must fail.
    
    This test proves the stronger claim: if you tamper with ANY packet field
    that feeds into HALO computation (e.g., policy_receipt), verification fails
    because the recomputed HALO final_hash won't match the stored commitment.
    
    This is the "court-ready" tamper test that proves tampering with committed
    fields is detected, not just tampering with the HALO artifact itself.
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
    
    # Get the transaction and tamper with a packet field that feeds HALO
    from gateway.app.services.storage import get_transaction
    from gateway.app.db.migrate import get_connection
    import json as json_lib
    
    packet = get_transaction(transaction_id)
    
    # Store original values for verification
    original_policy_change_ref = packet["policy_receipt"]["policy_change_ref"]
    original_halo_final_hash = packet["halo_chain"]["final_hash"]
    
    # Tamper with policy_receipt field that feeds into HALO Block 4
    # DO NOT touch halo_chain - that's the point of this test
    packet["policy_receipt"]["policy_change_ref"] = "TAMPERED-PCR"
    
    # Ensure halo_chain was NOT modified
    assert packet["halo_chain"]["final_hash"] == original_halo_final_hash
    
    # Store the tampered packet directly in DB
    packet_json = json_lib.dumps(packet, sort_keys=True)
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
    
    # Verify should detect tampering because:
    # - Recomputed HALO uses tampered policy_change_ref -> different final_hash
    # - Stored HALO still has original final_hash
    # - Comparison fails: recomputed != stored
    verify_response = client.post(f"/v1/transactions/{transaction_id}/verify")
    assert verify_response.status_code == 200
    
    result = verify_response.json()
    assert result["valid"] is False
    assert "failures" in result
    assert len(result["failures"]) > 0
    
    # Should have a halo_chain failure with final_hash_mismatch
    halo_failures = [f for f in result["failures"] if f["check"] == "halo_chain"]
    assert len(halo_failures) > 0
    assert halo_failures[0]["error"] == "final_hash_mismatch"
    # Verify debug field includes hash prefixes (not full hashes for security)
    assert "debug" in halo_failures[0]
    assert "stored_prefix" in halo_failures[0]["debug"]
    assert "recomputed_prefix" in halo_failures[0]["debug"]


def test_verify_detects_signature_tampering(client):
    """Test that verification detects signature tampering."""
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
    
    # Get the transaction and tamper with signature
    from gateway.app.services.storage import get_transaction
    from gateway.app.db.migrate import get_connection
    import json as json_lib
    
    packet = get_transaction(transaction_id)
    
    # Tamper with signature
    original_sig = packet["verification"]["signature_b64"]
    packet["verification"]["signature_b64"] = "dGFtcGVyZWRfc2lnbmF0dXJl"  # "tampered_signature" in base64
    
    # Store the tampered packet directly in DB
    packet_json = json_lib.dumps(packet, sort_keys=True)
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
    
    # Verify should detect tampering
    verify_response = client.post(f"/v1/transactions/{transaction_id}/verify")
    assert verify_response.status_code == 200
    
    result = verify_response.json()
    assert result["valid"] is False
    assert "failures" in result
    assert len(result["failures"]) > 0
    
    # Should have a signature failure
    sig_failures = [f for f in result["failures"] if f["check"] == "signature"]
    assert len(sig_failures) > 0


def test_environment_values_are_consistent(client):
    """Test that environment values are stored consistently as prod/staging/dev."""
    for env in ["prod", "staging", "dev"]:
        request = {
            "prompt": f"Test {env}",
            "environment": env,
            "client_id": "test-client",
            "feature_tag": "test",
            "model": "gpt-4",
            "temperature": 0.5
        }
        
        response = client.post("/v1/ai/call", json=request)
        assert response.status_code == 200
        
        transaction_id = response.json()["transaction_id"]
        packet_response = client.get(f"/v1/transactions/{transaction_id}")
        packet = packet_response.json()
        
        # Verify environment is stored exactly as provided
        assert packet["environment"] == env


def test_key_endpoint_returns_jwk_only(client):
    """Test that /v1/keys/{key_id} returns only the JWK object."""
    response = client.get("/v1/keys/dev-key-01")
    assert response.status_code == 200
    
    jwk = response.json()
    
    # Should be a JWK object, not wrapped in {key_id, jwk, status}
    assert "kty" in jwk  # JWK should have key type
    assert "key_id" not in jwk  # Should not have wrapper fields
    assert "status" not in jwk


def test_keys_list_endpoint_returns_metadata(client):
    """Test that /v1/keys returns list with key_id, jwk, and status."""
    response = client.get("/v1/keys")
    assert response.status_code == 200
    
    keys = response.json()
    assert isinstance(keys, list)
    assert len(keys) >= 1
    
    # Check structure of returned keys
    dev_key = next((k for k in keys if k["key_id"] == "dev-key-01"), None)
    assert dev_key is not None
    assert "key_id" in dev_key
    assert "jwk" in dev_key
    assert "status" in dev_key
    assert dev_key["status"] == "active"
