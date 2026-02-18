"""
Smoke tests for Clinical Documentation Integrity Layer (CDIL) API.

Tests the complete end-to-end flow:
- Health check
- AI call (approved and denied paths)
- Transaction retrieval
- Transaction verification
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


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Clinical Documentation Integrity Layer (CDIL)"
    assert data["status"] == "operational"


def test_list_keys(client):
    """Test listing public keys."""
    response = client.get("/v1/keys")
    assert response.status_code == 200
    keys = response.json()
    assert isinstance(keys, list)
    assert len(keys) >= 1
    
    # Check dev key is present
    dev_key = next((k for k in keys if k["key_id"] == "dev-key-01"), None)
    assert dev_key is not None
    assert dev_key["status"] == "active"
    assert "jwk" in dev_key


def test_get_key_by_id(client):
    """Test getting a specific key."""
    response = client.get("/v1/keys/dev-key-01")
    assert response.status_code == 200
    jwk = response.json()
    # Should return only JWK object, not wrapped
    assert "kty" in jwk  # JWK should have key type
    assert "x" in jwk  # EC public key should have x coordinate


def test_get_key_not_found(client):
    """Test getting a non-existent key."""
    response = client.get("/v1/keys/nonexistent")
    assert response.status_code == 404


def test_ai_call_approved(client):
    """Test approved AI call flow."""
    request = {
        "prompt": "What is the capital of France?",
        "environment": "prod",
        "client_id": "test-client-01",
        "feature_tag": "customer-support",
        "user_ref": "user-123",
        "intent_manifest": "text-generation",
        "model_request": {
            "provider": "openai",
            "model": "gpt-4",
            "temperature": 0.7,
            "max_tokens": 1000
        }
    }
    
    response = client.post("/v1/ai/call", json=request)
    assert response.status_code == 200
    
    data = response.json()
    assert "transaction_id" in data
    assert data["status"] == "completed"
    assert data["output"] is not None
    assert "accountability" in data
    
    accountability = data["accountability"]
    assert "policy_version_hash" in accountability
    assert "policy_change_ref" in accountability
    assert "final_hash" in accountability
    assert accountability["signed"] is True


def test_ai_call_denied_temperature(client):
    """Test denied AI call due to temperature constraint."""
    request = {
        "prompt": "Calculate total: $100",
        "environment": "prod",
        "client_id": "test-client-02",
        "feature_tag": "billing",  # billing requires temp=0.0
        "user_ref": "user-456",
        "intent_manifest": "text-generation",
        "model_request": {
            "provider": "openai",
            "model": "gpt-4",
            "temperature": 0.7,  # Wrong temperature for billing
            "max_tokens": 1000
        }
    }
    
    response = client.post("/v1/ai/call", json=request)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "denied"
    assert data["output"] is None  # No output for denied requests


def test_ai_call_denied_model(client):
    """Test denied AI call due to model not in allowlist."""
    request = {
        "prompt": "Hello world",
        "environment": "prod",
        "client_id": "test-client-03",
        "feature_tag": "general",
        "intent_manifest": "text-generation",
        "model_request": {
            "provider": "openai",
            "model": "gpt-5-turbo",  # Not in allowlist
            "temperature": 0.7,
            "max_tokens": 1000
        }
    }
    
    response = client.post("/v1/ai/call", json=request)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "denied"


def test_get_transaction(client):
    """Test retrieving a transaction."""
    # First create a transaction
    request = {
        "prompt": "Test prompt",
        "environment": "dev",
        "client_id": "test-client-04",
        "feature_tag": "test",
        "intent_manifest": "text-generation",
        "model_request": {
            "provider": "openai",
            "model": "gpt-4",
            "temperature": 0.5,
            "max_tokens": 1000
        }
    }
    
    create_response = client.post("/v1/ai/call", json=request)
    assert create_response.status_code == 200
    transaction_id = create_response.json()["transaction_id"]
    
    # Retrieve the transaction
    get_response = client.get(f"/v1/transactions/{transaction_id}")
    assert get_response.status_code == 200
    
    packet = get_response.json()
    assert packet["transaction_id"] == transaction_id
    assert "halo_chain" in packet
    assert "verification" in packet
    assert "policy_receipt" in packet


def test_get_transaction_not_found(client):
    """Test retrieving a non-existent transaction."""
    response = client.get("/v1/transactions/nonexistent-id")
    assert response.status_code == 404


def test_verify_transaction_valid(client):
    """Test verifying a valid transaction."""
    # First create a transaction
    request = {
        "prompt": "Verify this",
        "environment": "dev",
        "client_id": "test-client-05",
        "feature_tag": "test",
        "intent_manifest": "text-generation",
        "model_request": {
            "provider": "openai",
            "model": "gpt-4",
            "temperature": 0.0,
            "max_tokens": 1000
        }
    }
    
    create_response = client.post("/v1/ai/call", json=request)
    assert create_response.status_code == 200
    transaction_id = create_response.json()["transaction_id"]
    
    # Verify the transaction
    verify_response = client.post(f"/v1/transactions/{transaction_id}/verify")
    assert verify_response.status_code == 200
    
    result = verify_response.json()
    assert result["valid"] is True
    assert result["failures"] == []


def test_verify_transaction_not_found(client):
    """Test verifying a non-existent transaction."""
    response = client.post("/v1/transactions/nonexistent-id/verify")
    assert response.status_code == 404


def test_end_to_end_flow(client):
    """
    Test complete end-to-end flow:
    1. Call AI endpoint
    2. Retrieve transaction
    3. Verify transaction
    4. Validate packet structure
    """
    # Step 1: Create transaction
    request = {
        "prompt": "End-to-end test prompt",
        "environment": "prod",
        "client_id": "e2e-client",
        "feature_tag": "testing",
        "user_ref": "e2e-user",
        "intent_manifest": "text-generation",
        "model_request": {
            "provider": "openai",
            "model": "gpt-4",
            "temperature": 0.8,
            "max_tokens": 1000
        },
        "rag_context": {"doc1": "context data"}
    }
    
    call_response = client.post("/v1/ai/call", json=request)
    assert call_response.status_code == 200
    
    call_data = call_response.json()
    transaction_id = call_data["transaction_id"]
    assert call_data["status"] == "completed"
    
    # Step 2: Retrieve transaction
    get_response = client.get(f"/v1/transactions/{transaction_id}")
    assert get_response.status_code == 200
    
    packet = get_response.json()
    
    # Step 3: Validate packet structure
    # Top-level fields
    assert packet["transaction_id"] == transaction_id
    assert packet["client_id"] == "e2e-client"
    assert packet["environment"] == "prod"
    assert packet["feature_tag"] == "testing"
    assert packet["model_fingerprint"] == "gpt-4"
    
    # Policy receipt
    assert "policy_receipt" in packet
    assert "policy_version_hash" in packet["policy_receipt"]
    assert "policy_change_ref" in packet["policy_receipt"]
    assert "rules_applied" in packet["policy_receipt"]
    
    # Execution
    assert "execution" in packet
    assert packet["execution"]["outcome"] == "approved"
    assert "output_hash" in packet["execution"]
    
    # HALO chain
    assert "halo_chain" in packet
    assert packet["halo_chain"]["halo_version"] == "v1"
    assert len(packet["halo_chain"]["blocks"]) == 5
    assert "final_hash" in packet["halo_chain"]
    
    # Verification
    assert "verification" in packet
    assert packet["verification"]["alg"] == "ECDSA_SHA_256"
    assert packet["verification"]["key_id"] == "dev-key-01"
    assert "signature_b64" in packet["verification"]
    
    # Protocol metadata
    assert "protocol_metadata" in packet
    assert packet["protocol_metadata"]["halo_version"] == "v1"
    assert packet["protocol_metadata"]["c14n_version"] == "json_c14n_v1"
    
    # Step 4: Verify transaction
    verify_response = client.post(f"/v1/transactions/{transaction_id}/verify")
    assert verify_response.status_code == 200
    
    verify_result = verify_response.json()
    assert verify_result["valid"] is True
    assert verify_result["failures"] == []


def test_billing_feature_approved_with_correct_temp(client):
    """Test that billing feature works with temperature=0.0."""
    request = {
        "prompt": "Calculate billing total",
        "environment": "prod",
        "client_id": "billing-client",
        "feature_tag": "billing",
        "intent_manifest": "text-generation",
        "model_request": {
            "provider": "openai",
            "model": "gpt-4",
            "temperature": 0.0,  # Correct temperature for billing
            "max_tokens": 1000
        }
    }
    
    response = client.post("/v1/ai/call", json=request)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "completed"
    assert data["output"] is not None


def test_tamper_detection_policy_change_ref(client):
    """
    Test that tampering with policy_change_ref packet field is detected.
    
    This test verifies that modifying a packet field that feeds into HALO
    results in a verification failure because recomputed HALO won't match.
    """
    # Step 1: Create a valid transaction
    request = {
        "prompt": "Test tamper detection",
        "environment": "dev",
        "client_id": "tamper-test-client",
        "feature_tag": "test",
        "intent_manifest": "text-generation",
        "model_request": {
            "provider": "openai",
            "model": "gpt-4",
            "temperature": 0.5,
            "max_tokens": 1000
        }
    }
    
    create_response = client.post("/v1/ai/call", json=request)
    assert create_response.status_code == 200
    transaction_id = create_response.json()["transaction_id"]
    
    # Step 2: Retrieve the stored packet
    get_response = client.get(f"/v1/transactions/{transaction_id}")
    assert get_response.status_code == 200
    packet = get_response.json()
    
    # Step 3: Tamper with policy_change_ref PACKET FIELD (not HALO block)
    # This is what matters - tampering with the committed data that feeds into HALO
    packet["policy_receipt"]["policy_change_ref"] = "TAMPERED-PCR"
    
    # Step 4: Write the tampered packet back to the database
    from gateway.app.services.storage import update_transaction
    update_transaction(transaction_id, packet)
    
    # Step 5: Verify the transaction - should fail
    verify_response = client.post(f"/v1/transactions/{transaction_id}/verify")
    assert verify_response.status_code == 200
    
    result = verify_response.json()
    assert result["valid"] is False
    assert len(result["failures"]) > 0
    
    # Check that at least one failure is related to halo_chain
    halo_failures = [f for f in result["failures"] if f["check"] == "halo_chain"]
    assert len(halo_failures) > 0
    
    # Verify the failure uses consistent error schema with "error" key
    assert "error" in halo_failures[0]
    assert halo_failures[0]["error"] == "final_hash_mismatch"
