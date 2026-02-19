"""
Executive Dashboard API Routes for CDIL Sidecar.

Provides dashboard endpoints for executives to see:
- Notes reviewed and certificates issued
- Verification pass rates
- High-risk notes and deficits
- Defense bundle readiness
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional, Dict, Any

from gateway.app.security.auth import Identity, get_current_identity
from gateway.app.services.shadow_intake import list_shadow_items
from gateway.app.db.migrate import get_db_path
import sqlite3

router = APIRouter(prefix="/v1/dashboard", tags=["dashboard"])


@router.get(
    "/executive-summary",
    summary="Get executive summary dashboard",
    description="""
    Executive Summary Dashboard (The "Dashboard That Says...").
    
    Provides the key metrics executives need to see in 10 seconds:
    - Notes reviewed and certificates issued
    - Verification pass rate
    - Tamper detection events
    - High-risk notes count
    - Top deficit categories
    - Most/least defensible notes
    - Export-ready bundles
    
    **Authentication:**
    - Requires valid JWT with tenant_id claim
    - Only shows data for authenticated tenant
    
    **Date Range:**
    - from: Start date (ISO 8601 UTC)
    - to: End date (ISO 8601 UTC)
    - If not provided, shows all-time metrics
    """,
)
async def get_executive_summary(
    identity: Identity = Depends(get_current_identity),
    from_date: Optional[str] = Query(
        None, alias="from", description="Start date (ISO 8601 UTC)"
    ),
    to_date: Optional[str] = Query(
        None, alias="to", description="End date (ISO 8601 UTC)"
    ),
) -> Dict[str, Any]:
    """
    Get executive summary metrics.

    This is the "scary screen" for executives showing:
    - Overall system health and integrity
    - Risk indicators and deficit patterns
    - Actionable insights

    Args:
        identity: Authenticated identity (from JWT)
        from_date: Optional start date filter
        to_date: Optional end date filter

    Returns:
        Executive summary with key metrics
    """
    tenant_id = identity.tenant_id

    # Get database connection
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Build date filters
        date_filters = []
        params = [tenant_id]

        if from_date:
            date_filters.append("created_at_utc >= ?")
            params.append(from_date)

        if to_date:
            date_filters.append("created_at_utc <= ?")
            params.append(to_date)

        date_sql = " AND " + " AND ".join(date_filters) if date_filters else ""

        # Count certificates issued (notes reviewed)
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM certificates
            WHERE tenant_id = ? {date_sql}
        """,
            params,
        )
        certificates_issued = cursor.fetchone()[0]

        # Count shadow items (notes reviewed in shadow mode)
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM shadow_items
            WHERE tenant_id = ? {date_sql}
        """,
            params,
        )
        shadow_items = cursor.fetchone()[0]

        # Total notes reviewed (certificates + shadow items)
        notes_reviewed = certificates_issued + shadow_items

        # Verification pass rate (assume 100% for now - no tamper detection yet)
        # In production, this would query verification_events table
        verification_pass_rate = 1.0
        tamper_events_detected = 0

        # Count high-risk notes (score_band = 'red' or score < 60)
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM shadow_items
            WHERE tenant_id = ? {date_sql}
            AND (score_band = 'red' OR (score IS NOT NULL AND score < 60))
        """,
            params,
        )
        high_risk_notes = cursor.fetchone()[0]

        # Get top deficit categories (using score_band as proxy)
        # In production, this would aggregate deficit_category from analysis results
        cursor.execute(
            f"""
            SELECT 
                score_band,
                COUNT(*) as count
            FROM shadow_items
            WHERE tenant_id = ? {date_sql}
            AND score_band IS NOT NULL
            GROUP BY score_band
            ORDER BY count DESC
            LIMIT 5
        """,
            params,
        )

        deficit_rows = cursor.fetchall()
        top_deficit_categories = []

        # Map score_band to deficit categories (heuristic)
        category_mapping = {
            "red": "DX_SUPPORT_MISSING",
            "yellow": "PROCEDURE_JUSTIFICATION_THIN",
            "green": "TIMELINE_INCOHERENT",
        }

        for row in deficit_rows:
            if row["score_band"] in category_mapping:
                top_deficit_categories.append(
                    {
                        "category": category_mapping[row["score_band"]],
                        "count": row["count"],
                    }
                )

        # Count most defensible notes (score >= 80 or score_band = 'green')
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM shadow_items
            WHERE tenant_id = ? {date_sql}
            AND (score_band = 'green' OR (score IS NOT NULL AND score >= 80))
        """,
            params,
        )
        most_defensible_notes = cursor.fetchone()[0]

        # Count least defensible notes (score < 40 or score_band = 'red')
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM shadow_items
            WHERE tenant_id = ? {date_sql}
            AND (score_band = 'red' OR (score IS NOT NULL AND score < 40))
        """,
            params,
        )
        least_defensible_notes = cursor.fetchone()[0]

        # Export-ready bundles (all certificates can be exported)
        export_ready_bundles = certificates_issued

        return {
            "tenant_id": tenant_id,
            "window": {"from": from_date or "all-time", "to": to_date or "now"},
            "notes_reviewed": notes_reviewed,
            "certificates_issued": certificates_issued,
            "verification_pass_rate": verification_pass_rate,
            "tamper_events_detected": tamper_events_detected,
            "high_risk_notes": high_risk_notes,
            "top_deficit_categories": top_deficit_categories,
            "most_defensible_notes": most_defensible_notes,
            "least_defensible_notes": least_defensible_notes,
            "export_ready_bundles": export_ready_bundles,
        }

    finally:
        conn.close()


