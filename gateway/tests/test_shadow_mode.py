"""
Tests for Shadow Mode Evidence Deficit Engine.

Tests cover:
- Evidence scoring determinism
- Revenue estimation accuracy
- API endpoint security
- Tenant isolation
- No PHI leakage
"""

import pytest
from fastapi.testclient import TestClient

from gateway.app.main import app
from gateway.app.services.evidence_scoring import score_note_defensibility, DIAGNOSIS_RULES
from gateway.app.services.revenue_model import estimate_revenue_risk, calculate_annual_projection
from gateway.tests.auth_helpers import create_jwt_headers

client = TestClient(app)


class TestEvidenceScoring:
    """Tests for evidence scoring service."""
    
    def test_score_note_with_strong_evidence(self):
        """Test that notes with strong evidence get high scores."""
        note_text = """
        Patient presents with severe protein-calorie malnutrition.
        BMI is 16.5, indicating severe underweight status.
        Serum albumin is 2.1 g/dL (hypoalbuminemia).
        Patient reports 15 lb weight loss over past month.
        Dietary assessment completed by dietician showing inadequate caloric intake.
        """
        
        result = score_note_defensibility(
            note_text=note_text,
            diagnosis_codes=["E43"]
        )
        
        assert result["overall_score"] >= 80, "Note with strong evidence should score high"
        assert len(result["diagnoses"]) == 1
        assert result["diagnoses"][0]["code"] == "E43"
        assert result["diagnoses"][0]["evidence_present"] is True
        assert len(result["diagnoses"][0]["missing_elements"]) == 0
    
    def test_score_note_with_missing_evidence(self):
        """Test that notes with missing evidence get flagged."""
        note_text = """
        Patient has malnutrition.
        """
        
        result = score_note_defensibility(
            note_text=note_text,
            diagnosis_codes=["E43"]
        )
        
        assert result["overall_score"] < 70, "Note with missing evidence should score low"
        assert result["diagnoses"][0]["evidence_present"] is False
        assert len(result["diagnoses"][0]["missing_elements"]) > 0
        assert len(result["flags"]) > 0
    
    def test_score_note_with_sepsis_evidence(self):
        """Test sepsis diagnosis scoring."""
        note_text = """
        Patient presents with sepsis due to pneumonia.
        SIRS criteria met with fever (39.2°C), tachycardia (HR 115), tachypnea (RR 26).
        WBC elevated at 18,000. Blood cultures drawn and pending.
        Lactate 3.2. Chest X-ray shows right lower lobe infiltrate.
        Patient started on broad-spectrum antibiotics.
        """
        
        result = score_note_defensibility(
            note_text=note_text,
            diagnosis_codes=["A41.9"]
        )
        
        assert result["overall_score"] >= 80
        assert result["diagnoses"][0]["evidence_present"] is True
    
    def test_score_note_with_chf_evidence(self):
        """Test heart failure diagnosis scoring."""
        note_text = """
        Patient with acute decompensated heart failure.
        Ejection fraction 30% on recent echo.
        Patient reports worsening dyspnea and orthopnea.
        Physical exam reveals bilateral rales, S3 gallop, and peripheral edema.
        Chest X-ray shows pulmonary edema and cardiomegaly.
        """
        
        result = score_note_defensibility(
            note_text=note_text,
            diagnosis_codes=["I50.9"]
        )
        
        assert result["overall_score"] >= 80
        assert result["diagnoses"][0]["evidence_present"] is True
    
    def test_score_note_with_aki_evidence(self):
        """Test acute kidney injury diagnosis scoring."""
        note_text = """
        Patient with acute kidney injury.
        Creatinine elevated to 2.8 from baseline of 1.0.
        Urine output decreased to 20 mL/hr (oliguria).
        Likely prerenal etiology due to volume depletion.
        """
        
        result = score_note_defensibility(
            note_text=note_text,
            diagnosis_codes=["N17.9"]
        )
        
        assert result["overall_score"] >= 80
        assert result["diagnoses"][0]["evidence_present"] is True
    
    def test_score_note_with_respiratory_failure_evidence(self):
        """Test respiratory failure diagnosis scoring."""
        note_text = """
        Patient with acute respiratory failure.
        ABG shows pH 7.32, PaO2 55, PaCO2 52.
        Oxygen saturation 88% on room air.
        Respiratory rate 32, patient in respiratory distress.
        Started on supplemental oxygen via BiPAP.
        """
        
        result = score_note_defensibility(
            note_text=note_text,
            diagnosis_codes=["J96.00"]
        )
        
        assert result["overall_score"] >= 80
        assert result["diagnoses"][0]["evidence_present"] is True
    
    def test_score_note_with_multiple_diagnoses(self):
        """Test scoring with multiple diagnosis codes."""
        note_text = """
        Patient with malnutrition (BMI 16, albumin 2.0, 10 lb weight loss, dietary consult) 
        and acute kidney injury (creatinine 2.5 from baseline 1.0, oliguria present, prerenal cause).
        """
        
        result = score_note_defensibility(
            note_text=note_text,
            diagnosis_codes=["E43", "N17.9"]
        )
        
        assert len(result["diagnoses"]) == 2
        assert result["overall_score"] >= 80  # Both should be well-supported
    
    def test_score_note_with_unknown_diagnosis(self):
        """Test handling of unknown diagnosis codes."""
        note_text = "Patient presents with condition."
        
        result = score_note_defensibility(
            note_text=note_text,
            diagnosis_codes=["Z99.99"]  # Unknown code
        )
        
        assert len(result["diagnoses"]) == 1
        assert result["diagnoses"][0]["evidence_present"] is None
        assert result["diagnoses"][0]["risk_level"] == "unknown"
    
    def test_score_note_with_structured_data(self):
        """Test that structured data is considered in scoring."""
        note_text = "Patient has malnutrition."
        structured_data = {
            "bmi": 16.5,
            "albumin": 2.1,
            "weight_loss": "15 lbs",
            "dietary_assessment": "completed"
        }
        
        result = score_note_defensibility(
            note_text=note_text,
            diagnosis_codes=["E43"],
            structured_data=structured_data
        )
        
        # Structured data should help improve score
        assert result["overall_score"] > 50
    
    def test_score_empty_note(self):
        """Test handling of empty inputs."""
        result = score_note_defensibility(
            note_text="",
            diagnosis_codes=[]
        )
        
        assert result["overall_score"] == 0
        assert len(result["flags"]) > 0
    
    def test_scoring_is_deterministic(self):
        """Test that scoring produces consistent results."""
        note_text = "Patient with malnutrition, BMI 16, albumin 2.0."
        diagnosis_codes = ["E43"]
        
        result1 = score_note_defensibility(note_text, diagnosis_codes)
        result2 = score_note_defensibility(note_text, diagnosis_codes)
        
        assert result1["overall_score"] == result2["overall_score"]
        assert result1["diagnoses"] == result2["diagnoses"]


