"""
Tests for ROI projection endpoint and calculations.

These tests validate the /v2/analytics/roi-projection endpoint
and the underlying ROI calculation logic.
"""

import pytest
from fastapi.testclient import TestClient

from gateway.app.main import app
from gateway.app.services.roi import calculate_roi, RoiInputs


# Test client without database (analytics endpoints are stateless)
@pytest.fixture
def client():
    """Test client for analytics endpoints (no database needed)."""
    return TestClient(app)


# Test data fixtures
@pytest.fixture
def conservative_inputs():
    """Conservative ROI scenario inputs (5% / 5%)."""
    return {
        "annual_revenue": 500_000_000.0,
        "denial_rate": 0.08,
        "documentation_denial_ratio": 0.40,
        "appeal_recovery_rate": 0.25,
        "denial_prevention_rate": 0.05,
        "appeal_success_lift": 0.05,
        "cost_per_appeal": 150.0,
        "annual_claim_volume": 200_000,
        "cdil_annual_cost": 250_000.0
    }


@pytest.fixture
def moderate_inputs():
    """Moderate ROI scenario inputs (10% / 10%)."""
    return {
        "annual_revenue": 500_000_000.0,
        "denial_rate": 0.08,
        "documentation_denial_ratio": 0.40,
        "appeal_recovery_rate": 0.25,
        "denial_prevention_rate": 0.10,
        "appeal_success_lift": 0.10,
        "cost_per_appeal": 150.0,
        "annual_claim_volume": 200_000,
        "cdil_annual_cost": 250_000.0
    }


# ============================================================================
# Happy Path Tests
# ============================================================================

def test_roi_projection_happy_path_conservative(client, conservative_inputs):
    """Test ROI projection endpoint with conservative scenario."""
    response = client.post("/v2/analytics/roi-projection", json=conservative_inputs)
    
    assert response.status_code == 200
    data = response.json()
    
    # Check all required output keys are present
    assert "total_denied_revenue" in data
    assert "documentation_denied_revenue" in data
    assert "prevented_denials_revenue" in data
    assert "remaining_documentation_denied_revenue" in data
    assert "current_recovered_revenue" in data
    assert "incremental_recovery_gain" in data
    assert "appeals_avoided_count" in data
    assert "admin_savings" in data
    assert "total_preserved_revenue" in data
    assert "roi_multiple" in data
    assert "assumptions" in data
    
    # Verify calculations match expected values for conservative scenario
    # Total denied: 500M * 0.08 = 40M
    assert abs(data["total_denied_revenue"] - 40_000_000.0) < 1.0
    
    # Documentation denied: 40M * 0.40 = 16M
    assert abs(data["documentation_denied_revenue"] - 16_000_000.0) < 1.0
    
    # Prevented denials: 16M * 0.05 = 800K
    assert abs(data["prevented_denials_revenue"] - 800_000.0) < 1.0
    
    # Remaining denials: 16M - 800K = 15.2M
    assert abs(data["remaining_documentation_denied_revenue"] - 15_200_000.0) < 1.0
    
    # Current recovery: 15.2M * 0.25 = 3.8M
    assert abs(data["current_recovered_revenue"] - 3_800_000.0) < 1.0
    
    # Incremental recovery: 15.2M * 0.05 = 760K
    assert abs(data["incremental_recovery_gain"] - 760_000.0) < 1.0
    
    # Appeals avoided: 200K * 0.08 * 0.40 * 0.05 = 320
    assert abs(data["appeals_avoided_count"] - 320.0) < 1.0
    
    # Admin savings: 320 * 150 = 48K
    assert abs(data["admin_savings"] - 48_000.0) < 1.0
    
    # Total preserved: 800K + 760K + 48K = 1,608K
    assert abs(data["total_preserved_revenue"] - 1_608_000.0) < 1.0
    
    # ROI multiple: 1,608K / 250K = 6.432
    assert data["roi_multiple"] is not None
    assert abs(data["roi_multiple"] - 6.432) < 0.01
    
    # Verify assumptions are echoed back
    assert data["assumptions"]["annual_revenue"] == conservative_inputs["annual_revenue"]
    assert data["assumptions"]["denial_prevention_rate"] == conservative_inputs["denial_prevention_rate"]


