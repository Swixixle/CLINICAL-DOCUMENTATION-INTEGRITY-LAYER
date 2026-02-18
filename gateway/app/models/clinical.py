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
    """
    # Tenant identification
    tenant_id: str = Field(..., description="Tenant/organization identifier (REQUIRED)")
    
    # Governance metadata
    model_version: str = Field(..., description="AI model version used to generate note")
    prompt_version: str = Field(..., description="Prompt template version")
    governance_policy_version: str = Field(..., description="Governance policy version")
    
    # Clinical note content (will be hashed, not stored in plaintext)
    note_text: str = Field(..., description="Clinical note content (will be hashed)")
    
    # Review status
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
    - Human review status
    - Chain linkage (prevents tampering/insertion)
    - Signature (proves origin, prevents forgery)
    
    No plaintext PHI is included.
    """
    # Certificate identification
    certificate_id: str = Field(..., description="Unique certificate identifier")
    tenant_id: str = Field(..., description="Tenant/organization identifier")
    timestamp: str = Field(..., description="Certificate issuance timestamp (ISO 8601 UTC)")
    
    # Governance metadata
    model_version: str = Field(..., description="AI model version")
    prompt_version: str = Field(..., description="Prompt template version")
    governance_policy_version: str = Field(..., description="Governance policy version")
    
    # Content hashes (no plaintext PHI)
    note_hash: str = Field(..., description="SHA-256 hash of note content")
    patient_hash: Optional[str] = Field(default=None, description="SHA-256 hash of patient reference")
    reviewer_hash: Optional[str] = Field(default=None, description="SHA-256 hash of reviewer ID")
    
    # Clinical context
    encounter_id: Optional[str] = Field(default=None, description="Encounter/visit identifier")
    human_reviewed: bool = Field(..., description="Whether note was reviewed by clinician")
    
    # Integrity chain
    integrity_chain: IntegrityChain = Field(..., description="Chain linkage for tamper detection")
    
    # Cryptographic signature
    signature: SignatureBundle = Field(..., description="Digital signature")


class CertificateIssuanceResponse(BaseModel):
    """Response from certificate issuance endpoint."""
    certificate_id: str = Field(..., description="Unique certificate identifier")
    certificate: DocumentationIntegrityCertificate = Field(..., description="Complete certificate")
    verify_url: str = Field(..., description="URL to verify this certificate")
