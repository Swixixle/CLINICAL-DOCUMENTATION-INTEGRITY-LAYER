"""
Clinical Documentation models for CDIL.

These models define the request and response schemas for clinical documentation
integrity certificate issuance.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class ClinicalDocumentationRequest(BaseModel):
    """
    Request to issue an integrity certificate for finalized clinical documentation.
    
    PHI Handling:
    - note_text: hashed before storage, never persisted in plaintext
    - patient_reference: hashed if provided
    - human_reviewer_id: hashed if provided
    
    Note: tenant_id is derived from JWT authentication, not from request body or headers
    """
    # AI Model metadata (Courtroom Defense Mode - required for provenance)
    model_name: str = Field(..., description="AI model name/identifier (e.g., 'gpt-4', 'claude-3')")
    model_version: str = Field(..., description="AI model version used to generate note")
    prompt_version: str = Field(..., description="Prompt template version")
    
    # Governance metadata
    governance_policy_version: str = Field(..., description="Governance policy version")
    
    # Clinical note content (will be hashed, not stored in plaintext)
    note_text: str = Field(..., description="Clinical note content (will be hashed)")
    
    # Review status (Courtroom Defense Mode - human attestation)
    human_reviewed: bool = Field(..., description="Whether note was reviewed by clinician")
    
    # Optional fields
    human_reviewer_id: Optional[str] = Field(default=None, description="Reviewer ID (will be hashed if provided)")
    encounter_id: Optional[str] = Field(default=None, description="Encounter/visit identifier")
    patient_reference: Optional[str] = Field(default=None, description="Patient reference (will be hashed if provided)")


class IntegrityChain(BaseModel):
    """Integrity chain linkage for a certificate."""
    previous_hash: Optional[str] = Field(default=None, description="Hash of previous certificate in chain")
    chain_hash: str = Field(..., description="Hash of this certificate including chain linkage")


class SignatureBundle(BaseModel):
    """Cryptographic signature for a certificate."""
    key_id: str = Field(..., description="Signing key identifier")
    algorithm: str = Field(..., description="Signature algorithm (e.g., ECDSA_SHA_256)")
    signature: str = Field(..., description="Base64-encoded signature")


class DocumentationIntegrityCertificate(BaseModel):
    """
    Integrity certificate for finalized clinical documentation.
    
    This certificate provides cryptographic proof of:
    - Note content integrity (via note_hash)
    - Governance compliance (model_version, policy_version)
    - Human review status and attestation
    - Chain linkage (prevents tampering/insertion)
    - Signature (proves origin, prevents forgery)
    - Timing integrity (finalization vs EHR reference)
    
    No plaintext PHI is included.
    
    Courtroom Defense Mode: ALL provenance fields are included in the signed
    canonical message to provide complete chain of custody.
    """
    # Certificate identification
    certificate_id: str = Field(..., description="Unique certificate identifier")
    tenant_id: str = Field(..., description="Tenant/organization identifier")
    timestamp: str = Field(..., description="Certificate issuance timestamp (ISO 8601 UTC)")
    issued_at_utc: str = Field(..., description="When certificate was issued (ISO 8601 UTC) - signed field")
    
    # Timing integrity
    finalized_at: str = Field(..., description="When note was finalized and certificate issued (ISO 8601 UTC)")
    ehr_referenced_at: Optional[str] = Field(default=None, description="When EHR/record references the note/cert (ISO 8601 UTC)")
    ehr_commit_id: Optional[str] = Field(default=None, description="Opaque EHR reference string (no PHI)")
    
    # AI Model metadata (Courtroom Defense Mode)
    model_name: str = Field(..., description="AI model name/identifier (e.g., 'gpt-4', 'claude-3')")
    model_version: str = Field(..., description="AI model version")
    prompt_version: str = Field(..., description="Prompt template version")
    
    # Governance metadata
    governance_policy_version: str = Field(..., description="Governance policy version")
    governance_policy_hash: str = Field(..., description="Hash of governance policy document (signed)")
    
    # Governance provenance (legacy field)
    policy_hash: str = Field(..., description="Hash of governance policy document (legacy)")
    governance_summary: str = Field(..., description="Plain English policy summary")
    
    # Content hashes (no plaintext PHI)
    note_hash: str = Field(..., description="SHA-256 hash of note content")
    patient_hash: Optional[str] = Field(default=None, description="SHA-256 hash of patient reference")
    reviewer_hash: Optional[str] = Field(default=None, description="SHA-256 hash of reviewer ID")
    
    # Human attestation (Courtroom Defense Mode)
    human_reviewed: bool = Field(..., description="Whether note was reviewed by clinician")
    human_reviewer_id_hash: Optional[str] = Field(default=None, description="SHA-256 hash of reviewer ID (signed field)")
    human_attested_at_utc: Optional[str] = Field(default=None, description="When human attestation occurred (ISO 8601 UTC) - signed field")
    
    # Clinical context
    encounter_id: Optional[str] = Field(default=None, description="Encounter/visit identifier")
    
    # Integrity chain
    integrity_chain: IntegrityChain = Field(..., description="Chain linkage for tamper detection")
    
    # Cryptographic signature
    signature: SignatureBundle = Field(..., description="Digital signature")


class CertificateIssuanceResponse(BaseModel):
    """Response from certificate issuance endpoint."""
    certificate_id: str = Field(..., description="Unique certificate identifier")
    certificate: DocumentationIntegrityCertificate = Field(..., description="Complete certificate")
    verify_url: str = Field(..., description="URL to verify this certificate")


# Additional models for healthcare-specific routes

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