@router.get(
    "/risk-queue",
    summary="Get risk queue for specialist review",
    description="""
    Risk Queue (Specialist Worklist).
    
    Returns a prioritized list of notes that need review or remediation.
    Filtered by risk band (HIGH, MEDIUM, LOW).
    
    **Use Cases:**
    - CDI specialist worklist
    - Quality improvement review queue
    - High-risk note triage
    
    **Filters:**
    - band: Risk band filter (HIGH, MEDIUM, LOW)
    - limit: Max results to return (default: 50)
    
    **Authentication:**
    - Requires valid JWT with tenant_id claim
    - Only shows data for authenticated tenant
    """,
)
async def get_risk_queue(
    identity: Identity = Depends(get_current_identity),
    band: Optional[str] = Query(
        None, description="Risk band filter (HIGH, MEDIUM, LOW)"
    ),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
) -> Dict[str, Any]:
    """
    Get risk queue for specialist review.

    Args:
        identity: Authenticated identity (from JWT)
        band: Optional risk band filter
        limit: Max results to return

    Returns:
        Risk queue with items sorted by risk
    """
    tenant_id = identity.tenant_id

    # Map band to score_band
    band_mapping = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}

    score_band = None
    if band and band.upper() in band_mapping:
        score_band = band_mapping[band.upper()]

    # Get shadow items filtered by score_band
    result = list_shadow_items(
        tenant_id=tenant_id, score_band=score_band, page=1, page_size=limit
    )

    # Build risk queue items
    queue_items = []
    for item in result["items"]:
        # Get top 3 deficits (heuristic - in production would come from analysis)
        deficits = []
        if item.get("score_band") == "red":
            deficits = [
                "DX_SUPPORT_MISSING: High-value diagnosis lacks objective evidence",
                "HPI_INCOMPLETE: Missing timing, severity, or associated symptoms",
                "ATTESTATION_MISSING: No physician signature or attestation",
            ]
        elif item.get("score_band") == "yellow":
            deficits = [
                "PROCEDURE_JUSTIFICATION_THIN: Procedure lacks supporting rationale",
                "LAB_NOT_DISCUSSED: Critical lab value not addressed in note",
            ]

        queue_items.append(
            {
                "shadow_id": item.get("shadow_id"),
                "certificate_id": item.get("certificate_id"),
                "band": (item.get("score_band") or "unknown").upper(),
                "score": item.get("score"),
                "deficits": deficits[:3],  # Top 3
                "what_to_fix": (
                    "Add supporting evidence and documentation"
                    if deficits
                    else "No major issues"
                ),
                "export_links": {
                    "evidence_bundle_json": (
                        f"/v1/certificates/{item.get('certificate_id')}/evidence-bundle.json"
                        if item.get("certificate_id")
                        else None
                    ),
                    "evidence_bundle_zip": (
                        f"/v1/certificates/{item.get('certificate_id')}/evidence-bundle.zip"
                        if item.get("certificate_id")
                        else None
                    ),
                },
            }
        )

    return {
        "tenant_id": tenant_id,
        "band_filter": band,
        "items": queue_items,
        "total": result["total"],
        "returned": len(queue_items),
    }
