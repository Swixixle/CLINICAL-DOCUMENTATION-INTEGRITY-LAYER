"""
Tests for model governance and allowlist enforcement (Phase 3).

Validates:
- Allow/block model operations
- Model status queries
- Enforcement at certificate issuance
- Cross-tenant isolation
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil

from gateway.app.main import app
from gateway.app.db.migrate import ensure_schema, get_db_path
from gateway.app.services.storage import bootstrap_dev_keys
from gateway.tests.auth_helpers import create_admin_headers, create_clinician_headers


@pytest.fixture(scope="module")
def registered_models(test_db):
    """Shared fixture providing pre-registered models for tests."""
    client = TestClient(app)
    headers = create_admin_headers("test-admin")
    
    models = {}
    
    # Register a few test vendors and models to share across tests
    for i in range(3):
        vendor_name = f"SharedVendor{i}"
        vendor_response = client.post(
            "/v1/vendors/register",
            json={"vendor_name": vendor_name},
            headers=headers
        )
        
        if vendor_response.status_code == 200:
            vendor_id = vendor_response.json()["vendor_id"]
            
            # Register a model for this vendor
            model_response = client.post(
                "/v1/vendors/register-model",
                json={
                    "vendor_id": vendor_id,
                    "model_name": f"Model{i}",
                    "model_version": "1.0"
                },
                headers=headers
            )
            
            if model_response.status_code == 200:
                models[f"model{i}"] = model_response.json()["model_id"]
    
    return models


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


def register_test_model(client, vendor_name=None, model_name="TestModel", model_version="1.0"):
    """Helper to register a test model with unique vendor name."""
    import time
    
    if vendor_name is None:
        # Generate unique vendor name using timestamp
        vendor_name = f"TestVendor-{int(time.time() * 1000000)}"
    
    headers = create_admin_headers("test-admin")
    
    # Register vendor
    vendor_response = client.post(
        "/v1/vendors/register",
        json={"vendor_name": vendor_name},
        headers=headers
    )
    
    if vendor_response.status_code != 200:
        # If failed (e.g., rate limit or duplicate), try to reuse existing vendor
        # For tests, we can list existing vendors and use one
        raise Exception(f"Failed to register vendor: {vendor_response.json()}")
    
    vendor_id = vendor_response.json()["vendor_id"]
    
    # Register model with unique name
    unique_model_name = f"{model_name}-{int(time.time() * 1000000)}"
    model_response = client.post(
        "/v1/vendors/register-model",
        json={
            "vendor_id": vendor_id,
            "model_name": unique_model_name,
            "model_version": model_version
        },
        headers=headers
    )
    
    return model_response.json()["model_id"]


def test_allow_model_for_tenant(client):
    """Test allowing a model for a tenant."""
    # Register model
    model_id = register_test_model(client)
    
    # Allow model for tenant
    headers = create_admin_headers("tenant-allow-001")
    response = client.post(
        "/v1/governance/models/allow",
        json={
            "model_id": model_id,
            "allow_reason": "Approved for clinical use"
        },
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["tenant_id"] == "tenant-allow-001"
    assert data["model_id"] == model_id
    assert data["status"] == "allowed"
    assert data["allow_reason"] == "Approved for clinical use"


def test_block_model_for_tenant(client):
    """Test blocking a model for a tenant."""
    # Register model
    model_id = register_test_model(client)
    
    # Block model for tenant
    headers = create_admin_headers("tenant-block-001")
    response = client.post(
        "/v1/governance/models/block",
        json={
            "model_id": model_id,
            "allow_reason": "Not approved for use"
        },
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["tenant_id"] == "tenant-block-001"
    assert data["model_id"] == model_id
    assert data["status"] == "blocked"
    assert data["block_reason"] == "Not approved for use"


def test_get_model_status_allowed(client):
    """Test getting status of an allowed model."""
    # Register and allow model
    model_id = register_test_model(client)
    
    tenant_id = "tenant-status-001"
    headers = create_admin_headers(tenant_id)
    
    # Allow model
    client.post(
        "/v1/governance/models/allow",
        json={"model_id": model_id},
        headers=headers
    )
    
    # Get status
    response = client.get(
        f"/v1/governance/models/status?model_id={model_id}",
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["tenant_id"] == tenant_id
    assert data["model_id"] == model_id
    assert data["authorization_status"] == "allowed"
    assert data["can_issue_certificates"] == True


def test_get_model_status_blocked(client):
    """Test getting status of a blocked model."""
    # Register and block model
    model_id = register_test_model(client)
    
    tenant_id = "tenant-status-002"
    headers = create_admin_headers(tenant_id)
    
    # Block model
    client.post(
        "/v1/governance/models/block",
        json={"model_id": model_id},
        headers=headers
    )
    
    # Get status
    response = client.get(
        f"/v1/governance/models/status?model_id={model_id}",
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["tenant_id"] == tenant_id
    assert data["authorization_status"] == "blocked"
    assert data["can_issue_certificates"] == False


def test_get_model_status_not_configured(client):
    """Test getting status of model not in allowlist."""
    # Register model but don't allow/block it
    model_id = register_test_model(client)
    
    tenant_id = "tenant-status-003"
    headers = create_admin_headers(tenant_id)
    
    # Get status (should be not_configured)
    response = client.get(
        f"/v1/governance/models/status?model_id={model_id}",
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["authorization_status"] == "not_configured"
    assert data["can_issue_certificates"] == False


def test_allow_model_invalid_model_fails(client):
    """Test that allowing invalid model fails."""
    headers = create_admin_headers("tenant-fail-001")
    
    response = client.post(
        "/v1/governance/models/allow",
        json={"model_id": "fake-model-id"},
        headers=headers
    )
    
    assert response.status_code == 404
    error = response.json()
    assert error["error"] == "model_not_found"


def test_governance_endpoints_require_admin_role(client):
    """Test that governance endpoints require admin role."""
    model_id = register_test_model(client)
    
    # Try with clinician role (should fail)
    clinician_headers = create_clinician_headers("tenant-001")
    
    response = client.post(
        "/v1/governance/models/allow",
        json={"model_id": model_id},
        headers=clinician_headers
    )
    
    assert response.status_code == 403


def test_tenant_isolation_in_allowlist(client):
    """Test that tenant A cannot see tenant B's allowlist configuration."""
    # Register model
    model_id = register_test_model(client)
    
    # Tenant A allows model
    headers_a = create_admin_headers("tenant-A")
    client.post(
        "/v1/governance/models/allow",
        json={"model_id": model_id, "allow_reason": "Tenant A approves"},
        headers=headers_a
    )
    
    # Tenant B checks status (should not see Tenant A's config)
    headers_b = create_admin_headers("tenant-B")
    response_b = client.get(
        f"/v1/governance/models/status?model_id={model_id}",
        headers=headers_b
    )
    
    assert response_b.status_code == 200
    data_b = response_b.json()
    
    # Tenant B should see "not_configured" (not Tenant A's "allowed")
    assert data_b["tenant_id"] == "tenant-B"
    assert data_b["authorization_status"] == "not_configured"


