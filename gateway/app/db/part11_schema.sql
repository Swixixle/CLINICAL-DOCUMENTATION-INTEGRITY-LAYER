-- ============================================================================
-- Part 11 Compliant Clinical Documentation Integrity Schema
-- ============================================================================
-- This schema implements FDA 21 CFR Part 11 requirements for:
-- 1. Secure, computer-generated, time-stamped audit trails
-- 2. Binding electronic signatures
-- 3. Record retention & retrievability
-- 4. Tamper-evident event ledger with hash chaining
-- 
-- Design principles:
-- - Event sourcing (append-only, no overwrites)
-- - Hash chaining + periodic anchoring for tamper evidence
-- - Signatures as first-class objects
-- - PHI-safe storage (hashed pointers only)
-- ============================================================================

-- ============================================================================
-- 1. TENANCY & KEY MANAGEMENT
-- ============================================================================

-- Tenants table: Multi-tenant isolation with retention policies
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kms_key_ref TEXT,  -- Pointer to KMS/HSM key
    retention_policy_json TEXT,  -- JSON: {years: int, legal_hold_rules: {}}
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'  -- active, suspended, deleted
);

CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);

-- Key rings table: Cryptographic key management per tenant
CREATE TABLE IF NOT EXISTS key_rings (
    key_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    purpose TEXT NOT NULL,  -- signing, hashing, encryption
    public_key TEXT NOT NULL,
    rotated_at_utc TEXT,
    retired_at_utc TEXT,
    created_at_utc TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',  -- active, rotated, retired
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_key_rings_tenant ON key_rings(tenant_id);
CREATE INDEX IF NOT EXISTS idx_key_rings_purpose ON key_rings(tenant_id, purpose, status);

-- ============================================================================
-- 2. ENCOUNTER & NOTE IDENTITY
-- ============================================================================

-- Encounters table: Clinical encounter tracking
CREATE TABLE IF NOT EXISTS encounters (
    encounter_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    patient_ref_hash TEXT NOT NULL,  -- SHA-256 of patient ID + tenant salt
    encounter_time_start TEXT NOT NULL,  -- ISO 8601 UTC
    encounter_time_end TEXT,  -- ISO 8601 UTC, NULL if ongoing
    source_system TEXT,  -- EHR vendor identifier
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_encounters_tenant ON encounters(tenant_id);
CREATE INDEX IF NOT EXISTS idx_encounters_patient_hash ON encounters(patient_ref_hash);
CREATE INDEX IF NOT EXISTS idx_encounters_start_time ON encounters(encounter_time_start);

-- Notes table: Clinical note identity and current state
CREATE TABLE IF NOT EXISTS notes (
    note_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    encounter_id TEXT NOT NULL,
    note_type TEXT NOT NULL,  -- progress, discharge, consult, etc.
    status TEXT NOT NULL DEFAULT 'draft',  -- draft, finalized, amended, voided
    current_version_id TEXT,  -- FK to note_versions
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
    FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id)
);

CREATE INDEX IF NOT EXISTS idx_notes_tenant ON notes(tenant_id);
CREATE INDEX IF NOT EXISTS idx_notes_encounter ON notes(encounter_id);
CREATE INDEX IF NOT EXISTS idx_notes_status ON notes(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_notes_type ON notes(tenant_id, note_type);

-- ============================================================================
-- 3. VERSIONING + DRAFT/FINAL DIFF
-- ============================================================================

-- Actors table: User/system actors for audit trail
CREATE TABLE IF NOT EXISTS actors (
    actor_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    actor_type TEXT NOT NULL,  -- human, system, ai
    actor_name TEXT,
    actor_role TEXT,  -- physician, nurse, scribe, ai_model
    actor_identifier_hash TEXT,  -- Hashed external identifier
    created_at_utc TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_actors_tenant ON actors(tenant_id);
CREATE INDEX IF NOT EXISTS idx_actors_type ON actors(tenant_id, actor_type);

-- Note versions table: Full version history with hash chaining
CREATE TABLE IF NOT EXISTS note_versions (
    version_id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    created_by_actor_id TEXT NOT NULL,
    source TEXT NOT NULL,  -- ai_draft, human_edit, import, amendment
    content_uri TEXT,  -- Pointer to encrypted blob storage
    content_hash TEXT NOT NULL,  -- SHA-256 of canonicalized content
    prev_version_id TEXT,  -- FK to note_versions for per-note hash chain
    diff_from_prev_uri TEXT,  -- Optional: store patch/diff
    diff_stats_json TEXT,  -- JSON: {chars_added, chars_removed, lines_changed}
    FOREIGN KEY (note_id) REFERENCES notes(note_id),
    FOREIGN KEY (created_by_actor_id) REFERENCES actors(actor_id),
    FOREIGN KEY (prev_version_id) REFERENCES note_versions(version_id)
);

CREATE INDEX IF NOT EXISTS idx_note_versions_note ON note_versions(note_id);
CREATE INDEX IF NOT EXISTS idx_note_versions_created ON note_versions(created_at_utc);
CREATE INDEX IF NOT EXISTS idx_note_versions_actor ON note_versions(created_by_actor_id);

-- Prompt templates table: Track prompt template versions
CREATE TABLE IF NOT EXISTS prompt_templates (
    template_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    template_name TEXT NOT NULL,
    template_version TEXT NOT NULL,
    template_hash TEXT NOT NULL,  -- SHA-256 of template content
    template_content TEXT,  -- Optional: store template text
    created_at_utc TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_prompt_templates_tenant ON prompt_templates(tenant_id);
CREATE INDEX IF NOT EXISTS idx_prompt_templates_version ON prompt_templates(tenant_id, template_version);

-- AI generations table: Track AI model generations
CREATE TABLE IF NOT EXISTS ai_generations (
    generation_id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    model_provider TEXT NOT NULL,  -- openai, anthropic, etc.
    model_id TEXT NOT NULL,  -- gpt-4, claude-3, etc.
    model_version TEXT NOT NULL,
    prompt_template_id TEXT,
    context_snapshot_hash TEXT NOT NULL,  -- SHA-256 of context window
    context_snapshot_uri TEXT,  -- Optional: encrypted blob storage
    output_version_id TEXT NOT NULL,  -- FK to note_versions (the AI draft)
    FOREIGN KEY (note_id) REFERENCES notes(note_id),
    FOREIGN KEY (prompt_template_id) REFERENCES prompt_templates(template_id),
    FOREIGN KEY (output_version_id) REFERENCES note_versions(version_id)
);

CREATE INDEX IF NOT EXISTS idx_ai_generations_note ON ai_generations(note_id);
CREATE INDEX IF NOT EXISTS idx_ai_generations_model ON ai_generations(model_provider, model_id);
CREATE INDEX IF NOT EXISTS idx_ai_generations_created ON ai_generations(created_at_utc);

-- Human review sessions table: Track review duration and interaction
CREATE TABLE IF NOT EXISTS human_review_sessions (
    review_id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    ended_at_utc TEXT,
    duration_ms INTEGER,  -- Computed from start/end
    ui_surface TEXT,  -- web, mobile, ehr_embed
    interaction_metrics_json TEXT,  -- JSON: {scroll_depth, keystrokes, focus_events}
    red_flag BOOLEAN DEFAULT 0,  -- Risk indicator
    red_flag_reason TEXT,
    FOREIGN KEY (note_id) REFERENCES notes(note_id),
    FOREIGN KEY (actor_id) REFERENCES actors(actor_id)
);

CREATE INDEX IF NOT EXISTS idx_review_sessions_note ON human_review_sessions(note_id);
CREATE INDEX IF NOT EXISTS idx_review_sessions_actor ON human_review_sessions(actor_id);
CREATE INDEX IF NOT EXISTS idx_review_sessions_started ON human_review_sessions(started_at_utc);
CREATE INDEX IF NOT EXISTS idx_review_sessions_red_flag ON human_review_sessions(red_flag);

-- ============================================================================
-- 4. ATTESTATIONS + SIGNATURES (Part 11 Core)
-- ============================================================================

-- Attestations table: Human attestation records
CREATE TABLE IF NOT EXISTS attestations (
    attestation_id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL,
    version_id TEXT NOT NULL,  -- What exactly is being attested to
    actor_id TEXT NOT NULL,
    oversight_level TEXT NOT NULL,  -- view_only, section_edit, line_by_line_edit
    attestation_text TEXT NOT NULL,  -- Exact language shown at signing
    attested_at_utc TEXT NOT NULL,
    meaning TEXT NOT NULL,  -- author, reviewer, approver
    reason_for_change TEXT,  -- Required for amendments
    FOREIGN KEY (note_id) REFERENCES notes(note_id),
    FOREIGN KEY (version_id) REFERENCES note_versions(version_id),
    FOREIGN KEY (actor_id) REFERENCES actors(actor_id)
);

CREATE INDEX IF NOT EXISTS idx_attestations_note ON attestations(note_id);
CREATE INDEX IF NOT EXISTS idx_attestations_version ON attestations(version_id);
CREATE INDEX IF NOT EXISTS idx_attestations_actor ON attestations(actor_id);
CREATE INDEX IF NOT EXISTS idx_attestations_attested ON attestations(attested_at_utc);

-- Signatures table: Cryptographic signatures for attestations
CREATE TABLE IF NOT EXISTS signatures (
    signature_id TEXT PRIMARY KEY,
    attestation_id TEXT NOT NULL,
    signature_type TEXT NOT NULL,  -- x509, fido2, hsm, esign_vendor
    signed_hash TEXT NOT NULL,  -- SHA-256 of canonical attestation payload
    signature_blob TEXT NOT NULL,  -- Base64 encoded signature
    certificate_chain TEXT,  -- PEM chain or pointer
    signature_time_utc TEXT NOT NULL,
    time_source TEXT NOT NULL,  -- rfc3161_tsa, trusted_ntp, system
    verification_status TEXT NOT NULL DEFAULT 'pending',  -- valid, invalid, expired, revoked
    verified_at_utc TEXT,
    FOREIGN KEY (attestation_id) REFERENCES attestations(attestation_id)
);

CREATE INDEX IF NOT EXISTS idx_signatures_attestation ON signatures(attestation_id);
CREATE INDEX IF NOT EXISTS idx_signatures_verification_status ON signatures(verification_status);
CREATE INDEX IF NOT EXISTS idx_signatures_time ON signatures(signature_time_utc);

-- ============================================================================
-- 5. IMMUTABLE AUDIT LEDGER (Tamper-Proof Spine)
-- ============================================================================

-- Audit events table: Append-only event ledger with hash chaining
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,  -- ULID recommended for ordering
    tenant_id TEXT NOT NULL,
    occurred_at_utc TEXT NOT NULL,
    actor_id TEXT,  -- NULL for system events
    object_type TEXT NOT NULL,  -- note, version, attestation, export, access, policy
    object_id TEXT NOT NULL,
    action TEXT NOT NULL,  -- create, modify, finalize, sign, export, view, delete_requested, etc.
    event_payload_json TEXT NOT NULL,  -- JSON with NO PHI, only refs/hashes
    prev_event_hash TEXT,  -- Hash of previous event in chain
    event_hash TEXT NOT NULL,  -- hash(prev_event_hash + payload + metadata)
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
    FOREIGN KEY (actor_id) REFERENCES actors(actor_id)
);

CREATE INDEX IF NOT EXISTS idx_audit_events_tenant ON audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_occurred ON audit_events(occurred_at_utc);
CREATE INDEX IF NOT EXISTS idx_audit_events_object ON audit_events(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_action ON audit_events(tenant_id, action);
CREATE INDEX IF NOT EXISTS idx_audit_events_actor ON audit_events(actor_id);

-- Ledger anchors table: Periodic Merkle roots for tamper evidence
CREATE TABLE IF NOT EXISTS ledger_anchors (
    anchor_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    period_start_utc TEXT NOT NULL,
    period_end_utc TEXT NOT NULL,
    merkle_root TEXT,  -- Merkle root hash
    chain_tip_hash TEXT,  -- Alternative: chain tip hash
    anchored_at_utc TEXT NOT NULL,
    anchor_method TEXT NOT NULL,  -- external_tsa, internal_worm, public_chain_optional
    anchor_proof TEXT,  -- TSA receipt or other proof
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_ledger_anchors_tenant ON ledger_anchors(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ledger_anchors_period ON ledger_anchors(period_start_utc, period_end_utc);
CREATE INDEX IF NOT EXISTS idx_ledger_anchors_anchored ON ledger_anchors(anchored_at_utc);

-- ============================================================================
-- 6. CLINICAL INDICATOR ANCHORS (Evidence Map)
-- ============================================================================

-- Clinical facts table: Structured clinical data references
CREATE TABLE IF NOT EXISTS clinical_facts (
    fact_id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL,
    fact_type TEXT NOT NULL,  -- lab, vitals, diagnosis, med, symptom, imaging
    fact_code TEXT,  -- LOINC/SNOMED/ICD code
    fact_value_normalized_json TEXT,  -- JSON representation of value
    source_ref_uri TEXT,  -- Pointer to EHR export / FHIR resource
    source_hash TEXT NOT NULL,  -- SHA-256 of source data
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id)
);

CREATE INDEX IF NOT EXISTS idx_clinical_facts_encounter ON clinical_facts(encounter_id);
CREATE INDEX IF NOT EXISTS idx_clinical_facts_type ON clinical_facts(fact_type);
CREATE INDEX IF NOT EXISTS idx_clinical_facts_code ON clinical_facts(fact_code);

-- Note fact links table: Links between notes and clinical facts
CREATE TABLE IF NOT EXISTS note_fact_links (
    link_id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    fact_id TEXT NOT NULL,
    claim_span_json TEXT,  -- JSON: {start_char, end_char} - where in note
    strength TEXT NOT NULL,  -- direct, inferred, weak
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (note_id) REFERENCES notes(note_id),
    FOREIGN KEY (version_id) REFERENCES note_versions(version_id),
    FOREIGN KEY (fact_id) REFERENCES clinical_facts(fact_id)
);

CREATE INDEX IF NOT EXISTS idx_note_fact_links_note ON note_fact_links(note_id);
CREATE INDEX IF NOT EXISTS idx_note_fact_links_version ON note_fact_links(version_id);
CREATE INDEX IF NOT EXISTS idx_note_fact_links_fact ON note_fact_links(fact_id);

-- ============================================================================
-- 7. CLONING / UNIQUENESS SCORING
-- ============================================================================

-- Similarity scores table: Track note uniqueness and cloning detection
CREATE TABLE IF NOT EXISTS similarity_scores (
    score_id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    corpus_scope TEXT NOT NULL,  -- provider_last_50, clinic_last_500
    method TEXT NOT NULL,  -- simhash, embeddings_cosine, shingles_jaccard
    uniqueness_score REAL NOT NULL,  -- 0.0 to 1.0
    nearest_neighbors_json TEXT,  -- JSON: [{note_id, similarity}, ...]
    computed_at_utc TEXT NOT NULL,
    FOREIGN KEY (note_id) REFERENCES notes(note_id),
    FOREIGN KEY (version_id) REFERENCES note_versions(version_id)
);

CREATE INDEX IF NOT EXISTS idx_similarity_scores_note ON similarity_scores(note_id);
CREATE INDEX IF NOT EXISTS idx_similarity_scores_version ON similarity_scores(version_id);
CREATE INDEX IF NOT EXISTS idx_similarity_scores_computed ON similarity_scores(computed_at_utc);
CREATE INDEX IF NOT EXISTS idx_similarity_scores_uniqueness ON similarity_scores(uniqueness_score);

-- ============================================================================
-- 8. DEFENSE BUNDLE EXPORTS (One-Click Output)
-- ============================================================================

-- Defense bundles table: Exportable evidence packages
CREATE TABLE IF NOT EXISTS defense_bundles (
    bundle_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    requested_by_actor_id TEXT NOT NULL,
    scope_json TEXT NOT NULL,  -- JSON: {note_ids, date_range, payer_request_id, subpoena_id}
    bundle_manifest_hash TEXT NOT NULL,  -- SHA-256 of manifest
    bundle_uri TEXT,  -- Pointer to ZIP in WORM storage
    bundle_signature_id TEXT,  -- FK to signatures (org signing the export)
    verification_instructions TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
    FOREIGN KEY (requested_by_actor_id) REFERENCES actors(actor_id),
    FOREIGN KEY (bundle_signature_id) REFERENCES signatures(signature_id)
);

CREATE INDEX IF NOT EXISTS idx_defense_bundles_tenant ON defense_bundles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_defense_bundles_created ON defense_bundles(created_at_utc);
CREATE INDEX IF NOT EXISTS idx_defense_bundles_requested_by ON defense_bundles(requested_by_actor_id);

-- Bundle items table: Individual items within a defense bundle
CREATE TABLE IF NOT EXISTS bundle_items (
    bundle_item_id TEXT PRIMARY KEY,
    bundle_id TEXT NOT NULL,
    item_type TEXT NOT NULL,  -- note_pdf, note_json, audit_log, provenance, diffs, fact_map, etc.
    item_uri TEXT NOT NULL,
    item_hash TEXT NOT NULL,  -- SHA-256 of item content
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (bundle_id) REFERENCES defense_bundles(bundle_id)
);

CREATE INDEX IF NOT EXISTS idx_bundle_items_bundle ON bundle_items(bundle_id);
CREATE INDEX IF NOT EXISTS idx_bundle_items_type ON bundle_items(item_type);
