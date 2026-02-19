"""
Shadow Mode Intake Models for CDIL Sidecar.

Models for shadow mode ingestion endpoints that allow read-only
intake of clinical notes for retrospective analysis.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ShadowIntakeRequest(BaseModel):
    """Request model for shadow mode note intake."""
    note_text: str = Field(..., description="Clinical note text to ingest")
    encounter_id: Optional[str] = Field(None, description="Optional encounter identifier")
    patient_reference: Optional[str] = Field(None, description="Optional patient reference")
    source_system: Optional[str] = Field(None, description="Optional source system identifier")
    note_type: Optional[str] = Field(None, description="Optional note type (e.g., progress, discharge)")
    author_role: Optional[str] = Field(None, description="Optional author role")


class ShadowIntakeResponse(BaseModel):
    """Response model for shadow mode note intake."""
    shadow_id: str = Field(..., description="Unique shadow item identifier")
    note_hash: str = Field(..., description="SHA-256 hash of note text")
    timestamp: str = Field(..., description="Ingestion timestamp (ISO 8601 UTC)")
    tenant_id: str = Field(..., description="Tenant ID from authentication")
    status: str = Field(..., description="Status: ingested, analyzed, exported")


class ShadowItemDetail(BaseModel):
    """Detailed shadow item response."""
    shadow_id: str = Field(..., description="Unique shadow item identifier")
    tenant_id: str = Field(..., description="Tenant ID")
    created_at_utc: str = Field(..., description="Creation timestamp (ISO 8601 UTC)")
    note_hash: str = Field(..., description="SHA-256 hash of note text")
    encounter_id: Optional[str] = Field(None, description="Encounter identifier")
    patient_reference: Optional[str] = Field(None, description="Patient reference (hashed)")
    source_system: Optional[str] = Field(None, description="Source system identifier")
    note_type: Optional[str] = Field(None, description="Note type")
    author_role: Optional[str] = Field(None, description="Author role")
    status: str = Field(..., description="Status: ingested, analyzed, exported")
    certificate_id: Optional[str] = Field(None, description="Linked certificate ID if issued")
    score: Optional[int] = Field(None, description="Evidence score (0-100) if analyzed")
    score_band: Optional[str] = Field(None, description="Risk band: green, yellow, red")
    note_text: Optional[str] = Field(None, description="Note text if STORE_NOTE_TEXT enabled")


class ShadowItemListResponse(BaseModel):
    """Response model for shadow item list queries."""
    items: List[ShadowItemDetail] = Field(..., description="List of shadow items")
    total: int = Field(..., description="Total count of items matching filters")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