def test_roi_projection_happy_path_moderate(client, moderate_inputs):
    """Test ROI projection endpoint with moderate scenario."""
    response = client.post("/v2/analytics/roi-projection", json=moderate_inputs)
    
    assert response.status_code == 200
    data = response.json()
    
    # Prevented denials: 16M * 0.10 = 1.6M
    assert abs(data["prevented_denials_revenue"] - 1_600_000.0) < 1.0
    
    # Remaining denials: 16M - 1.6M = 14.4M
    assert abs(data["remaining_documentation_denied_revenue"] - 14_400_000.0) < 1.0
    
    # Incremental recovery: 14.4M * 0.10 = 1.44M
    assert abs(data["incremental_recovery_gain"] - 1_440_000.0) < 1.0
    
    # Appeals avoided: 200K * 0.08 * 0.40 * 0.10 = 640
    assert abs(data["appeals_avoided_count"] - 640.0) < 1.0
    
    # Admin savings: 640 * 150 = 96K
    assert abs(data["admin_savings"] - 96_000.0) < 1.0
    
    # Total preserved: 1.6M + 1.44M + 96K = 3,136K
    assert abs(data["total_preserved_revenue"] - 3_136_000.0) < 1.0
    
    # ROI multiple: 3,136K / 250K = 12.544
    assert data["roi_multiple"] is not None
    assert abs(data["roi_multiple"] - 12.544) < 0.01


# ============================================================================
# Validation Tests - Reject Invalid Inputs
# ============================================================================

def test_roi_projection_rejects_negative_revenue(client, conservative_inputs):
    """Test that negative annual_revenue is rejected."""
    invalid_inputs = conservative_inputs.copy()
    invalid_inputs["annual_revenue"] = -500_000_000.0
    
    response = client.post("/v2/analytics/roi-projection", json=invalid_inputs)
    
    assert response.status_code == 422
    data = response.json()
    assert "validation_error" in data["error"] or "error" in data


def test_roi_projection_rejects_denial_rate_above_one(client, conservative_inputs):
    """Test that denial_rate > 1.0 is rejected."""
    invalid_inputs = conservative_inputs.copy()
    invalid_inputs["denial_rate"] = 1.5  # 150% denial rate is impossible
    
    response = client.post("/v2/analytics/roi-projection", json=invalid_inputs)
    
    assert response.status_code == 422


def test_roi_projection_rejects_documentation_denial_ratio_above_one(client, conservative_inputs):
    """Test that documentation_denial_ratio > 1.0 is rejected."""
    invalid_inputs = conservative_inputs.copy()
    invalid_inputs["documentation_denial_ratio"] = 1.2
    
    response = client.post("/v2/analytics/roi-projection", json=invalid_inputs)
    
    assert response.status_code == 422


def test_roi_projection_rejects_negative_cost_per_appeal(client, conservative_inputs):
    """Test that negative cost_per_appeal is rejected."""
    invalid_inputs = conservative_inputs.copy()
    invalid_inputs["cost_per_appeal"] = -150.0
    
    response = client.post("/v2/analytics/roi-projection", json=invalid_inputs)
    
    assert response.status_code == 422


def test_roi_projection_rejects_negative_claim_volume(client, conservative_inputs):
    """Test that negative annual_claim_volume is rejected."""
    invalid_inputs = conservative_inputs.copy()
    invalid_inputs["annual_claim_volume"] = -200_000
    
    response = client.post("/v2/analytics/roi-projection", json=invalid_inputs)
    
    assert response.status_code == 422


# ============================================================================
# Determinism Tests
# ============================================================================

def test_roi_projection_deterministic(client, conservative_inputs):
    """Test that same inputs produce identical outputs."""
    response1 = client.post("/v2/analytics/roi-projection", json=conservative_inputs)
    response2 = client.post("/v2/analytics/roi-projection", json=conservative_inputs)
    
    assert response1.status_code == 200
    assert response2.status_code == 200
    
    data1 = response1.json()
    data2 = response2.json()
    
    # All numeric outputs should be identical
    assert data1["total_denied_revenue"] == data2["total_denied_revenue"]
    assert data1["prevented_denials_revenue"] == data2["prevented_denials_revenue"]
    assert data1["incremental_recovery_gain"] == data2["incremental_recovery_gain"]
    assert data1["admin_savings"] == data2["admin_savings"]
    assert data1["total_preserved_revenue"] == data2["total_preserved_revenue"]
    assert data1["roi_multiple"] == data2["roi_multiple"]


# ============================================================================
# Edge Cases
# ============================================================================

def test_roi_projection_zero_cdil_cost(client, conservative_inputs):
    """Test handling of zero CDIL cost (divide-by-zero safety)."""
    inputs_with_zero_cost = conservative_inputs.copy()
    inputs_with_zero_cost["cdil_annual_cost"] = 0.0
    
    response = client.post("/v2/analytics/roi-projection", json=inputs_with_zero_cost)
    
    assert response.status_code == 200
    data = response.json()
    
    # ROI multiple should be None when cost is 0
    assert data["roi_multiple"] is None
    
    # Should include explanatory note
    assert data["roi_note"] is not None
    assert "cdil_annual_cost is 0" in data["roi_note"].lower()
    
    # But other calculations should still work
    assert data["total_preserved_revenue"] > 0


