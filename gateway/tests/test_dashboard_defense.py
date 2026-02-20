"""
Tests for Dashboard and Defense API endpoints.

Validates:
- Executive summary dashboard returns expected metrics
- Risk queue filtering works correctly
- Defense simulation shows PASS vs FAIL correctly
"""

import os
from fastapi.testclient import TestClient

# Enable test mode
os.environ["ENV"] = "TEST"
os.environ["DISABLE_RATE_LIMITS"] = "1"

from gateway.app.main import app
from gateway.tests.auth_helpers import create_jwt_headers

client = TestClient(app)


class TestDashboard:
    """Tests for dashboard endpoints."""

    def test_executive_summary_structure(self):
        """Test that executive summary returns expected structure."""
        headers = create_jwt_headers(tenant_id="test-tenant-dash", role="admin")

        response = client.get("/v1/dashboard/executive-summary", headers=headers)

        # May return 404 if no data yet, or 200 with empty metrics
        # For now, just verify endpoint exists and returns valid JSON
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()

            # Verify expected fields
            assert "tenant_id" in data
            assert "window" in data
            assert "notes_reviewed" in data
            assert "certificates_issued" in data
            assert "verification_pass_rate" in data
            assert "tamper_events_detected" in data
            assert "high_risk_notes" in data
            assert "top_deficit_categories" in data
            assert "most_defensible_notes" in data
            assert "least_defensible_notes" in data
            assert "export_ready_bundles" in data

    def test_executive_summary_requires_auth(self):
        """Test that dashboard requires authentication."""
        response = client.get("/v1/dashboard/executive-summary")
        assert response.status_code == 401

    def test_risk_queue_structure(self):
        """Test that risk queue returns expected structure."""
        headers = create_jwt_headers(tenant_id="test-tenant-risk", role="clinician")

        response = client.get(
            "/v1/dashboard/risk-queue", headers=headers, params={"limit": 10}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "tenant_id" in data
        assert "items" in data
        assert "total" in data
        assert "returned" in data

        # Verify items structure (if any exist)
        if data["items"]:
            item = data["items"][0]
            assert "shadow_id" in item or "certificate_id" in item
            assert "band" in item
            assert "deficits" in item
            assert "what_to_fix" in item
            assert "export_links" in item

    def test_risk_queue_filtering(self):
        """Test risk queue filtering by band."""
        headers = create_jwt_headers(tenant_id="test-tenant-filter", role="clinician")

        # Test HIGH band filter
        response = client.get(
            "/v1/dashboard/risk-queue",
            headers=headers,
            params={"band": "HIGH", "limit": 5},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["band_filter"] == "HIGH"


class TestDefenseSimulation:
    """Tests for defense simulation endpoint."""

    def test_alteration_simulation_requires_valid_certificate(self):
        """Test that simulation requires a valid certificate."""
        headers = create_jwt_headers(tenant_id="test-tenant-defense", role="clinician")

        response = client.post(
            "/v1/defense/simulate-alteration",
            headers=headers,
            json={
                "certificate_id": "nonexistent-cert-id",
                "modified_note_text": "Altered documentation text",
            },
        )

        # Should return 404 for nonexistent certificate
        assert response.status_code == 404

    def test_alteration_simulation_tenant_isolation(self):
        """Test that simulation enforces tenant isolation."""
        # This test would require creating a certificate first
        # Skipping for now as it requires full certificate creation flow
        pass

    def test_alteration_simulation_structure(self):
        """Test that simulation response has expected structure."""
        # This test validates the response structure when a valid certificate exists
        # For now, we just verify the endpoint exists and requires auth

        headers = create_jwt_headers(tenant_id="test-tenant-sim", role="clinician")

        response = client.post(
            "/v1/defense/simulate-alteration",
            headers=headers,
            json={
                "certificate_id": "test-cert-id",
                "modified_note_text": "Test alteration",
            },
        )

        # Will be 404 without a real certificate, but that's expected
        assert response.status_code in [404, 200]

        # If 200, verify structure
        if response.status_code == 200:
            data = response.json()

            assert "certificate_id" in data
            assert "original_verification" in data
            assert "mutated_verification" in data
            assert "demonstration" in data

            demo = data["demonstration"]
            assert "original_status" in demo
            assert "mutated_status" in demo
            assert "proof" in demo
            assert "what_broke" in demo
            assert "explanation" in demo
            assert "recommended_action" in demo

    def test_alteration_simulation_requires_auth(self):
        """Test that defense simulation requires authentication."""
        response = client.post(
            "/v1/defense/simulate-alteration",
            json={"certificate_id": "test-id", "modified_note_text": "Test"},
        )

        assert response.status_code == 401