class TestRevenueModel:
    """Tests for revenue estimation service."""
    
    def test_estimate_revenue_risk_basic(self):
        """Test basic revenue risk calculation."""
        scored_notes = [
            {"overall_score": 50, "diagnoses": [{"code": "E43", "evidence_present": False}]},
            {"overall_score": 90, "diagnoses": [{"code": "E43", "evidence_present": True}]},
            {"overall_score": 60, "diagnoses": [{"code": "A41.9", "evidence_present": False}]}
        ]
        
        result = estimate_revenue_risk(
            scored_notes=scored_notes,
            average_claim_value=20000,
            denial_probability=0.08
        )
        
        assert result["notes_analyzed"] == 3
        assert result["notes_flagged"] == 2  # Scores < 70
        assert result["percent_flagged"] > 0
        assert result["estimated_revenue_at_risk"] > 0
        
        # Check calculation: 2 notes * $20,000 * 0.08 = $3,200
        expected_risk = 2 * 20000 * 0.08
        assert result["estimated_revenue_at_risk"] == expected_risk
    
    def test_estimate_revenue_risk_no_flags(self):
        """Test revenue risk when all notes are defensible."""
        scored_notes = [
            {"overall_score": 95, "diagnoses": []},
            {"overall_score": 90, "diagnoses": []}
        ]
        
        result = estimate_revenue_risk(
            scored_notes=scored_notes,
            average_claim_value=20000,
            denial_probability=0.08
        )
        
        assert result["notes_flagged"] == 0
        assert result["estimated_revenue_at_risk"] == 0
    
    def test_estimate_revenue_risk_tracks_diagnoses(self):
        """Test that high-risk diagnoses are tracked."""
        scored_notes = [
            {"overall_score": 50, "diagnoses": [
                {"code": "E43", "evidence_present": False, "description": "Malnutrition"}
            ]},
            {"overall_score": 55, "diagnoses": [
                {"code": "E43", "evidence_present": False, "description": "Malnutrition"}
            ]},
            {"overall_score": 60, "diagnoses": [
                {"code": "A41.9", "evidence_present": False, "description": "Sepsis"}
            ]}
        ]
        
        result = estimate_revenue_risk(scored_notes)
        
        assert len(result["high_risk_diagnoses"]) == 2
        # E43 should be first (appears twice)
        assert result["high_risk_diagnoses"][0]["code"] == "E43"
        assert result["high_risk_diagnoses"][0]["count"] == 2
    
    def test_estimate_revenue_risk_empty_list(self):
        """Test handling of empty notes list."""
        result = estimate_revenue_risk([])
        
        assert result["notes_analyzed"] == 0
        assert result["notes_flagged"] == 0
        assert result["estimated_revenue_at_risk"] == 0
    
    def test_calculate_annual_projection(self):
        """Test annual revenue projection."""
        result = calculate_annual_projection(
            current_risk=10000,
            notes_in_sample=100,
            annual_note_volume=10000
        )
        
        # $10,000 risk for 100 notes = $100/note
        # $100/note * 10,000 notes = $1,000,000 annual
        assert result["projected_annual_risk"] == 1000000.0
        assert result["projection_method"] == "linear_extrapolation"
    
    def test_calculate_annual_projection_zero_sample(self):
        """Test annual projection with zero sample."""
        result = calculate_annual_projection(
            current_risk=0,
            notes_in_sample=0,
            annual_note_volume=10000
        )
        
        assert result["projected_annual_risk"] == 0
        assert result["projection_method"] == "insufficient_data"


