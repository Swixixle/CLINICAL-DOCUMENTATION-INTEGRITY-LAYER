"""
Tests for vendor registry and model management (Phase 2).

Validates:
- Vendor registration
- Model registration
- Key rotation
- Model listing
- Admin role enforcement
"""

import pytest
import json
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil

from gateway.app.main import app
from gateway.app.db.migrate import ensure_schema, get_db_path
from gateway.app.services.storage import bootstrap_dev_keys
from gateway.tests.auth_helpers import create_admin_headers, create_clinician_headers


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database."""
    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "test.db"
    
    import gateway.app.db.migrate as migrate_module
    original_get_db_path = migrate_module.get_db_path
    migrate_module.get_db_path = lambda: temp_db_path
    
    ensure_schema()
    bootstrap_dev_keys()
    
    yield temp_db_path
    
    migrate_module.get_db_path = original_get_db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def client(test_db):
    """Test client with test database."""
    return TestClient(app)


def test_register_vendor(client):
    """Test registering a new AI vendor."""
    headers = create_admin_headers("admin-tenant-001")
    
    response = client.post(
        "/v1/vendors/register",
        json={"vendor_name": "OpenAI"},
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "vendor_id" in data
    assert data["vendor_name"] == "OpenAI"
    assert data["status"] == "active"
    assert "created_at" in data


def test_register_duplicate_vendor_fails(client):
    """Test that registering duplicate vendor fails."""
    headers = create_admin_headers("admin-tenant-002")
    
    # Register first vendor
    response1 = client.post(
        "/v1/vendors/register",
        json={"vendor_name": "Anthropic"},
        headers=headers
    )
    assert response1.status_code == 200
    
    # Try to register same vendor again
    response2 = client.post(
        "/v1/vendors/register",
        json={"vendor_name": "Anthropic"},
        headers=headers
    )
    
    assert response2.status_code == 400
    error = response2.json()
    assert error["error"] == "vendor_already_exists"


def test_register_model(client):
    """Test registering an AI model."""
    headers = create_admin_headers("admin-tenant-003")
    
    # First register vendor
    vendor_response = client.post(
        "/v1/vendors/register",
        json={"vendor_name": "OpenAI"},
        headers=headers
    )
    vendor_id = vendor_response.json()["vendor_id"]
    
    # Register model
    model_response = client.post(
        "/v1/vendors/register-model",
        json={
            "vendor_id": vendor_id,
            "model_name": "GPT-4-Turbo",
            "model_version": "2024-11",
            "metadata": {"max_tokens": 128000}
        },
        headers=headers
    )
    
    assert model_response.status_code == 200
    data = model_response.json()
    
    assert "model_id" in data
    assert data["vendor_id"] == vendor_id
    assert data["model_name"] == "GPT-4-Turbo"
    assert data["model_version"] == "2024-11"
    assert data["status"] == "active"


def test_register_model_with_public_key(client):
    """Test registering model with vendor public key."""
    headers = create_admin_headers("admin-tenant-004")
    
    # Register vendor
    vendor_response = client.post(
        "/v1/vendors/register",
        json={"vendor_name": "Anthropic"},
        headers=headers
    )
    vendor_id = vendor_response.json()["vendor_id"]
    
    # Register model with public key
    public_jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": "WKn-ZIGevcwGIyyrzFoZNBdaq9_TsqzGl96oc0CWuis",
        "y": "y77t-RvAHRKTsSGdIYUfweuOvwrvDD-Q3Hv5J0fSKbE"
    }
    
    model_response = client.post(
        "/v1/vendors/register-model",
        json={
            "vendor_id": vendor_id,
            "model_name": "Claude-3",
            "model_version": "opus-20240229",
            "public_jwk": public_jwk
        },
        headers=headers
    )
    
    assert model_response.status_code == 200
    data = model_response.json()
    
    assert "key_id" in data
    assert data["key_id"] is not None


def test_register_model_invalid_vendor_fails(client):
    """Test that registering model with invalid vendor fails."""
    headers = create_admin_headers("admin-tenant-005")
    
    response = client.post(
        "/v1/vendors/register-model",
        json={
            "vendor_id": "fake-vendor-id",
            "model_name": "Test-Model",
            "model_version": "1.0"
        },
        headers=headers
    )
    
    assert response.status_code == 400
    error = response.json()
    assert error["error"] == "vendor_not_found"


def test_rotate_model_key(client):
    """Test rotating a model's public key."""
    headers = create_admin_headers("admin-tenant-006")
    
    # Register vendor and model
    vendor_response = client.post(
        "/v1/vendors/register",
        json={"vendor_name": "Google"},
        headers=headers
    )
    vendor_id = vendor_response.json()["vendor_id"]
    
    # Register model with initial key
    old_jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": "old-x-coordinate",
        "y": "old-y-coordinate"
    }
    
    model_response = client.post(
        "/v1/vendors/register-model",
        json={
            "vendor_id": vendor_id,
            "model_name": "Gemini",
            "model_version": "1.5",
            "public_jwk": old_jwk
        },
        headers=headers
    )
    model_id = model_response.json()["model_id"]
    
    # Rotate key
    new_jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": "new-x-coordinate",
        "y": "new-y-coordinate"
    }
    
    rotation_response = client.post(
        "/v1/vendors/rotate-model-key",
        json={
            "model_id": model_id,
            "new_public_jwk": new_jwk
        },
        headers=headers
    )
    
    assert rotation_response.status_code == 200
    data = rotation_response.json()
    
    assert data["model_id"] == model_id
    assert "new_key_id" in data
    assert "rotated_at" in data


