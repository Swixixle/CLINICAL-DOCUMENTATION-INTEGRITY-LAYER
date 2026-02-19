"""
Tests for Shadow Mode Intake API endpoints.

Validates:
- Shadow intake creates records with no PHI leakage
- Per-tenant isolation (cross-tenant returns 404)
- PHI-safe storage (hashes only by default)
"""

import os
import pytest
from fastapi.testclient import TestClient

# Enable test mode to disable rate limiting
os.environ["ENV"] = "TEST"
os.environ["DISABLE_RATE_LIMITS"] = "1"

from gateway.app.main import app
from gateway.tests.auth_helpers import create_jwt_headers

client = TestClient(app)


class TestShadowIntake:
    """Tests for shadow intake endpoints."""
    
    def test_shadow_intake_creates_record(self):
        """Test that shadow intake creates a record with hash."""
        note_text = "Patient presents with chest pain. Vital signs stable. ECG shows normal sinus rhythm."
        
        headers = create_jwt_headers(tenant_id="test-hospital-1", role="clinician")
        
        response = client.post(
            "/v1/shadow/intake",
            headers=headers,
            json={
                "note_text": note_text,
                "encounter_id": "ENC-123",
                "note_type": "progress"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response has expected fields
        assert "shadow_id" in data
        assert "note_hash" in data
        assert "timestamp" in data
        assert "tenant_id" in data
        assert data["tenant_id"] == "test-hospital-1"
        assert data["status"] == "ingested"
        
        # Verify note_hash is not the plaintext
        assert data["note_hash"] != note_text
        
        # Verify hash is SHA-256 (64 hex chars)
        assert len(data["note_hash"]) == 64
    
    def test_shadow_intake_no_phi_leakage_by_default(self):
        """Test that note text is NOT stored by default (PHI safety)."""
        note_text = "Patient John Doe, SSN 123-45-6789, has diabetes. Phone: 555-1234."
        
        headers = create_jwt_headers(tenant_id="test-hospital-2", role="clinician")
        
        response = client.post(
            "/v1/shadow/intake",
            headers=headers,
            json={
                "note_text": note_text,
                "patient_reference": "PATIENT-456"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        shadow_id = data["shadow_id"]
        
        # Try to retrieve the shadow item
        get_response = client.get(
            f"/v1/shadow/items/{shadow_id}",
            headers=headers
        )
        
        assert get_response.status_code == 200
        item = get_response.json()
        
        # Verify note_text is NOT in response (PHI safety)
        assert "note_text" not in item or item.get("note_text") is None
        
        # Verify only hash is present
        assert "note_hash" in item
        assert item["note_hash"] != note_text
    
    def test_shadow_intake_tenant_isolation(self):
        """Test that cross-tenant access returns 404."""
        # Create shadow item as tenant-1
        headers_t1 = create_jwt_headers(tenant_id="tenant-1", role="clinician")
        
        response = client.post(
            "/v1/shadow/intake",
            headers=headers_t1,
            json={
                "note_text": "Tenant 1 note text"
            }
        )
        
        assert response.status_code == 200
        shadow_id = response.json()["shadow_id"]
        
        # Try to access as tenant-2
        headers_t2 = create_jwt_headers(tenant_id="tenant-2", role="clinician")
        
        get_response = client.get(
            f"/v1/shadow/items/{shadow_id}",
            headers=headers_t2
        )
        
        # Should return 404 (not found) due to tenant isolation
        assert get_response.status_code == 404
    
    def test_shadow_intake_validates_minimum_note_length(self):
        """Test that very short notes are rejected."""
        headers = create_jwt_headers(tenant_id="test-hospital-3", role="clinician")
        
        response = client.post(
            "/v1/shadow/intake",
            headers=headers,
            json={
                "note_text": "Short"  # Less than 10 characters
            }
        )
        
        # Should reject notes < 10 characters
        assert response.status_code == 400
    
    def test_shadow_intake_list_items(self):
        """Test listing shadow items with filters."""
        headers = create_jwt_headers(tenant_id="test-hospital-4", role="clinician")
        
        # Create multiple items
        for i in range(3):
            client.post(
                "/v1/shadow/intake",
                headers=headers,
                json={
                    "note_text": f"Test note {i} with sufficient length"
                }
            )
        
        # List items
        response = client.get(
            "/v1/shadow/items",
            headers=headers,
            params={"page": 1, "page_size": 10}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        
        # Verify we have at least the items we created
        assert data["total"] >= 3
        assert len(data["items"]) >= 3
        
        # Verify tenant isolation
        for item in data["items"]:
            assert item["tenant_id"] == "test-hospital-4"
    
    def test_shadow_intake_requires_authentication(self):
        """Test that shadow intake requires JWT authentication."""
        response = client.post(
            "/v1/shadow/intake",
            json={
                "note_text": "Test note without authentication"
            }
        )
        
        # Should return 401 Unauthorized
        assert response.status_code == 401