class TestShadowModeAPI:
    """Tests for shadow mode API endpoints."""
    
    def test_analyze_endpoint_requires_auth(self):
        """Test that analyze endpoint requires authentication."""
        response = client.post("/v1/shadow/analyze", json={
            "notes": [
                {
                    "note_text": "Patient with malnutrition",
                    "diagnosis_codes": ["E43"]
                }
            ]
        })
        
        assert response.status_code == 401  # Unauthorized without JWT
    
    def test_analyze_endpoint_with_valid_request(self):
        """Test successful analysis request."""
        headers = create_jwt_headers("hospital-alpha", role="clinician")
        
        response = client.post("/v1/shadow/analyze", headers=headers, json={
            "notes": [
                {
                    "note_text": "Patient with malnutrition. BMI 16, albumin 2.0, weight loss documented.",
                    "diagnosis_codes": ["E43"]
                }
            ],
            "average_claim_value": 20000,
            "denial_probability": 0.08
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert "summary" in data
        assert "details" in data
        assert "revenue_impact" in data
        assert data["tenant_id"] == "hospital-alpha"
        assert len(data["details"]) == 1
    
    def test_analyze_endpoint_with_multiple_notes(self):
        """Test analysis with multiple notes."""
        headers = create_jwt_headers("hospital-beta", role="clinician")
        
        response = client.post("/v1/shadow/analyze", headers=headers, json={
            "notes": [
                {
                    "note_text": "Malnutrition with BMI 16, albumin 2.0",
                    "diagnosis_codes": ["E43"],
                    "claim_value": 25000
                },
                {
                    "note_text": "Sepsis with SIRS criteria, fever, elevated WBC, blood cultures positive",
                    "diagnosis_codes": ["A41.9"],
                    "claim_value": 30000
                },
                {
                    "note_text": "Patient has condition",
                    "diagnosis_codes": ["E43"]
                }
            ]
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["summary"]["notes_analyzed"] == 3
        assert len(data["details"]) == 3
        assert "estimated_revenue_at_risk" in data["revenue_impact"]
    
    def test_analyze_endpoint_empty_notes(self):
        """Test analysis with no notes."""
        headers = create_jwt_headers("hospital-alpha", role="clinician")
        
        response = client.post("/v1/shadow/analyze", headers=headers, json={
            "notes": []
        })
        
        assert response.status_code == 400
    
    def test_analyze_endpoint_tenant_isolation(self):
        """Test that tenant ID from JWT is used, not request data."""
        headers = create_jwt_headers("hospital-alpha", role="clinician")
        
        response = client.post("/v1/shadow/analyze", headers=headers, json={
            "notes": [
                {
                    "note_text": "Test note",
                    "diagnosis_codes": ["E43"]
                }
            ]
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Tenant ID should come from JWT, not request
        assert data["tenant_id"] == "hospital-alpha"
    
    def test_dashboard_endpoint_requires_auth(self):
        """Test that dashboard endpoint requires authentication."""
        response = client.get("/v1/shadow/dashboard")
        
        assert response.status_code == 401  # Unauthorized without JWT
    
    def test_dashboard_endpoint_requires_prior_analysis(self):
        """Test that dashboard requires analysis to be run first."""
        headers = create_jwt_headers("hospital-new", role="auditor")
        
        response = client.get("/v1/shadow/dashboard", headers=headers)
        
        assert response.status_code == 404
    
    def test_dashboard_endpoint_after_analysis(self):
        """Test dashboard shows data after analysis."""
        headers = create_jwt_headers("hospital-gamma", role="clinician")
        
        # First run analysis
        client.post("/v1/shadow/analyze", headers=headers, json={
            "notes": [
                {
                    "note_text": "Malnutrition with BMI 16, albumin 2.0",
                    "diagnosis_codes": ["E43"]
                },
                {
                    "note_text": "Patient has malnutrition",
                    "diagnosis_codes": ["E43"]
                },
                {
                    "note_text": "Sepsis with complete documentation",
                    "diagnosis_codes": ["A41.9"]
                }
            ]
        })
        
        # Then get dashboard
        response = client.get("/v1/shadow/dashboard", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "percent_defensible" in data
        assert "percent_at_risk" in data
        assert "estimated_annual_leakage" in data
        assert "top_vulnerable_diagnoses" in data
        assert data["tenant_id"] == "hospital-gamma"
        
        # Verify percentages add up to 100
        assert abs(data["percent_defensible"] + data["percent_at_risk"] - 100) < 0.1
    
    def test_dashboard_endpoint_with_annual_volume(self):
        """Test dashboard with annual volume projection."""
        headers = create_jwt_headers("hospital-delta", role="clinician")
        
        # Run analysis
        client.post("/v1/shadow/analyze", headers=headers, json={
            "notes": [
                {
                    "note_text": "Poor documentation",
                    "diagnosis_codes": ["E43"]
                }
            ],
            "average_claim_value": 20000,
            "denial_probability": 0.10
        })
        
        # Get dashboard with annual projection
        response = client.get(
            "/v1/shadow/dashboard?annual_note_volume=10000",
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should project to larger annual amount
        assert data["estimated_annual_leakage"] > 2000  # 1 note sample projected to 10k


class TestShadowModeSecurity:
    """Security tests for shadow mode."""
    
    def test_cross_tenant_isolation(self):
        """Test that tenants cannot see each other's data."""
        # Tenant A analyzes notes
        headers_a = create_jwt_headers("hospital-a", role="clinician")
        client.post("/v1/shadow/analyze", headers=headers_a, json={
            "notes": [
                {
                    "note_text": "Tenant A note",
                    "diagnosis_codes": ["E43"]
                }
            ]
        })
        
        # Tenant B tries to access dashboard
        headers_b = create_jwt_headers("hospital-b", role="auditor")
        response = client.get("/v1/shadow/dashboard", headers=headers_b)
        
        # Should not have access to Tenant A's data
        assert response.status_code == 404
    
    def test_no_phi_in_response(self):
        """Test that note text is not returned in responses."""
        headers = create_jwt_headers("hospital-phi", role="clinician")
        
        response = client.post("/v1/shadow/analyze", headers=headers, json={
            "notes": [
                {
                    "note_text": "Patient John Doe with SSN 123-45-6789 has malnutrition",
                    "diagnosis_codes": ["E43"]
                }
            ]
        })
        
        assert response.status_code == 200
        response_text = response.text.lower()
        
        # Ensure PHI not in response
        assert "john doe" not in response_text
        assert "ssn" not in response_text
        assert "123-45-6789" not in response_text
    
    def test_role_based_access(self):
        """Test that different roles can access shadow mode."""
        note_payload = {
            "notes": [
                {
                    "note_text": "Test note",
                    "diagnosis_codes": ["E43"]
                }
            ]
        }
        
        # Clinician should have access
        headers_clinician = create_jwt_headers("hospital-roles", role="clinician")
        response = client.post("/v1/shadow/analyze", headers=headers_clinician, json=note_payload)
        assert response.status_code == 200
        
        # Auditor should have access
        headers_auditor = create_jwt_headers("hospital-roles", role="auditor")
        response = client.get("/v1/shadow/dashboard", headers=headers_auditor)
        assert response.status_code == 200
        
        # Admin should have access
        headers_admin = create_jwt_headers("hospital-roles", role="admin")
        response = client.post("/v1/shadow/analyze", headers=headers_admin, json=note_payload)
        assert response.status_code == 200


class TestShadowModeIntegration:
    """Integration tests for complete workflows."""
    
    def test_complete_shadow_mode_workflow(self):
        """Test complete workflow: analyze -> dashboard."""
        headers = create_jwt_headers("hospital-workflow", role="clinician")
        
        # Step 1: Analyze a batch of notes
        analyze_response = client.post("/v1/shadow/analyze", headers=headers, json={
            "notes": [
                {
                    "note_text": "Malnutrition with BMI 15.5, albumin 1.8, significant weight loss, dietary assessment by RD",
                    "diagnosis_codes": ["E43"],
                    "claim_value": 24000
                },
                {
                    "note_text": "Patient has malnutrition",
                    "diagnosis_codes": ["E43"],
                    "claim_value": 20000
                },
                {
                    "note_text": "CHF with EF 25%, rales, edema, CXR shows pulmonary edema",
                    "diagnosis_codes": ["I50.9"],
                    "claim_value": 28000
                }
            ],
            "average_claim_value": 22000,
            "denial_probability": 0.09
        })
        
        assert analyze_response.status_code == 200
        analyze_data = analyze_response.json()
        
        # Verify analysis results
        assert analyze_data["summary"]["notes_analyzed"] == 3
        assert "estimated_revenue_at_risk" in analyze_data["revenue_impact"]
        
        # Step 2: Get dashboard
        dashboard_response = client.get("/v1/shadow/dashboard", headers=headers)
        
        assert dashboard_response.status_code == 200
        dashboard_data = dashboard_response.json()
        
        # Verify dashboard metrics
        assert 0 <= dashboard_data["percent_defensible"] <= 100
        assert 0 <= dashboard_data["percent_at_risk"] <= 100
        assert dashboard_data["estimated_annual_leakage"] >= 0
        
        # Verify tenant consistency
        assert analyze_data["tenant_id"] == dashboard_data["tenant_id"]
