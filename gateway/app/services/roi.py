"""
ROI (Return on Investment) calculation service for CDIL.

This module provides financial modeling for the ROI of deploying CDIL,
calculating preserved revenue from denial prevention and appeal success improvements.

No PHI is processed or stored by this service - it's pure financial/operational modeling.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional


class RoiInputs(BaseModel):
    """
    Input parameters for ROI calculation.
    
    All financial values are in USD. Rates are represented as floats between 0 and 1
    (e.g., 0.08 represents 8%).
    """
    annual_revenue: float = Field(
        ...,
        description="Annual Net Patient Service Revenue (NPSR) in USD",
        gt=0
    )
    denial_rate: float = Field(
        ...,
        description="Overall denial rate (0.00 to 1.00)",
        ge=0,
        le=1
    )
    documentation_denial_ratio: float = Field(
        ...,
        description="Ratio of denials due to documentation issues (0.00 to 1.00)",
        ge=0,
        le=1
    )
    appeal_recovery_rate: float = Field(
        ...,
        description="Current baseline appeal recovery rate (0.00 to 1.00)",
        ge=0,
        le=1
    )
    denial_prevention_rate: float = Field(
        ...,
        description="CDIL lever: % of documentation denials prevented pre-submission (0.00 to 1.00)",
        ge=0,
        le=1
    )
    appeal_success_lift: float = Field(
        ...,
        description="CDIL lever: Incremental appeal success rate improvement (0.00 to 1.00)",
        ge=0,
        le=1
    )
    cost_per_appeal: float = Field(
        ...,
        description="Average cost per manual appeal in USD",
        ge=0
    )
    annual_claim_volume: int = Field(
        ...,
        description="Total claims submitted annually",
        ge=0
    )
    cdil_annual_cost: float = Field(
        ...,
        description="Annual CDIL licensing and implementation cost in USD",
        ge=0
    )


class RoiOutputs(BaseModel):
    """
    Output metrics from ROI calculation.
    
    All computed revenue/savings values in USD.
    ROI multiple can be None if cdil_annual_cost is 0.
    """
    total_denied_revenue: float = Field(
        ...,
        description="Total revenue denied annually"
    )
    documentation_denied_revenue: float = Field(
        ...,
        description="Revenue denied due to documentation issues"
    )
    prevented_denials_revenue: float = Field(
        ...,
        description="Revenue preserved by preventing denials pre-submission"
    )
    remaining_documentation_denied_revenue: float = Field(
        ...,
        description="Documentation-related denials after prevention"
    )
    current_recovered_revenue: float = Field(
        ...,
        description="Baseline recovered revenue from current appeal process"
    )
    incremental_recovery_gain: float = Field(
        ...,
        description="Additional revenue recovered via improved appeal success"
    )
    appeals_avoided_count: float = Field(
        ...,
        description="Number of appeals avoided due to denial prevention"
    )
    admin_savings: float = Field(
        ...,
        description="Administrative cost savings from avoided appeals"
    )
    total_preserved_revenue: float = Field(
        ...,
        description="Total revenue preserved (prevention + incremental recovery + admin savings)"
    )
    roi_multiple: Optional[float] = Field(
        ...,
        description="ROI multiple (preserved revenue / CDIL cost). None if CDIL cost is 0."
    )
    roi_note: Optional[str] = Field(
        default=None,
        description="Explanatory note about ROI calculation"
    )
    assumptions: RoiInputs = Field(
        ...,
        description="Echo of input assumptions for transparency"
    )


def calculate_roi(inputs: RoiInputs) -> RoiOutputs:
    """
    Calculate ROI metrics for CDIL deployment.
    
    This is a pure computation function with no side effects - no database access,
    no PHI processing, fully deterministic.
    
    Calculation steps:
    1. Calculate total documentation-related denied revenue
    2. Calculate prevented denials (denial_prevention_rate applied)
    3. Calculate remaining denials after prevention
    4. Calculate current baseline appeal recovery
    5. Calculate incremental recovery from appeal success lift
    6. Calculate administrative savings from avoided appeals
    7. Sum total preserved revenue and compute ROI multiple
    
    Args:
        inputs: RoiInputs with all required parameters
        
    Returns:
        RoiOutputs with all computed metrics
    """
    
    # Step 1: Total denied revenue
    total_denied_revenue = inputs.annual_revenue * inputs.denial_rate
    
    # Step 2: Documentation-related denied revenue
    documentation_denied_revenue = total_denied_revenue * inputs.documentation_denial_ratio
    
    # Step 3: Prevented denials (revenue saved by catching issues pre-submission)
    prevented_denials_revenue = documentation_denied_revenue * inputs.denial_prevention_rate
    
    # Step 4: Remaining documentation denials after prevention
    remaining_documentation_denied_revenue = documentation_denied_revenue - prevented_denials_revenue
    
    # Step 5: Current baseline appeal recovery (what would happen without CDIL)
    current_recovered_revenue = remaining_documentation_denied_revenue * inputs.appeal_recovery_rate
    
    # Step 6: Incremental recovery gain from appeal success lift
    # This is the ADDITIONAL revenue recovered beyond baseline due to CDIL's evidence bundles
    incremental_recovery_gain = remaining_documentation_denied_revenue * inputs.appeal_success_lift
    
    # Step 7: Calculate administrative savings
    # Appeals avoided = number of denials prevented
    total_documentation_denials_count = inputs.annual_claim_volume * inputs.denial_rate * inputs.documentation_denial_ratio
    appeals_avoided_count = total_documentation_denials_count * inputs.denial_prevention_rate
    admin_savings = appeals_avoided_count * inputs.cost_per_appeal
    
    # Step 8: Total preserved revenue (sum of all benefits)
    total_preserved_revenue = prevented_denials_revenue + incremental_recovery_gain + admin_savings
    
    # Step 9: ROI multiple (handle divide-by-zero)
    roi_multiple = None
    roi_note = None
    
    if inputs.cdil_annual_cost > 0:
        roi_multiple = total_preserved_revenue / inputs.cdil_annual_cost
    else:
        roi_note = "ROI multiple cannot be calculated: cdil_annual_cost is 0"
    
    return RoiOutputs(
        total_denied_revenue=total_denied_revenue,
        documentation_denied_revenue=documentation_denied_revenue,
        prevented_denials_revenue=prevented_denials_revenue,
        remaining_documentation_denied_revenue=remaining_documentation_denied_revenue,
        current_recovered_revenue=current_recovered_revenue,
        incremental_recovery_gain=incremental_recovery_gain,
        appeals_avoided_count=appeals_avoided_count,
        admin_savings=admin_savings,
        total_preserved_revenue=total_preserved_revenue,
        roi_multiple=roi_multiple,
        roi_note=roi_note,
        assumptions=inputs
    )
