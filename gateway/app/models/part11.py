"""
Part 11 Compliance Models for CDIL.

These models define the data structures for FDA 21 CFR Part 11 compliant
clinical documentation integrity tracking, including:
- Tenancy & key management
- Encounter & note versioning
- AI generation tracking
- Human review sessions
- Attestations & signatures
- Immutable audit ledger
- Clinical fact anchoring
- Similarity scoring
- Defense bundle exports
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


# ============================================================================
# ENUMERATIONS
# ============================================================================


class TenantStatus(str, Enum):
    """Tenant status values."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class KeyPurpose(str, Enum):
    """Cryptographic key purpose."""
    SIGNING = "signing"
    HASHING = "hashing"
    ENCRYPTION = "encryption"


class KeyStatus(str, Enum):
    """Key status values."""
    ACTIVE = "active"
    ROTATED = "rotated"
    RETIRED = "retired"


class NoteStatus(str, Enum):
    """Note status values."""
    DRAFT = "draft"
    FINALIZED = "finalized"
    AMENDED = "amended"
    VOIDED = "voided"


class ActorType(str, Enum):
    """Actor type values."""
    HUMAN = "human"
    SYSTEM = "system"
    AI = "ai"


class VersionSource(str, Enum):
    """Note version source."""
    AI_DRAFT = "ai_draft"
    HUMAN_EDIT = "human_edit"
    IMPORT = "import"
    AMENDMENT = "amendment"


class OversightLevel(str, Enum):
    """Human oversight level for attestations."""
    VIEW_ONLY = "view_only"
    SECTION_EDIT = "section_edit"
    LINE_BY_LINE_EDIT = "line_by_line_edit"


class AttestationMeaning(str, Enum):
    """Attestation meaning/role."""
    AUTHOR = "author"
    REVIEWER = "reviewer"
    APPROVER = "approver"


class SignatureType(str, Enum):
    """Signature type values."""
    X509 = "x509"
    FIDO2 = "fido2"
    HSM = "hsm"
    ESIGN_VENDOR = "esign_vendor"


class TimeSource(str, Enum):
    """Time source for signatures."""
    RFC3161_TSA = "rfc3161_tsa"
    TRUSTED_NTP = "trusted_ntp"
    SYSTEM = "system"


class VerificationStatus(str, Enum):
    """Signature verification status."""
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AuditObjectType(str, Enum):
    """Audit event object types."""
    NOTE = "note"
    VERSION = "version"
    ATTESTATION = "attestation"
    EXPORT = "export"
    ACCESS = "access"
    POLICY = "policy"


class AuditAction(str, Enum):
    """Audit event actions."""
    CREATE = "create"
    MODIFY = "modify"
    FINALIZE = "finalize"
    SIGN = "sign"
    EXPORT = "export"
    VIEW = "view"
    DELETE_REQUESTED = "delete_requested"
    DELETE_DENIED = "delete_denied"
    LEGAL_HOLD = "legal_hold"


class AnchorMethod(str, Enum):
    """Ledger anchor method."""
    EXTERNAL_TSA = "external_tsa"
    INTERNAL_WORM = "internal_worm"
    PUBLIC_CHAIN = "public_chain_optional"


class FactType(str, Enum):
    """Clinical fact types."""
    LAB = "lab"
    VITALS = "vitals"
    DIAGNOSIS = "diagnosis"
    MED = "med"
    SYMPTOM = "symptom"
    IMAGING = "imaging"


class LinkStrength(str, Enum):
    """Note-to-fact link strength."""
    DIRECT = "direct"
    INFERRED = "inferred"
    WEAK = "weak"


class SimilarityMethod(str, Enum):
    """Similarity scoring method."""
    SIMHASH = "simhash"
    EMBEDDINGS_COSINE = "embeddings_cosine"
    SHINGLES_JACCARD = "shingles_jaccard"


class BundleItemType(str, Enum):
    """Defense bundle item types."""
    NOTE_PDF = "note_pdf"
    NOTE_JSON = "note_json"
    AUDIT_LOG = "audit_log"
    PROVENANCE = "provenance"
    DIFFS = "diffs"
    FACT_MAP = "fact_map"
    ACCESS_LOG = "access_log"
    CERTS = "certs"


