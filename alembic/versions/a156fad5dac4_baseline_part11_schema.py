"""baseline_part11_schema

Revision ID: a156fad5dac4
Revises:
Create Date: 2026-02-20 01:02:42.488427

Baseline schema for CDIL — FDA 21 CFR Part 11 compliant tables.

Semantic equivalence is preserved with gateway/app/db/part11_schema.sql
(SQLite) and deploy/production-db-setup.sql (Postgres reference).  Column
names, NOT NULL constraints, and relationships are identical so that audit
event hash chains computed by gateway/app/db/part11_operations.py are
portable between SQLite (development/test) and Postgres (production).

Key design rules that MUST NOT change:
  - audit_events is append-only (no UPDATE / DELETE permitted by policy)
  - event_hash is computed over: prev_event_hash || occurred_at_utc ||
    object_type || object_id || action || event_payload_json
  - payload stored as TEXT (not JSONB) to keep hash canonicalization stable
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a156fad5dac4"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all Part 11 tables."""

    # ------------------------------------------------------------------ #
    # 1. TENANCY & KEY MANAGEMENT                                         #
    # ------------------------------------------------------------------ #

    op.create_table(
        "tenants",
        sa.Column("tenant_id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("kms_key_ref", sa.Text, nullable=True),
        sa.Column("retention_policy_json", sa.Text, nullable=True),
        sa.Column("created_at_utc", sa.Text, nullable=False),
        sa.Column("updated_at_utc", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
    )
    op.create_index("idx_tenants_status", "tenants", ["status"])

    op.create_table(
        "key_rings",
        sa.Column("key_id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("purpose", sa.Text, nullable=False),
        sa.Column("public_key", sa.Text, nullable=False),
        sa.Column("rotated_at_utc", sa.Text, nullable=True),
        sa.Column("retired_at_utc", sa.Text, nullable=True),
        sa.Column("created_at_utc", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
    )
    op.create_index("idx_key_rings_tenant", "key_rings", ["tenant_id"])
    op.create_index(
        "idx_key_rings_purpose", "key_rings", ["tenant_id", "purpose", "status"]
    )

    # ------------------------------------------------------------------ #
    # 2. ENCOUNTER & NOTE IDENTITY                                        #
    # ------------------------------------------------------------------ #

    op.create_table(
        "encounters",
        sa.Column("encounter_id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("patient_ref_hash", sa.Text, nullable=False),
        sa.Column("encounter_time_start", sa.Text, nullable=False),
        sa.Column("encounter_time_end", sa.Text, nullable=True),
        sa.Column("source_system", sa.Text, nullable=True),
        sa.Column("created_at_utc", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
    )
    op.create_index("idx_encounters_tenant", "encounters", ["tenant_id"])
    op.create_index("idx_encounters_patient_hash", "encounters", ["patient_ref_hash"])
    op.create_index("idx_encounters_start_time", "encounters", ["encounter_time_start"])

    op.create_table(
        "notes",
        sa.Column("note_id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("encounter_id", sa.Text, nullable=False),
        sa.Column("note_type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("current_version_id", sa.Text, nullable=True),
        sa.Column("created_at_utc", sa.Text, nullable=False),
        sa.Column("updated_at_utc", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.encounter_id"]),
    )
    op.create_index("idx_notes_tenant", "notes", ["tenant_id"])
    op.create_index("idx_notes_encounter", "notes", ["encounter_id"])
    op.create_index("idx_notes_status", "notes", ["tenant_id", "status"])
    op.create_index("idx_notes_type", "notes", ["tenant_id", "note_type"])

    # ------------------------------------------------------------------ #
    # 3. VERSIONING + DRAFT/FINAL DIFF                                    #
    # ------------------------------------------------------------------ #

    op.create_table(
        "actors",
        sa.Column("actor_id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("actor_type", sa.Text, nullable=False),
        sa.Column("actor_name", sa.Text, nullable=True),
        sa.Column("actor_role", sa.Text, nullable=True),
        sa.Column("actor_identifier_hash", sa.Text, nullable=True),
        sa.Column("created_at_utc", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
    )
    op.create_index("idx_actors_tenant", "actors", ["tenant_id"])
    op.create_index("idx_actors_type", "actors", ["tenant_id", "actor_type"])

    op.create_table(
        "note_versions",
        sa.Column("version_id", sa.Text, primary_key=True),
        sa.Column("note_id", sa.Text, nullable=False),
        sa.Column("created_at_utc", sa.Text, nullable=False),
        sa.Column("created_by_actor_id", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("content_uri", sa.Text, nullable=True),
        sa.Column("content_hash", sa.Text, nullable=False),
        sa.Column("prev_version_id", sa.Text, nullable=True),
        sa.Column("diff_from_prev_uri", sa.Text, nullable=True),
        sa.Column("diff_stats_json", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(["note_id"], ["notes.note_id"]),
        sa.ForeignKeyConstraint(["created_by_actor_id"], ["actors.actor_id"]),
        sa.ForeignKeyConstraint(["prev_version_id"], ["note_versions.version_id"]),
    )
    op.create_index("idx_note_versions_note", "note_versions", ["note_id"])
    op.create_index("idx_note_versions_created", "note_versions", ["created_at_utc"])
    op.create_index("idx_note_versions_actor", "note_versions", ["created_by_actor_id"])

    op.create_table(
        "prompt_templates",
        sa.Column("template_id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("template_name", sa.Text, nullable=False),
        sa.Column("template_version", sa.Text, nullable=False),
        sa.Column("template_hash", sa.Text, nullable=False),
        sa.Column("template_content", sa.Text, nullable=True),
        sa.Column("created_at_utc", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
    )
    op.create_index("idx_prompt_templates_tenant", "prompt_templates", ["tenant_id"])
    op.create_index(
        "idx_prompt_templates_version",
        "prompt_templates",
        ["tenant_id", "template_version"],
    )

    op.create_table(
        "ai_generations",
        sa.Column("generation_id", sa.Text, primary_key=True),
        sa.Column("note_id", sa.Text, nullable=False),
        sa.Column("created_at_utc", sa.Text, nullable=False),
        sa.Column("model_provider", sa.Text, nullable=False),
        sa.Column("model_id", sa.Text, nullable=False),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("prompt_template_id", sa.Text, nullable=True),
        sa.Column("context_snapshot_hash", sa.Text, nullable=False),
        sa.Column("context_snapshot_uri", sa.Text, nullable=True),
        sa.Column("output_version_id", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["notes.note_id"]),
        sa.ForeignKeyConstraint(
            ["prompt_template_id"], ["prompt_templates.template_id"]
        ),
        sa.ForeignKeyConstraint(["output_version_id"], ["note_versions.version_id"]),
    )
    op.create_index("idx_ai_generations_note", "ai_generations", ["note_id"])
    op.create_index(
        "idx_ai_generations_model",
        "ai_generations",
        ["model_provider", "model_id"],
    )
    op.create_index("idx_ai_generations_created", "ai_generations", ["created_at_utc"])

    op.create_table(
        "human_review_sessions",
        sa.Column("review_id", sa.Text, primary_key=True),
        sa.Column("note_id", sa.Text, nullable=False),
        sa.Column("actor_id", sa.Text, nullable=False),
        sa.Column("started_at_utc", sa.Text, nullable=False),
        sa.Column("ended_at_utc", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("ui_surface", sa.Text, nullable=True),
        sa.Column("interaction_metrics_json", sa.Text, nullable=True),
        sa.Column("red_flag", sa.Boolean, nullable=True, server_default="false"),
        sa.Column("red_flag_reason", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(["note_id"], ["notes.note_id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.actor_id"]),
    )
    op.create_index("idx_review_sessions_note", "human_review_sessions", ["note_id"])
    op.create_index("idx_review_sessions_actor", "human_review_sessions", ["actor_id"])
    op.create_index(
        "idx_review_sessions_started",
        "human_review_sessions",
        ["started_at_utc"],
    )
    op.create_index(
        "idx_review_sessions_red_flag",
        "human_review_sessions",
        ["red_flag"],
    )

    # ------------------------------------------------------------------ #
    # 4. ATTESTATIONS + SIGNATURES (Part 11 Core)                         #
    # ------------------------------------------------------------------ #

    op.create_table(
        "attestations",
        sa.Column("attestation_id", sa.Text, primary_key=True),
        sa.Column("note_id", sa.Text, nullable=False),
        sa.Column("version_id", sa.Text, nullable=False),
        sa.Column("actor_id", sa.Text, nullable=False),
        sa.Column("oversight_level", sa.Text, nullable=False),
        sa.Column("attestation_text", sa.Text, nullable=False),
        sa.Column("attested_at_utc", sa.Text, nullable=False),
        sa.Column("meaning", sa.Text, nullable=False),
        sa.Column("reason_for_change", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(["note_id"], ["notes.note_id"]),
        sa.ForeignKeyConstraint(["version_id"], ["note_versions.version_id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.actor_id"]),
    )
    op.create_index("idx_attestations_note", "attestations", ["note_id"])
    op.create_index("idx_attestations_version", "attestations", ["version_id"])
    op.create_index("idx_attestations_actor", "attestations", ["actor_id"])
    op.create_index("idx_attestations_attested", "attestations", ["attested_at_utc"])

    op.create_table(
        "signatures",
        sa.Column("signature_id", sa.Text, primary_key=True),
        sa.Column("attestation_id", sa.Text, nullable=False),
        sa.Column("signature_type", sa.Text, nullable=False),
        sa.Column("signed_hash", sa.Text, nullable=False),
        sa.Column("signature_blob", sa.Text, nullable=False),
        sa.Column("certificate_chain", sa.Text, nullable=True),
        sa.Column("signature_time_utc", sa.Text, nullable=False),
        sa.Column("time_source", sa.Text, nullable=False),
        sa.Column(
            "verification_status",
            sa.Text,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("verified_at_utc", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(["attestation_id"], ["attestations.attestation_id"]),
    )
    op.create_index("idx_signatures_attestation", "signatures", ["attestation_id"])
    op.create_index(
        "idx_signatures_verification_status",
        "signatures",
        ["verification_status"],
    )
    op.create_index("idx_signatures_time", "signatures", ["signature_time_utc"])

    # ------------------------------------------------------------------ #
    # 5. IMMUTABLE AUDIT LEDGER (Tamper-Proof Spine)                      #
    #                                                                     #
    # WARNING: audit_events is append-only by policy (FDA 21 CFR Part 11) #
    # Any application-layer UPDATE or DELETE on this table is a violation. #
    # payload stored as TEXT so hash canonicalization is stable across    #
    # SQLite and Postgres.                                                 #
    # ------------------------------------------------------------------ #

    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("occurred_at_utc", sa.Text, nullable=False),
        sa.Column("actor_id", sa.Text, nullable=True),
        sa.Column("object_type", sa.Text, nullable=False),
        sa.Column("object_id", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("event_payload_json", sa.Text, nullable=False),
        sa.Column("prev_event_hash", sa.Text, nullable=True),
        sa.Column("event_hash", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.actor_id"]),
    )
    op.create_index("idx_audit_events_tenant", "audit_events", ["tenant_id"])
    op.create_index("idx_audit_events_occurred", "audit_events", ["occurred_at_utc"])
    op.create_index(
        "idx_audit_events_object",
        "audit_events",
        ["object_type", "object_id"],
    )
    op.create_index("idx_audit_events_action", "audit_events", ["tenant_id", "action"])
    op.create_index("idx_audit_events_actor", "audit_events", ["actor_id"])

    op.create_table(
        "ledger_anchors",
        sa.Column("anchor_id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("period_start_utc", sa.Text, nullable=False),
        sa.Column("period_end_utc", sa.Text, nullable=False),
        sa.Column("merkle_root", sa.Text, nullable=True),
        sa.Column("chain_tip_hash", sa.Text, nullable=True),
        sa.Column("anchored_at_utc", sa.Text, nullable=False),
        sa.Column("anchor_method", sa.Text, nullable=False),
        sa.Column("anchor_proof", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
    )
    op.create_index("idx_ledger_anchors_tenant", "ledger_anchors", ["tenant_id"])
    op.create_index(
        "idx_ledger_anchors_period",
        "ledger_anchors",
        ["period_start_utc", "period_end_utc"],
    )
    op.create_index(
        "idx_ledger_anchors_anchored", "ledger_anchors", ["anchored_at_utc"]
    )

    # ------------------------------------------------------------------ #
    # 6. CLINICAL INDICATOR ANCHORS (Evidence Map)                        #
    # ------------------------------------------------------------------ #

    op.create_table(
        "clinical_facts",
        sa.Column("fact_id", sa.Text, primary_key=True),
        sa.Column("encounter_id", sa.Text, nullable=False),
        sa.Column("fact_type", sa.Text, nullable=False),
        sa.Column("fact_code", sa.Text, nullable=True),
        sa.Column("fact_value_normalized_json", sa.Text, nullable=True),
        sa.Column("source_ref_uri", sa.Text, nullable=True),
        sa.Column("source_hash", sa.Text, nullable=False),
        sa.Column("created_at_utc", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.encounter_id"]),
    )
    op.create_index("idx_clinical_facts_encounter", "clinical_facts", ["encounter_id"])
    op.create_index("idx_clinical_facts_type", "clinical_facts", ["fact_type"])
    op.create_index("idx_clinical_facts_code", "clinical_facts", ["fact_code"])

    op.create_table(
        "note_fact_links",
        sa.Column("link_id", sa.Text, primary_key=True),
        sa.Column("note_id", sa.Text, nullable=False),
        sa.Column("version_id", sa.Text, nullable=False),
        sa.Column("fact_id", sa.Text, nullable=False),
        sa.Column("claim_span_json", sa.Text, nullable=True),
        sa.Column("strength", sa.Text, nullable=False),
        sa.Column("created_at_utc", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["notes.note_id"]),
        sa.ForeignKeyConstraint(["version_id"], ["note_versions.version_id"]),
        sa.ForeignKeyConstraint(["fact_id"], ["clinical_facts.fact_id"]),
    )
    op.create_index("idx_note_fact_links_note", "note_fact_links", ["note_id"])
    op.create_index("idx_note_fact_links_version", "note_fact_links", ["version_id"])
    op.create_index("idx_note_fact_links_fact", "note_fact_links", ["fact_id"])

    # ------------------------------------------------------------------ #
    # 7. CLONING / UNIQUENESS SCORING                                     #
    # ------------------------------------------------------------------ #

    op.create_table(
        "similarity_scores",
        sa.Column("score_id", sa.Text, primary_key=True),
        sa.Column("note_id", sa.Text, nullable=False),
        sa.Column("version_id", sa.Text, nullable=False),
        sa.Column("corpus_scope", sa.Text, nullable=False),
        sa.Column("method", sa.Text, nullable=False),
        sa.Column("uniqueness_score", sa.Float, nullable=False),
        sa.Column("nearest_neighbors_json", sa.Text, nullable=True),
        sa.Column("computed_at_utc", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["notes.note_id"]),
        sa.ForeignKeyConstraint(["version_id"], ["note_versions.version_id"]),
    )
    op.create_index("idx_similarity_scores_note", "similarity_scores", ["note_id"])
    op.create_index(
        "idx_similarity_scores_version", "similarity_scores", ["version_id"]
    )
    op.create_index(
        "idx_similarity_scores_computed",
        "similarity_scores",
        ["computed_at_utc"],
    )
    op.create_index(
        "idx_similarity_scores_uniqueness",
        "similarity_scores",
        ["uniqueness_score"],
    )

    # ------------------------------------------------------------------ #
    # 8. DEFENSE BUNDLE EXPORTS (One-Click Output)                        #
    # ------------------------------------------------------------------ #

    op.create_table(
        "defense_bundles",
        sa.Column("bundle_id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("created_at_utc", sa.Text, nullable=False),
        sa.Column("requested_by_actor_id", sa.Text, nullable=False),
        sa.Column("scope_json", sa.Text, nullable=False),
        sa.Column("bundle_manifest_hash", sa.Text, nullable=False),
        sa.Column("bundle_uri", sa.Text, nullable=True),
        sa.Column("bundle_signature_id", sa.Text, nullable=True),
        sa.Column("verification_instructions", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.ForeignKeyConstraint(["requested_by_actor_id"], ["actors.actor_id"]),
        sa.ForeignKeyConstraint(["bundle_signature_id"], ["signatures.signature_id"]),
    )
    op.create_index("idx_defense_bundles_tenant", "defense_bundles", ["tenant_id"])
    op.create_index(
        "idx_defense_bundles_created", "defense_bundles", ["created_at_utc"]
    )
    op.create_index(
        "idx_defense_bundles_requested_by",
        "defense_bundles",
        ["requested_by_actor_id"],
    )

    op.create_table(
        "bundle_items",
        sa.Column("bundle_item_id", sa.Text, primary_key=True),
        sa.Column("bundle_id", sa.Text, nullable=False),
        sa.Column("item_type", sa.Text, nullable=False),
        sa.Column("item_uri", sa.Text, nullable=False),
        sa.Column("item_hash", sa.Text, nullable=False),
        sa.Column("created_at_utc", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["bundle_id"], ["defense_bundles.bundle_id"]),
    )
    op.create_index("idx_bundle_items_bundle", "bundle_items", ["bundle_id"])
    op.create_index("idx_bundle_items_type", "bundle_items", ["item_type"])


def downgrade() -> None:
    """Drop all Part 11 tables in reverse dependency order."""
    op.drop_table("bundle_items")
    op.drop_table("defense_bundles")
    op.drop_table("similarity_scores")
    op.drop_table("note_fact_links")
    op.drop_table("clinical_facts")
    op.drop_table("ledger_anchors")
    op.drop_table("audit_events")
    op.drop_table("signatures")
    op.drop_table("attestations")
    op.drop_table("human_review_sessions")
    op.drop_table("ai_generations")
    op.drop_table("prompt_templates")
    op.drop_table("note_versions")
    op.drop_table("actors")
    op.drop_table("notes")
    op.drop_table("encounters")
    op.drop_table("key_rings")
    op.drop_table("tenants")
