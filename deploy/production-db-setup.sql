-- ============================================================================
-- Schema Version: 1.0.0  (Alembic baseline revision: a156fad5dac4)
-- Date: 2026-02-19
-- Compatibility: PostgreSQL 15+
--
-- Production Postgres Schema — Clinical Documentation Integrity Layer (CDIL)
--
-- IMPORTANT: Alembic is the authoritative source of truth for schema changes.
-- This file is kept in sync with the Alembic baseline migration as a human-
-- readable reference and a fallback for ops teams without Python tooling.
-- For all production provisioning use:
--
--   export DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/cdil
--   alembic upgrade head
--
-- To regenerate this file from the current Alembic head:
--   alembic upgrade head --sql > deploy/production-db-setup.sql
--
-- Semantic equivalence is preserved: all column names, constraints, and
-- relationships match gateway/app/db/part11_schema.sql (SQLite source) so
-- that audit event hash chains computed by gateway/app/db/part11_operations.py
-- are portable between SQLite (development/test) and Postgres (production).
--
-- FDA 21 CFR Part 11 design principles retained:
--   - Event sourcing (append-only audit_events)
--   - Hash chaining + periodic anchoring for tamper evidence
--   - PHI-safe storage (hashed pointers only)
--   - Deterministic hash canonicalization (see part11_operations.py)
-- ============================================================================

-- ============================================================================
-- 1. TENANCY & KEY MANAGEMENT
-- ============================================================================

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kms_key_ref TEXT,
    retention_policy_json TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);