# ============================================================================
# TENANCY & KEY MANAGEMENT
# ============================================================================


class RetentionPolicy(BaseModel):
    """Retention policy configuration."""
    years: int = Field(..., description="Years to retain records")
    legal_hold_rules: Dict[str, Any] = Field(
        default_factory=dict, description="Legal hold rules"
    )


class Tenant(BaseModel):
    """Tenant/organization model."""
    tenant_id: str = Field(..., description="Unique tenant identifier")
    name: str = Field(..., description="Tenant name")
    kms_key_ref: Optional[str] = Field(None, description="KMS/HSM key reference")
    retention_policy: Optional[RetentionPolicy] = Field(
        None, description="Retention policy"
    )
    created_at_utc: str = Field(..., description="Creation timestamp (ISO 8601 UTC)")
    updated_at_utc: str = Field(..., description="Update timestamp (ISO 8601 UTC)")
    status: TenantStatus = Field(default=TenantStatus.ACTIVE, description="Tenant status")


class KeyRing(BaseModel):
    """Cryptographic key ring entry."""
    key_id: str = Field(..., description="Unique key identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    purpose: KeyPurpose = Field(..., description="Key purpose")
    public_key: str = Field(..., description="Public key (PEM or JWK)")
    rotated_at_utc: Optional[str] = Field(
        None, description="Rotation timestamp (ISO 8601 UTC)"
    )
    retired_at_utc: Optional[str] = Field(
        None, description="Retirement timestamp (ISO 8601 UTC)"
    )
    created_at_utc: str = Field(..., description="Creation timestamp (ISO 8601 UTC)")
    status: KeyStatus = Field(default=KeyStatus.ACTIVE, description="Key status")


# ============================================================================
# ENCOUNTER & NOTE IDENTITY
# ============================================================================


class Encounter(BaseModel):
    """Clinical encounter model."""
    encounter_id: str = Field(..., description="Unique encounter identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    patient_ref_hash: str = Field(..., description="SHA-256 hash of patient ID + salt")
    encounter_time_start: str = Field(
        ..., description="Encounter start time (ISO 8601 UTC)"
    )
    encounter_time_end: Optional[str] = Field(
        None, description="Encounter end time (ISO 8601 UTC)"
    )
    source_system: Optional[str] = Field(None, description="Source EHR system")
    created_at_utc: str = Field(..., description="Creation timestamp (ISO 8601 UTC)")


class Note(BaseModel):
    """Clinical note identity and current state."""
    note_id: str = Field(..., description="Unique note identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    encounter_id: str = Field(..., description="Encounter identifier")
    note_type: str = Field(..., description="Note type (progress, discharge, etc.)")
    status: NoteStatus = Field(default=NoteStatus.DRAFT, description="Note status")
    current_version_id: Optional[str] = Field(
        None, description="Current version identifier"
    )
    created_at_utc: str = Field(..., description="Creation timestamp (ISO 8601 UTC)")
    updated_at_utc: str = Field(..., description="Update timestamp (ISO 8601 UTC)")


# ============================================================================
# VERSIONING + ACTORS
# ============================================================================


class Actor(BaseModel):
    """User or system actor for audit trail."""
    actor_id: str = Field(..., description="Unique actor identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    actor_type: ActorType = Field(..., description="Actor type")
    actor_name: Optional[str] = Field(None, description="Actor name")
    actor_role: Optional[str] = Field(None, description="Actor role")
    actor_identifier_hash: Optional[str] = Field(
        None, description="Hashed external identifier"
    )
    created_at_utc: str = Field(..., description="Creation timestamp (ISO 8601 UTC)")
    status: str = Field(default="active", description="Actor status")


class DiffStats(BaseModel):
    """Statistics for version diff."""
    chars_added: int = Field(..., description="Characters added")
    chars_removed: int = Field(..., description="Characters removed")
    lines_changed: int = Field(..., description="Lines changed")


class NoteVersion(BaseModel):
    """Note version with hash chaining."""
    version_id: str = Field(..., description="Unique version identifier")
    note_id: str = Field(..., description="Note identifier")
    created_at_utc: str = Field(..., description="Creation timestamp (ISO 8601 UTC)")
    created_by_actor_id: str = Field(..., description="Actor who created this version")
    source: VersionSource = Field(..., description="Version source")
    content_uri: Optional[str] = Field(None, description="Encrypted content URI")
    content_hash: str = Field(..., description="SHA-256 of content")
    prev_version_id: Optional[str] = Field(None, description="Previous version ID")
    diff_from_prev_uri: Optional[str] = Field(None, description="Diff/patch URI")
    diff_stats: Optional[DiffStats] = Field(None, description="Diff statistics")


class PromptTemplate(BaseModel):
    """Prompt template version tracking."""
    template_id: str = Field(..., description="Unique template identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    template_name: str = Field(..., description="Template name")
    template_version: str = Field(..., description="Template version")
    template_hash: str = Field(..., description="SHA-256 of template content")
    template_content: Optional[str] = Field(None, description="Template text")
    created_at_utc: str = Field(..., description="Creation timestamp (ISO 8601 UTC)")
    status: str = Field(default="active", description="Template status")


class AIGeneration(BaseModel):
    """AI model generation tracking."""
    generation_id: str = Field(..., description="Unique generation identifier")
    note_id: str = Field(..., description="Note identifier")
    created_at_utc: str = Field(..., description="Creation timestamp (ISO 8601 UTC)")
    model_provider: str = Field(..., description="AI provider (openai, anthropic, etc.)")
    model_id: str = Field(..., description="Model ID (gpt-4, claude-3, etc.)")
    model_version: str = Field(..., description="Model version")
    prompt_template_id: Optional[str] = Field(None, description="Prompt template ID")
    context_snapshot_hash: str = Field(..., description="SHA-256 of context window")
    context_snapshot_uri: Optional[str] = Field(
        None, description="Encrypted context URI"
    )
    output_version_id: str = Field(..., description="Output version ID (AI draft)")


class InteractionMetrics(BaseModel):
    """Human review interaction metrics."""
    scroll_depth: Optional[float] = Field(None, description="Scroll depth percentage")
    keystrokes: Optional[int] = Field(None, description="Keystroke count")
    focus_events: Optional[int] = Field(None, description="Focus event count")


class HumanReviewSession(BaseModel):
    """Human review session tracking."""
    review_id: str = Field(..., description="Unique review identifier")
    note_id: str = Field(..., description="Note identifier")
    actor_id: str = Field(..., description="Reviewer actor ID")
    started_at_utc: str = Field(..., description="Start timestamp (ISO 8601 UTC)")
    ended_at_utc: Optional[str] = Field(None, description="End timestamp (ISO 8601 UTC)")
    duration_ms: Optional[int] = Field(None, description="Duration in milliseconds")
    ui_surface: Optional[str] = Field(None, description="UI surface (web, mobile, etc.)")
    interaction_metrics: Optional[InteractionMetrics] = Field(
        None, description="Interaction metrics"
    )
    red_flag: bool = Field(default=False, description="Risk flag indicator")
    red_flag_reason: Optional[str] = Field(None, description="Risk flag reason")


# ============================================================================
# ATTESTATIONS + SIGNATURES
# ============================================================================


class Attestation(BaseModel):
    """Human attestation record."""
    attestation_id: str = Field(..., description="Unique attestation identifier")
    note_id: str = Field(..., description="Note identifier")
    version_id: str = Field(..., description="Version being attested")
    actor_id: str = Field(..., description="Attesting actor ID")
    oversight_level: OversightLevel = Field(..., description="Oversight level")
    attestation_text: str = Field(..., description="Attestation text shown to user")
    attested_at_utc: str = Field(..., description="Attestation timestamp (ISO 8601 UTC)")
    meaning: AttestationMeaning = Field(..., description="Attestation meaning")
    reason_for_change: Optional[str] = Field(None, description="Reason for change/amendment")


class Signature(BaseModel):
    """Cryptographic signature record."""
    signature_id: str = Field(..., description="Unique signature identifier")
    attestation_id: str = Field(..., description="Attestation identifier")
    signature_type: SignatureType = Field(..., description="Signature type")
    signed_hash: str = Field(..., description="SHA-256 of attestation payload")
    signature_blob: str = Field(..., description="Base64 encoded signature")
    certificate_chain: Optional[str] = Field(None, description="PEM certificate chain")
    signature_time_utc: str = Field(..., description="Signature timestamp (ISO 8601 UTC)")
    time_source: TimeSource = Field(..., description="Time source")
    verification_status: VerificationStatus = Field(
        default=VerificationStatus.PENDING, description="Verification status"
    )
    verified_at_utc: Optional[str] = Field(
        None, description="Verification timestamp (ISO 8601 UTC)"
    )


# ============================================================================
# IMMUTABLE AUDIT LEDGER
# ============================================================================


class AuditEvent(BaseModel):
    """Append-only audit event with hash chaining."""
    event_id: str = Field(..., description="Unique event identifier (ULID)")
    tenant_id: str = Field(..., description="Tenant identifier")
    occurred_at_utc: str = Field(..., description="Event timestamp (ISO 8601 UTC)")
    actor_id: Optional[str] = Field(None, description="Actor ID (null for system)")
    object_type: AuditObjectType = Field(..., description="Object type")
    object_id: str = Field(..., description="Object identifier")
    action: AuditAction = Field(..., description="Action performed")
    event_payload: Dict[str, Any] = Field(..., description="Event payload (no PHI)")
    prev_event_hash: Optional[str] = Field(None, description="Previous event hash")
    event_hash: str = Field(..., description="This event hash")


class LedgerAnchor(BaseModel):
    """Periodic ledger anchor for tamper evidence."""
    anchor_id: str = Field(..., description="Unique anchor identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    period_start_utc: str = Field(..., description="Period start (ISO 8601 UTC)")
    period_end_utc: str = Field(..., description="Period end (ISO 8601 UTC)")
    merkle_root: Optional[str] = Field(None, description="Merkle root hash")
    chain_tip_hash: Optional[str] = Field(None, description="Chain tip hash")
    anchored_at_utc: str = Field(..., description="Anchor timestamp (ISO 8601 UTC)")
    anchor_method: AnchorMethod = Field(..., description="Anchor method")
    anchor_proof: Optional[str] = Field(None, description="Anchor proof (TSA receipt, etc.)")


# ============================================================================
# CLINICAL INDICATOR ANCHORS
# ============================================================================


class ClinicalFact(BaseModel):
    """Structured clinical fact reference."""
    fact_id: str = Field(..., description="Unique fact identifier")
    encounter_id: str = Field(..., description="Encounter identifier")
    fact_type: FactType = Field(..., description="Fact type")
    fact_code: Optional[str] = Field(None, description="LOINC/SNOMED/ICD code")
    fact_value_normalized: Optional[Dict[str, Any]] = Field(
        None, description="Normalized value"
    )
    source_ref_uri: Optional[str] = Field(None, description="Source reference URI")
    source_hash: str = Field(..., description="SHA-256 of source data")
    created_at_utc: str = Field(..., description="Creation timestamp (ISO 8601 UTC)")


class ClaimSpan(BaseModel):
    """Span of text in note making a claim."""
    start_char: int = Field(..., description="Start character position")
    end_char: int = Field(..., description="End character position")


class NoteFactLink(BaseModel):
    """Link between note and clinical fact."""
    link_id: str = Field(..., description="Unique link identifier")
    note_id: str = Field(..., description="Note identifier")
    version_id: str = Field(..., description="Version identifier")
    fact_id: str = Field(..., description="Fact identifier")
    claim_span: Optional[ClaimSpan] = Field(None, description="Text span in note")
    strength: LinkStrength = Field(..., description="Link strength")
    created_at_utc: str = Field(..., description="Creation timestamp (ISO 8601 UTC)")


# ============================================================================
# SIMILARITY SCORING
# ============================================================================


class NearestNeighbor(BaseModel):
    """Nearest neighbor for similarity analysis."""
    note_id: str = Field(..., description="Neighbor note ID")
    similarity: float = Field(..., description="Similarity score (0.0-1.0)")


class SimilarityScore(BaseModel):
    """Note uniqueness/similarity score."""
    score_id: str = Field(..., description="Unique score identifier")
    note_id: str = Field(..., description="Note identifier")
    version_id: str = Field(..., description="Version identifier")
    corpus_scope: str = Field(..., description="Corpus scope (e.g., provider_last_50)")
    method: SimilarityMethod = Field(..., description="Similarity method")
    uniqueness_score: float = Field(..., description="Uniqueness score (0.0-1.0)")
    nearest_neighbors: List[NearestNeighbor] = Field(
        default_factory=list, description="Nearest neighbors"
    )
    computed_at_utc: str = Field(..., description="Computation timestamp (ISO 8601 UTC)")


# ============================================================================
# DEFENSE BUNDLE EXPORTS
# ============================================================================


class BundleScope(BaseModel):
    """Defense bundle scope specification."""
    note_ids: Optional[List[str]] = Field(None, description="Specific note IDs")
    date_range: Optional[Dict[str, str]] = Field(None, description="Date range filter")
    payer_request_id: Optional[str] = Field(None, description="Payer request ID")
    subpoena_id: Optional[str] = Field(None, description="Subpoena ID")


class DefenseBundle(BaseModel):
    """Defense bundle export record."""
    bundle_id: str = Field(..., description="Unique bundle identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    created_at_utc: str = Field(..., description="Creation timestamp (ISO 8601 UTC)")
    requested_by_actor_id: str = Field(..., description="Requesting actor ID")
    scope: BundleScope = Field(..., description="Bundle scope")
    bundle_manifest_hash: str = Field(..., description="SHA-256 of manifest")
    bundle_uri: Optional[str] = Field(None, description="Bundle ZIP URI")
    bundle_signature_id: Optional[str] = Field(None, description="Bundle signature ID")
    verification_instructions: Optional[str] = Field(
        None, description="Verification instructions"
    )


class BundleItem(BaseModel):
    """Individual item in defense bundle."""
    bundle_item_id: str = Field(..., description="Unique item identifier")
    bundle_id: str = Field(..., description="Bundle identifier")
    item_type: BundleItemType = Field(..., description="Item type")
    item_uri: str = Field(..., description="Item URI")
    item_hash: str = Field(..., description="SHA-256 of item content")
    created_at_utc: str = Field(..., description="Creation timestamp (ISO 8601 UTC)")


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================


class CreateEncounterRequest(BaseModel):
    """Request to create an encounter."""
    patient_id: str = Field(..., description="Patient identifier (will be hashed)")
    encounter_time_start: str = Field(..., description="Start time (ISO 8601 UTC)")
    encounter_time_end: Optional[str] = Field(None, description="End time (ISO 8601 UTC)")
    source_system: Optional[str] = Field(None, description="Source EHR system")


class CreateNoteRequest(BaseModel):
    """Request to create a note."""
    encounter_id: str = Field(..., description="Encounter identifier")
    note_type: str = Field(..., description="Note type")
    note_text: str = Field(..., description="Note content")
    ai_provider: Optional[str] = Field(None, description="AI provider")
    model_id: Optional[str] = Field(None, description="Model ID")
    model_version: Optional[str] = Field(None, description="Model version")


class CreateAttestationRequest(BaseModel):
    """Request to create an attestation."""
    note_id: str = Field(..., description="Note identifier")
    version_id: str = Field(..., description="Version identifier")
    oversight_level: OversightLevel = Field(..., description="Oversight level")
    attestation_text: str = Field(..., description="Attestation text")
    meaning: AttestationMeaning = Field(..., description="Attestation meaning")
    reason_for_change: Optional[str] = Field(None, description="Reason for change")


class CreateDefenseBundleRequest(BaseModel):
    """Request to create a defense bundle."""
    scope: BundleScope = Field(..., description="Bundle scope")
    verification_instructions: Optional[str] = Field(
        None, description="Verification instructions"
    )