def test_list_models(client):
    """Test listing all models."""
    headers = create_admin_headers("admin-tenant-007")
    
    # Register vendor and multiple models
    vendor_response = client.post(
        "/v1/vendors/register",
        json={"vendor_name": "TestVendor"},
        headers=headers
    )
    vendor_id = vendor_response.json()["vendor_id"]
    
    # Register first model
    client.post(
        "/v1/vendors/register-model",
        json={
            "vendor_id": vendor_id,
            "model_name": "Model-A",
            "model_version": "1.0"
        },
        headers=headers
    )
    
    # Register second model
    client.post(
        "/v1/vendors/register-model",
        json={
            "vendor_id": vendor_id,
            "model_name": "Model-B",
            "model_version": "2.0"
        },
        headers=headers
    )
    
    # List models
    list_response = client.get("/v1/vendors/models", headers=headers)
    
    assert list_response.status_code == 200
    data = list_response.json()
    
    assert "models" in data
    assert data["total_count"] >= 2
    assert len(data["models"]) >= 2


def test_list_models_filtered_by_vendor(client):
    """Test listing models filtered by vendor."""
    headers = create_admin_headers("admin-tenant-008")
    
    # Register two vendors
    vendor1_response = client.post(
        "/v1/vendors/register",
        json={"vendor_name": "Vendor1"},
        headers=headers
    )
    vendor1_id = vendor1_response.json()["vendor_id"]
    
    vendor2_response = client.post(
        "/v1/vendors/register",
        json={"vendor_name": "Vendor2"},
        headers=headers
    )
    vendor2_id = vendor2_response.json()["vendor_id"]
    
    # Register models for each vendor
    client.post(
        "/v1/vendors/register-model",
        json={
            "vendor_id": vendor1_id,
            "model_name": "Vendor1-Model",
            "model_version": "1.0"
        },
        headers=headers
    )
    
    client.post(
        "/v1/vendors/register-model",
        json={
            "vendor_id": vendor2_id,
            "model_name": "Vendor2-Model",
            "model_version": "1.0"
        },
        headers=headers
    )
    
    # List models for vendor1 only
    list_response = client.get(
        f"/v1/vendors/models?vendor_id={vendor1_id}",
        headers=headers
    )
    
    assert list_response.status_code == 200
    data = list_response.json()
    
    # Should only return vendor1's models
    for model in data["models"]:
        assert model["vendor_id"] == vendor1_id


def test_vendor_endpoints_require_admin_role(client):
    """Test that vendor endpoints require admin role."""
    # Try with clinician role (should fail)
    clinician_headers = create_clinician_headers("tenant-001")
    
    # Try to register vendor
    response = client.post(
        "/v1/vendors/register",
        json={"vendor_name": "TestVendor"},
        headers=clinician_headers
    )
    
    assert response.status_code == 403  # Forbidden


def test_vendor_endpoints_require_authentication(client):
    """Test that vendor endpoints require authentication."""
    # Try without auth header
    response = client.post(
        "/v1/vendors/register",
        json={"vendor_name": "TestVendor"}
    )
    
    assert response.status_code in [401, 403]


def test_get_allowed_models_empty_initially(client):
    """Test that allowed models list is empty initially."""
    headers = create_admin_headers("tenant-allowed-001")
    
    response = client.get("/v1/allowed-models", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["tenant_id"] == "tenant-allowed-001"
    assert data["total_count"] == 0
    assert data["allowed_models"] == []
