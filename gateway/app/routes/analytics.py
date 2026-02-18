"""
Analytics endpoints for CDIL business metrics and ROI projections.

This module provides business intelligence endpoints that do NOT process PHI.
All endpoints are pure computation/modeling based on financial/operational inputs.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

from gateway.app.services.roi import RoiInputs, RoiOutputs, calculate_roi


router = APIRouter(prefix="/v2/analytics", tags=["analytics"])


@router.post("/roi-projection", response_model=RoiOutputs)
async def roi_projection(inputs: RoiInputs) -> RoiOutputs:
    """
    Calculate ROI projection for CDIL deployment.
    
    This endpoint performs pure financial/operational modeling with NO PHI processing.
    It calculates preserved revenue based on denial prevention and appeal success improvements.
    
    **No database access, no PHI, no storage - fully stateless computation.**
    
    Request body must include:
    - annual_revenue: Annual Net Patient Service Revenue (> 0)
    - denial_rate: Overall denial rate (0.0 to 1.0)
    - documentation_denial_ratio: % denials due to documentation (0.0 to 1.0)
    - appeal_recovery_rate: Current baseline appeal recovery (0.0 to 1.0)
    - denial_prevention_rate: CDIL lever - % denials prevented (0.0 to 1.0)
    - appeal_success_lift: CDIL lever - incremental appeal success (0.0 to 1.0)
    - cost_per_appeal: Average cost per manual appeal (>= 0)
    - annual_claim_volume: Total annual claims (>= 0)
    - cdil_annual_cost: CDIL annual cost (>= 0)
    
    Returns:
    - All intermediate and final computed metrics
    - ROI multiple (or null if cdil_annual_cost is 0)
    - Assumptions echoed back for transparency
    
    Example (conservative scenario):
    ```json
    {
        "annual_revenue": 500000000,
        "denial_rate": 0.08,
        "documentation_denial_ratio": 0.40,
        "appeal_recovery_rate": 0.25,
        "denial_prevention_rate": 0.05,
        "appeal_success_lift": 0.05,
        "cost_per_appeal": 150,
        "annual_claim_volume": 200000,
        "cdil_annual_cost": 250000
    }
    ```
    
    Validation:
    - Rejects negative revenue
    - Rejects rates > 1.0
    - Rejects negative costs/volumes
    """
    try:
        # Calculate ROI (inputs already validated by Pydantic)
        outputs = calculate_roi(inputs)
        return outputs
        
    except ValidationError as e:
        # This should be caught by FastAPI's validation, but handle it explicitly
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "validation_error",
                "message": "Invalid input parameters",
                "details": e.errors()
            }
        )
    except Exception as e:
        # Catch any unexpected errors (should not happen in pure computation)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "calculation_error",
                "message": "Failed to calculate ROI projection"
            }
        )