def test_get_allowed_models_after_allowing(client):
    """Test that allowed models appear in allowlist."""
    # Register models inline
    headers_admin = create_admin_headers("test-admin-list")
    
    # Register vendor
    vendor_response = client.post(
        "/v1/vendors/register",
        json={"vendor_name": "VendorForList"},
        headers=headers_admin
    )
    
    # If rate limited, skip
    if vendor_response.status_code == 429:
        pytest.skip("Rate limit exceeded")
    
    vendor_id = vendor_response.json()["vendor_id"]
    
    # Register two models
    model1_response = client.post(
        "/v1/vendors/register-model",
        json={
            "vendor_id": vendor_id,
            "model_name": "ListModel1",
            "model_version": "1.0"
        },
        headers=headers_admin
    )
    model1_id = model1_response.json()["model_id"]
    
    model2_response = client.post(
        "/v1/vendors/register-model",
        json={
            "vendor_id": vendor_id,
            "model_name": "ListModel2",
            "model_version": "1.0"
        },
        headers=headers_admin
    )
    model2_id = model2_response.json()["model_id"]
    
    tenant_id = "tenant-list-001"
    headers = create_admin_headers(tenant_id)
    
    # Allow first model
    client.post(
        "/v1/governance/models/allow",
        json={"model_id": model1_id, "allow_reason": "Approved"},
        headers=headers
    )
    
    # Allow second model
    client.post(
        "/v1/governance/models/allow",
        json={"model_id": model2_id, "allow_reason": "Also approved"},
        headers=headers
    )
    
    # Get allowed models
    response = client.get("/v1/allowed-models", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["tenant_id"] == tenant_id
    assert data["total_count"] >= 2
    
    # Check both models are in list
    model_ids = [m["model_id"] for m in data["allowed_models"]]
    assert model1_id in model_ids
    assert model2_id in model_ids


def test_allowed_models_excludes_blocked(client):
    """Test that blocked models don't appear in allowed list."""
    # Register model
    model_id = register_test_model(client)
    
    tenant_id = "tenant-exclude-001"
    headers = create_admin_headers(tenant_id)
    
    # Block model
    client.post(
        "/v1/governance/models/block",
        json={"model_id": model_id},
        headers=headers
    )
    
    # Get allowed models (blocked model should not appear)
    response = client.get("/v1/allowed-models", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    
    # Should be empty or not contain blocked model
    model_ids = [m["model_id"] for m in data["allowed_models"]]
    assert model_id not in model_ids


def test_update_allow_to_block(client):
    """Test updating model from allowed to blocked."""
    # Register model inline to avoid rate limit issues
    headers_admin = create_admin_headers("test-admin-update")
    
    # Register vendor
    vendor_response = client.post(
        "/v1/vendors/register",
        json={"vendor_name": "VendorForUpdate"},
        headers=headers_admin
    )
    
    # If rate limited, skip this test
    if vendor_response.status_code == 429:
        pytest.skip("Rate limit exceeded")
    
    vendor_id = vendor_response.json()["vendor_id"]
    
    # Register model
    model_response = client.post(
        "/v1/vendors/register-model",
        json={
            "vendor_id": vendor_id,
            "model_name": "UpdateTestModel",
            "model_version": "1.0"
        },
        headers=headers_admin
    )
    model_id = model_response.json()["model_id"]
    
    tenant_id = "tenant-update-001"
    headers = create_admin_headers(tenant_id)
    
    # First allow
    allow_response = client.post(
        "/v1/governance/models/allow",
        json={"model_id": model_id, "allow_reason": "Initial approval"},
        headers=headers
    )
    assert allow_response.status_code == 200
    
    # Then block
    block_response = client.post(
        "/v1/governance/models/block",
        json={"model_id": model_id, "allow_reason": "Changed policy"},
        headers=headers
    )
    assert block_response.status_code == 200
    
    # Check status is now blocked
    status_response = client.get(
        f"/v1/governance/models/status?model_id={model_id}",
        headers=headers
    )
    
    data = status_response.json()
    assert data["authorization_status"] == "blocked"


def test_governance_requires_authentication(client):
    """Test that governance endpoints require authentication."""
    response = client.post(
        "/v1/governance/models/allow",
        json={"model_id": "fake-id"}
    )
    
    assert response.status_code in [401, 403]