def test_roi_projection_zero_denial_rate(client, conservative_inputs):
    """Test handling of zero denial rate."""
    inputs_with_zero_denials = conservative_inputs.copy()
    inputs_with_zero_denials["denial_rate"] = 0.0
    
    response = client.post("/v2/analytics/roi-projection", json=inputs_with_zero_denials)
    
    assert response.status_code == 200
    data = response.json()
    
    # All denial-related metrics should be 0
    assert data["total_denied_revenue"] == 0.0
    assert data["documentation_denied_revenue"] == 0.0
    assert data["prevented_denials_revenue"] == 0.0
    assert data["incremental_recovery_gain"] == 0.0
    assert data["total_preserved_revenue"] == 0.0
    
    # ROI multiple should be 0
    assert data["roi_multiple"] == 0.0


def test_roi_projection_maximum_prevention_rate(client, conservative_inputs):
    """Test handling of 100% prevention rate."""
    inputs_with_max_prevention = conservative_inputs.copy()
    inputs_with_max_prevention["denial_prevention_rate"] = 1.0  # 100% prevention
    
    response = client.post("/v2/analytics/roi-projection", json=inputs_with_max_prevention)
    
    assert response.status_code == 200
    data = response.json()
    
    # All documentation denials should be prevented
    assert abs(data["prevented_denials_revenue"] - data["documentation_denied_revenue"]) < 1.0
    
    # No remaining denials
    assert abs(data["remaining_documentation_denied_revenue"]) < 1.0
    
    # No incremental recovery (nothing left to appeal)
    assert abs(data["incremental_recovery_gain"]) < 1.0


# ============================================================================
# Service Layer Unit Tests
# ============================================================================

def test_calculate_roi_service_function():
    """Test the underlying calculate_roi service function directly."""
    inputs = RoiInputs(
        annual_revenue=100_000_000.0,
        denial_rate=0.10,
        documentation_denial_ratio=0.50,
        appeal_recovery_rate=0.30,
        denial_prevention_rate=0.10,
        appeal_success_lift=0.10,
        cost_per_appeal=200.0,
        annual_claim_volume=100_000,
        cdil_annual_cost=100_000.0
    )
    
    outputs = calculate_roi(inputs)
    
    # Verify calculation logic
    # Total denied: 100M * 0.10 = 10M
    assert abs(outputs.total_denied_revenue - 10_000_000.0) < 1.0
    
    # Documentation denied: 10M * 0.50 = 5M
    assert abs(outputs.documentation_denied_revenue - 5_000_000.0) < 1.0
    
    # Prevented: 5M * 0.10 = 500K
    assert abs(outputs.prevented_denials_revenue - 500_000.0) < 1.0
    
    # Remaining: 5M - 500K = 4.5M
    assert abs(outputs.remaining_documentation_denied_revenue - 4_500_000.0) < 1.0
    
    # Incremental recovery: 4.5M * 0.10 = 450K
    assert abs(outputs.incremental_recovery_gain - 450_000.0) < 1.0
    
    # Appeals avoided: 100K * 0.10 * 0.50 * 0.10 = 500
    assert abs(outputs.appeals_avoided_count - 500.0) < 1.0
    
    # Admin savings: 500 * 200 = 100K
    assert abs(outputs.admin_savings - 100_000.0) < 1.0
    
    # Total preserved: 500K + 450K + 100K = 1,050K
    assert abs(outputs.total_preserved_revenue - 1_050_000.0) < 1.0
    
    # ROI: 1,050K / 100K = 10.5
    assert outputs.roi_multiple is not None
    assert abs(outputs.roi_multiple - 10.5) < 0.01


def test_calculate_roi_assumptions_echo():
    """Test that input assumptions are echoed in output."""
    inputs = RoiInputs(
        annual_revenue=200_000_000.0,
        denial_rate=0.07,
        documentation_denial_ratio=0.35,
        appeal_recovery_rate=0.20,
        denial_prevention_rate=0.08,
        appeal_success_lift=0.08,
        cost_per_appeal=175.0,
        annual_claim_volume=150_000,
        cdil_annual_cost=200_000.0
    )
    
    outputs = calculate_roi(inputs)
    
    # Verify all inputs are echoed
    assert outputs.assumptions.annual_revenue == inputs.annual_revenue
    assert outputs.assumptions.denial_rate == inputs.denial_rate
    assert outputs.assumptions.documentation_denial_ratio == inputs.documentation_denial_ratio
    assert outputs.assumptions.appeal_recovery_rate == inputs.appeal_recovery_rate
    assert outputs.assumptions.denial_prevention_rate == inputs.denial_prevention_rate
    assert outputs.assumptions.appeal_success_lift == inputs.appeal_success_lift
    assert outputs.assumptions.cost_per_appeal == inputs.cost_per_appeal
    assert outputs.assumptions.annual_claim_volume == inputs.annual_claim_volume
    assert outputs.assumptions.cdil_annual_cost == inputs.cdil_annual_cost