CREATE TABLE IF NOT EXISTS key_rings (
    key_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    public_key TEXT NOT NULL,
    rotated_at_utc TEXT,
    retired_at_utc TEXT,
    created_at_utc TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_key_rings_tenant ON key_rings(tenant_id);
CREATE INDEX IF NOT EXISTS idx_key_rings_purpose ON key_rings(tenant_id, purpose, status);

-- ============================================================================
-- 2. ENCOUNTER & NOTE IDENTITY
-- ============================================================================

CREATE TABLE IF NOT EXISTS encounters (
    encounter_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    patient_ref_hash TEXT NOT NULL,
    encounter_time_start TEXT NOT NULL,
    encounter_time_end TEXT,
    source_system TEXT,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_encounters_tenant ON encounters(tenant_id);
CREATE INDEX IF NOT EXISTS idx_encounters_patient_hash ON encounters(patient_ref_hash);
CREATE INDEX IF NOT EXISTS idx_encounters_start_time ON encounters(encounter_time_start);

CREATE TABLE IF NOT EXISTS notes (
    note_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    encounter_id TEXT NOT NULL,
    note_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    current_version_id TEXT,
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

CREATE TABLE IF NOT EXISTS actors (
    actor_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_name TEXT,
    actor_role TEXT,
    actor_identifier_hash TEXT,
    created_at_utc TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_actors_tenant ON actors(tenant_id);
CREATE INDEX IF NOT EXISTS idx_actors_type ON actors(tenant_id, actor_type);

CREATE TABLE IF NOT EXISTS note_versions (
    version_id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    created_by_actor_id TEXT NOT NULL,
    source TEXT NOT NULL,
    content_uri TEXT,
    content_hash TEXT NOT NULL,
    prev_version_id TEXT,
    diff_from_prev_uri TEXT,
    diff_stats_json TEXT,
    FOREIGN KEY (note_id) REFERENCES notes(note_id),
    FOREIGN KEY (created_by_actor_id) REFERENCES actors(actor_id),
    FOREIGN KEY (prev_version_id) REFERENCES note_versions(version_id)
);

CREATE INDEX IF NOT EXISTS idx_note_versions_note ON note_versions(note_id);
CREATE INDEX IF NOT EXISTS idx_note_versions_created ON note_versions(created_at_utc);
CREATE INDEX IF NOT EXISTS idx_note_versions_actor ON note_versions(created_by_actor_id);

CREATE TABLE IF NOT EXISTS prompt_templates (
    template_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    template_name TEXT NOT NULL,
    template_version TEXT NOT NULL,
    template_hash TEXT NOT NULL,
    template_content TEXT,
    created_at_utc TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_prompt_templates_tenant ON prompt_templates(tenant_id);
CREATE INDEX IF NOT EXISTS idx_prompt_templates_version ON prompt_templates(tenant_id, template_version);

CREATE TABLE IF NOT EXISTS ai_generations (
    generation_id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    model_provider TEXT NOT NULL,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    prompt_template_id TEXT,
    context_snapshot_hash TEXT NOT NULL,
    context_snapshot_uri TEXT,
    output_version_id TEXT NOT NULL,
    FOREIGN KEY (note_id) REFERENCES notes(note_id),
    FOREIGN KEY (prompt_template_id) REFERENCES prompt_templates(template_id),
    FOREIGN KEY (output_version_id) REFERENCES note_versions(version_id)
);

CREATE INDEX IF NOT EXISTS idx_ai_generations_note ON ai_generations(note_id);
CREATE INDEX IF NOT EXISTS idx_ai_generations_model ON ai_generations(model_provider, model_id);
CREATE INDEX IF NOT EXISTS idx_ai_generations_created ON ai_generations(created_at_utc);

CREATE TABLE IF NOT EXISTS human_review_sessions (
    review_id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    ended_at_utc TEXT,
    duration_ms INTEGER,
    ui_surface TEXT,
    interaction_metrics_json TEXT,
    red_flag BOOLEAN DEFAULT FALSE,
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

CREATE TABLE IF NOT EXISTS attestations (
    attestation_id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    oversight_level TEXT NOT NULL,
    attestation_text TEXT NOT NULL,
    attested_at_utc TEXT NOT NULL,
    meaning TEXT NOT NULL,
    reason_for_change TEXT,
    FOREIGN KEY (note_id) REFERENCES notes(note_id),
    FOREIGN KEY (version_id) REFERENCES note_versions(version_id),
    FOREIGN KEY (actor_id) REFERENCES actors(actor_id)
);

CREATE INDEX IF NOT EXISTS idx_attestations_note ON attestations(note_id);
CREATE INDEX IF NOT EXISTS idx_attestations_version ON attestations(version_id);
CREATE INDEX IF NOT EXISTS idx_attestations_actor ON attestations(actor_id);
CREATE INDEX IF NOT EXISTS idx_attestations_attested ON attestations(attested_at_utc);

CREATE TABLE IF NOT EXISTS signatures (
    signature_id TEXT PRIMARY KEY,
    attestation_id TEXT NOT NULL,
    signature_type TEXT NOT NULL,
    signed_hash TEXT NOT NULL,
    signature_blob TEXT NOT NULL,
    certificate_chain TEXT,
    signature_time_utc TEXT NOT NULL,
    time_source TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'pending',
    verified_at_utc TEXT,
    FOREIGN KEY (attestation_id) REFERENCES attestations(attestation_id)
);

CREATE INDEX IF NOT EXISTS idx_signatures_attestation ON signatures(attestation_id);
CREATE INDEX IF NOT EXISTS idx_signatures_verification_status ON signatures(verification_status);
CREATE INDEX IF NOT EXISTS idx_signatures_time ON signatures(signature_time_utc);

-- ============================================================================
-- 5. IMMUTABLE AUDIT LEDGER (Tamper-Proof Spine)
--
-- This is the core Part 11 table. Each row's event_hash is computed as:
--   SHA-256(prev_event_hash || occurred_at_utc || object_type || object_id
--           || action || event_payload_json)
-- using the exact canonicalization in gateway/app/db/part11_operations.py.
-- Any modification to a row will cause hash verification to fail.
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    occurred_at_utc TEXT NOT NULL,
    actor_id TEXT,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    action TEXT NOT NULL,
    event_payload_json TEXT NOT NULL,
    prev_event_hash TEXT,
    event_hash TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
    FOREIGN KEY (actor_id) REFERENCES actors(actor_id)
);

CREATE INDEX IF NOT EXISTS idx_audit_events_tenant ON audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_occurred ON audit_events(occurred_at_utc);
CREATE INDEX IF NOT EXISTS idx_audit_events_object ON audit_events(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_action ON audit_events(tenant_id, action);
CREATE INDEX IF NOT EXISTS idx_audit_events_actor ON audit_events(actor_id);

CREATE TABLE IF NOT EXISTS ledger_anchors (
    anchor_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    period_start_utc TEXT NOT NULL,
    period_end_utc TEXT NOT NULL,
    merkle_root TEXT,
    chain_tip_hash TEXT,
    anchored_at_utc TEXT NOT NULL,
    anchor_method TEXT NOT NULL,
    anchor_proof TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_ledger_anchors_tenant ON ledger_anchors(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ledger_anchors_period ON ledger_anchors(period_start_utc, period_end_utc);
CREATE INDEX IF NOT EXISTS idx_ledger_anchors_anchored ON ledger_anchors(anchored_at_utc);

-- ============================================================================
-- 6. CLINICAL INDICATOR ANCHORS (Evidence Map)
-- ============================================================================

CREATE TABLE IF NOT EXISTS clinical_facts (
    fact_id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    fact_code TEXT,
    fact_value_normalized_json TEXT,
    source_ref_uri TEXT,
    source_hash TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id)
);

CREATE INDEX IF NOT EXISTS idx_clinical_facts_encounter ON clinical_facts(encounter_id);
CREATE INDEX IF NOT EXISTS idx_clinical_facts_type ON clinical_facts(fact_type);
CREATE INDEX IF NOT EXISTS idx_clinical_facts_code ON clinical_facts(fact_code);

CREATE TABLE IF NOT EXISTS note_fact_links (
    link_id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    fact_id TEXT NOT NULL,
    claim_span_json TEXT,
    strength TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS similarity_scores (
    score_id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    corpus_scope TEXT NOT NULL,
    method TEXT NOT NULL,
    uniqueness_score REAL NOT NULL,
    nearest_neighbors_json TEXT,
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

CREATE TABLE IF NOT EXISTS defense_bundles (
    bundle_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    requested_by_actor_id TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    bundle_manifest_hash TEXT NOT NULL,
    bundle_uri TEXT,
    bundle_signature_id TEXT,
    verification_instructions TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
    FOREIGN KEY (requested_by_actor_id) REFERENCES actors(actor_id),
    FOREIGN KEY (bundle_signature_id) REFERENCES signatures(signature_id)
);

CREATE INDEX IF NOT EXISTS idx_defense_bundles_tenant ON defense_bundles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_defense_bundles_created ON defense_bundles(created_at_utc);
CREATE INDEX IF NOT EXISTS idx_defense_bundles_requested_by ON defense_bundles(requested_by_actor_id);

CREATE TABLE IF NOT EXISTS bundle_items (
    bundle_item_id TEXT PRIMARY KEY,
    bundle_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    item_uri TEXT NOT NULL,
    item_hash TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (bundle_id) REFERENCES defense_bundles(bundle_id)
);

CREATE INDEX IF NOT EXISTS idx_bundle_items_bundle ON bundle_items(bundle_id);
CREATE INDEX IF NOT EXISTS idx_bundle_items_type ON bundle_items(item_type);
