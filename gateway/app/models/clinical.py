"""
Clinical documentation models for healthcare-specific routes.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ClinicalDocRequest(BaseModel):
    """Request model for clinical documentation integrity certificate generation."""
    
    # Clinical identifiers
    clinician_id: str = Field(..., description="Identifier for the clinician")
    patient_id: str = Field(..., description="Patient identifier (will be hashed)")
    encounter_id: str = Field(..., description="Encounter/visit identifier")
    
    # AI vendor information
    ai_vendor: str = Field(..., description="AI vendor/provider name (e.g., 'openai', 'anthropic')")
    model_version: str = Field(..., description="AI model version (e.g., 'gpt-4-turbo')")
    prompt_version: str = Field(..., description="Prompt template version identifier")
    governance_policy_version: str = Field(..., description="Governance policy version")
    
    # Documentation content
    note_text: str = Field(..., description="AI-generated clinical note text")
    
    # Review information
    human_reviewed: bool = Field(default=False, description="Whether a human reviewed the note")
    human_editor_id: Optional[str] = Field(default=None, description="Identifier of human reviewer/editor")
    
    # Optional metadata
    note_type: Optional[str] = Field(default=None, description="Type of clinical note (e.g., 'progress_note', 'discharge_summary')")
    environment: str = Field(default="prod", description="Environment: prod, staging, or dev")


class ClinicalDocumentationCertificate(BaseModel):
    """Clinical Documentation Integrity Certificate - response model."""
    
    # Core identifiers
    certificate_id: str = Field(..., description="Unique certificate identifier")
    encounter_id: str = Field(..., description="Encounter identifier")
    
    # Version tracking
    model_version: str = Field(..., description="AI model version")
    prompt_version: str = Field(..., description="Prompt version")
    governance_policy_version: str = Field(..., description="Governance policy version")
    
    # Integrity hashes (no PHI)
    note_hash: str = Field(..., description="SHA-256 hash of clinical note")
    patient_hash: str = Field(..., description="SHA-256 hash of patient identifier")
    
    # Metadata
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    human_reviewed: bool = Field(..., description="Whether note was human reviewed")
    
    # Cryptographic proof
    signature: str = Field(..., description="Cryptographic signature")
    final_hash: str = Field(..., description="HALO chain final hash")
    
    # Governance attestation
    governance_checks: list[str] = Field(default_factory=list, description="List of governance checks executed")


class ClinicalDocResponse(BaseModel):
    """Response from clinical documentation endpoint."""
    
    certificate_id: str = Field(..., description="Unique certificate identifier")
    verification_url: str = Field(..., description="URL to verify certificate")
    hash_prefix: str = Field(..., description="First 8 characters of final hash for quick reference")
    certificate: ClinicalDocumentationCertificate = Field(..., description="Full certificate details")
