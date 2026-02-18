#!/bin/bash
# Demo script for CDIL ROI Projection Endpoint
# Usage: ./demo/roi_endpoint_demo.sh

echo "================================================================================"
echo "CDIL ROI Projection Endpoint Demo"
echo "================================================================================"
echo ""

# Check if server is running
if ! curl -s http://localhost:8000/healthz > /dev/null 2>&1; then
    echo "ERROR: CDIL server is not running."
    echo "Start the server with: uvicorn gateway.app.main:app --reload --port 8000"
    exit 1
fi

echo "✓ Server is running at http://localhost:8000"
echo ""

echo "Scenario 1: Conservative (5% / 5%)"
echo "-----------------------------------"
curl -s -X POST http://localhost:8000/v2/analytics/roi-projection \
  -H "Content-Type: application/json" \
  -d '{
    "annual_revenue": 500000000,
    "denial_rate": 0.08,
    "documentation_denial_ratio": 0.40,
    "appeal_recovery_rate": 0.25,
    "denial_prevention_rate": 0.05,
    "appeal_success_lift": 0.05,
    "cost_per_appeal": 150,
    "annual_claim_volume": 200000,
    "cdil_annual_cost": 250000
  }' | python -m json.tool | grep -E "(total_preserved_revenue|roi_multiple)"

echo ""
echo "Scenario 2: Moderate (10% / 10%)"
echo "--------------------------------"
curl -s -X POST http://localhost:8000/v2/analytics/roi-projection \
  -H "Content-Type: application/json" \
  -d '{
    "annual_revenue": 500000000,
    "denial_rate": 0.08,
    "documentation_denial_ratio": 0.40,
    "appeal_recovery_rate": 0.25,
    "denial_prevention_rate": 0.10,
    "appeal_success_lift": 0.10,
    "cost_per_appeal": 150,
    "annual_claim_volume": 200000,
    "cdil_annual_cost": 250000
  }' | python -m json.tool | grep -E "(total_preserved_revenue|roi_multiple)"

echo ""
echo "Scenario 3: Aggressive (15% / 15%)"
echo "----------------------------------"
curl -s -X POST http://localhost:8000/v2/analytics/roi-projection \
  -H "Content-Type: application/json" \
  -d '{
    "annual_revenue": 500000000,
    "denial_rate": 0.08,
    "documentation_denial_ratio": 0.40,
    "appeal_recovery_rate": 0.25,
    "denial_prevention_rate": 0.15,
    "appeal_success_lift": 0.15,
    "cost_per_appeal": 150,
    "annual_claim_volume": 200000,
    "cdil_annual_cost": 250000
  }' | python -m json.tool | grep -E "(total_preserved_revenue|roi_multiple)"

echo ""
echo "================================================================================"
echo "Demo complete. See docs/ROI_CALCULATOR_TEMPLATE.md for detailed formulas."
echo "================================================================================"
