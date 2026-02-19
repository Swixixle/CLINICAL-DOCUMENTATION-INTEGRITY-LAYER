"""
Shadow Mode Intake API Routes.

Provides endpoints for ingesting clinical notes in shadow mode (read-only sidecar).
No EMR integration required - designed for pilot deployments.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from gateway.app.models.shadow_intake import (
    ShadowIntakeRequest,
    ShadowIntakeResponse,
    ShadowItemDetail,
    ShadowItemListResponse,
)
from gateway.app.security.auth import Identity, get_current_identity
from gateway.app.services.shadow_intake import (
    create_shadow_item,
    get_shadow_item,
    list_shadow_items,
)

router = APIRouter(prefix="/v1/shadow", tags=["shadow-intake"])


@router.post(
    "/intake",
    response_model=ShadowIntakeResponse,
    summary="Ingest clinical note in shadow mode",
    description="""
    Shadow Mode Intake (Read-only Sidecar).
    
    Ingests a clinical note for retrospective analysis without EMR integration.
    
    **PHI Safety:**
    - Note text is hashed immediately
    - Plaintext NOT stored unless STORE_NOTE_TEXT=true
    - Patient references are hashed
    - Only metadata and hashes persisted by default
    
    **Use Cases:**
    - Pilot deployments without EHR integration
    - Retrospective documentation analysis
    - Evidence deficit identification
    - Revenue leakage estimation
    
    **Authentication:**
    - Requires valid JWT with tenant_id claim
    - Tenant isolation enforced
    """,
)
async def intake_shadow_note(
    request: ShadowIntakeRequest, identity: Identity = Depends(get_current_identity)
) -> ShadowIntakeResponse:
    """
    Ingest a clinical note in shadow mode.

    This is a read-only ingestion endpoint that does not integrate with EHRs.
    Notes are hashed but not stored in plaintext unless explicitly configured.

    Args:
        request: Shadow intake request with note text and metadata
        identity: Authenticated identity (from JWT)

    Returns:
        Shadow intake response with shadow_id and note_hash
    """
    # Validate note text is not empty
    if not request.note_text or len(request.note_text.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_note_text",
                "message": "note_text must be at least 10 characters",
            },
        )

    # Create shadow item
    result = create_shadow_item(
        tenant_id=identity.tenant_id,
        note_text=request.note_text,
        encounter_id=request.encounter_id,
        patient_reference=request.patient_reference,
        source_system=request.source_system,
        note_type=request.note_type,
        author_role=request.author_role,
    )

    return ShadowIntakeResponse(**result)


@router.get(
    "/items/{shadow_id}",
    response_model=ShadowItemDetail,
    summary="Get shadow item by ID",
    description="""
    Retrieve a specific shadow item by its ID.
    
    **Tenant Isolation:**
    - Returns 404 if shadow_id belongs to a different tenant
    - No cross-tenant access allowed
    
    **Authentication:**
    - Requires valid JWT with tenant_id claim
    """,
)
async def get_shadow_item_detail(
    shadow_id: str, identity: Identity = Depends(get_current_identity)
) -> ShadowItemDetail:
    """
    Get a shadow item by ID.

    Enforces tenant isolation: returns 404 if item belongs to different tenant.

    Args:
        shadow_id: Shadow item identifier
        identity: Authenticated identity (from JWT)

    Returns:
        Shadow item detail

    Raises:
        HTTPException: 404 if not found or unauthorized
    """
    item = get_shadow_item(shadow_id, identity.tenant_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "shadow_item_not_found",
                "message": f"Shadow item {shadow_id} not found or unauthorized",
            },
        )

    # Remove note_text from response unless explicitly stored
    if item.get("note_text") is None:
        item.pop("note_text", None)

    return ShadowItemDetail(**item)


@router.get(
    "/items",
    response_model=ShadowItemListResponse,
    summary="List shadow items with filters",
    description="""
    List shadow items with optional date range and status filters.
    
    **Tenant Isolation:**
    - Only returns items for authenticated tenant
    - No cross-tenant access
    
    **Filters:**
    - from: Start date (ISO 8601 UTC)
    - to: End date (ISO 8601 UTC)
    - status: Item status (ingested, analyzed, exported)
    - score_band: Risk band (green, yellow, red)
    
    **Pagination:**
    - page: Page number (default: 1)
    - page_size: Items per page (default: 50, max: 100)
    
    **Authentication:**
    - Requires valid JWT with tenant_id claim
    """,
)
async def list_shadow_items_endpoint(
    identity: Identity = Depends(get_current_identity),
    from_date: Optional[str] = Query(
        None, alias="from", description="Start date (ISO 8601 UTC)"
    ),
    to_date: Optional[str] = Query(
        None, alias="to", description="End date (ISO 8601 UTC)"
    ),
    status: Optional[str] = Query(None, description="Status filter"),
    score_band: Optional[str] = Query(
        None, description="Score band filter (green, yellow, red)"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
) -> ShadowItemListResponse:
    """
    List shadow items with filters.

    Enforces tenant isolation: only returns items for authenticated tenant.

    Args:
        identity: Authenticated identity (from JWT)
        from_date: Optional start date filter
        to_date: Optional end date filter
        status: Optional status filter
        score_band: Optional score band filter
        page: Page number
        page_size: Items per page

    Returns:
        Shadow item list response with pagination
    """
    result = list_shadow_items(
        tenant_id=identity.tenant_id,
        from_date=from_date,
        to_date=to_date,
        status=status,
        score_band=score_band,
        page=page,
        page_size=page_size,
    )

    # Convert items to ShadowItemDetail models
    items = [ShadowItemDetail(**item) for item in result["items"]]

    return ShadowItemListResponse(
        items=items,
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )
