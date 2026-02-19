# Part 11 Compliance Implementation Guide

## Overview

This document describes the FDA 21 CFR Part 11 compliant implementation in CDIL (Clinical Documentation Integrity Layer). The implementation provides secure, tamper-evident audit trails, binding electronic signatures, and record retention capabilities for AI-generated clinical documentation.

## Core Compliance Requirements

### 21 CFR Part 11 Requirements

The implementation addresses these key Part 11 requirements:

1. **§11.10(a) - Validation of systems**: Database schema ensures data integrity through hash chaining and foreign key constraints
2. **§11.10(c) - Secure audit trails**: Append-only audit_events table with hash chaining prevents tampering
3. **§11.10(e) - Timestamping**: All events include ISO 8601 UTC timestamps with configurable time sources
4. **§11.10(k)(1) - Change tracking**: note_versions table maintains complete version history
4. **§11.50 - Electronic signatures**: signatures table implements binding electronic signatures with certificate chains
5. **§11.70 - Signature uniqueness**: Per-tenant signing keys prevent cross-tenant forgery

## Architecture

### Database Schema

The Part 11 compliant schema consists of 13 tables organized into functional groups:

#### 1. Tenancy & Key Management
- **tenants**: Multi-tenant isolation with retention policies
- **key_rings**: Cryptographic key management per tenant

#### 2. Encounter & Note Identity
- **encounters**: Clinical encounter tracking with hashed patient references
- **notes**: Clinical note identity and current state
- **actors**: User/system actors for audit trail

#### 3. Versioning & Provenance
- **note_versions**: Full version history with hash chaining
- **prompt_templates**: AI prompt template tracking
- **ai_generations**: AI model generation provenance
- **human_review_sessions**: Human review duration and interaction metrics

#### 4. Attestations & Signatures
- **attestations**: Human attestation records
- **signatures**: Cryptographic signatures with verification status

#### 5. Immutable Audit Ledger
- **audit_events**: Append-only event ledger with hash chaining
- **ledger_anchors**: Periodic Merkle roots for tamper evidence

#### 6. Clinical Evidence
- **clinical_facts**: Structured clinical data references
- **note_fact_links**: Links between notes and clinical evidence

#### 7. Quality Metrics
- **similarity_scores**: Note uniqueness and cloning detection

#### 8. Defense Bundles
- **defense_bundles**: Exportable evidence packages
- **bundle_items**: Individual items within bundles

## Key Features

### Event Sourcing

All changes are captured as events in the append-only audit_events table. Nothing is ever deleted or overwritten, satisfying Part 11's requirement that "changes shall not obscure previously recorded information."

```python
# Example: Creating an audit event
create_audit_event(
    conn,
    tenant_id="tenant-123",
    object_type="note",
    object_id="note-456",
    action="finalize",
    event_payload={
        "note_hash": "abc123...",
        "version_id": "v-789",
        "status_change": {"from": "draft", "to": "finalized"}
    },
    actor_id="actor-001"
)
```

### Hash Chaining

Each audit event includes:
- `prev_event_hash`: Hash of the previous event in the chain
- `event_hash`: Hash of current event including payload and metadata

This creates a tamper-evident chain where any modification breaks the hash linkage.

```python
# Verify audit chain integrity
result = verify_audit_chain(conn, tenant_id="tenant-123")
# Returns: {"valid": True, "total_events": 150, "errors": []}
```

### PHI-Safe Storage

Patient identifiers and clinical content are hashed before storage:

```python
# Patient reference is hashed with tenant as salt
patient_ref_hash = hash_with_salt(patient_id, tenant_id)

# Note content is hashed, not stored in plaintext
content_hash = hash_content(note_text)
```

Plaintext content can be stored in encrypted blob storage referenced by URI.

### Version History

Complete version history with diff tracking:

```python
# Create a new version with link to previous
version_id = create_note_version(
    conn,
    note_id="note-123",
    created_by_actor_id="actor-456",
    source="human_edit",
    content="Updated note content",
    prev_version_id="version-abc",  # Links to previous version
    diff_stats={
        "chars_added": 42,
        "chars_removed": 5,
        "lines_changed": 2
    }
)
```

### Electronic Signatures

Part 11 compliant electronic signatures with certificate chains:

```python
# Create attestation
attestation_id = create_attestation(
    conn,
    note_id="note-123",
    version_id="version-456",
    actor_id="actor-789",
    oversight_level="line_by_line_edit",
    attestation_text="I attest that I have reviewed...",
    meaning="author"
)

# Create signature
signature_id = create_signature(
    conn,
    attestation_id=attestation_id,
    signature_type="x509",
    signed_hash="sha256hash...",
    signature_blob="base64signature...",
    time_source="rfc3161_tsa",
    certificate_chain="-----BEGIN CERTIFICATE-----\n..."
)
```

### Human Review Tracking

Track review duration and interaction patterns to detect "robo-signing":

```python
# Start review session
review_id = create_review_session(
    conn,
    note_id="note-123",
    actor_id="actor-456",
    ui_surface="web"
)

# ... user reviews note ...

# End session with metrics
end_review_session(
    conn,
    review_id=review_id,
    interaction_metrics={
        "scroll_depth": 0.95,
        "keystrokes": 42,
        "focus_events": 15
    },
    red_flag=False
)
```

### Defense Bundle Export

Create litigation-ready evidence bundles:

```python
# Create defense bundle
bundle_id = create_defense_bundle(
    conn,
    tenant_id="tenant-123",
    requested_by_actor_id="actor-456",
    scope={
        "note_ids": ["note-1", "note-2", "note-3"],
        "date_range": {"start": "2024-01-01", "end": "2024-01-31"}
    },
    verification_instructions="Verify with OpenSSL..."
)

# Add items to bundle
add_bundle_item(
    conn,
    bundle_id=bundle_id,
    item_type="note_json",
    item_uri="s3://bundles/note-1.json",
    item_content='{"note_id": "note-1", ...}'
)
```

## Usage Examples

### Complete Workflow Example

```python
from app.db.migrate import get_connection
from app.db.part11_operations import *

conn = get_connection()

# 1. Create tenant
tenant_id = create_tenant(
    conn,
    name="Example Hospital",
    retention_policy={"years": 7, "legal_hold_rules": {}}
)

# 2. Create encounter
encounter_id = create_encounter(
    conn,
    tenant_id=tenant_id,
    patient_id="patient-12345",
    encounter_time_start="2024-01-15T09:00:00Z",
    source_system="Epic"
)

# 3. Create note
note_id = create_note(
    conn,
    tenant_id=tenant_id,
    encounter_id=encounter_id,
    note_type="progress"
)

# 4. Create AI actor
ai_actor_id = create_actor(
    conn,
    tenant_id=tenant_id,
    actor_type="ai",
    actor_name="GPT-4"
)

# 5. Create AI draft version
ai_version_id = create_note_version(
    conn,
    note_id=note_id,
    created_by_actor_id=ai_actor_id,
    source="ai_draft",
    content="AI-generated note content..."
)

# 6. Track AI generation
generation_id = create_ai_generation(
    conn,
    note_id=note_id,
    model_provider="openai",
    model_id="gpt-4",
    model_version="gpt-4-0125-preview",
    context_snapshot_hash=hash_content("context..."),
    output_version_id=ai_version_id
)

# 7. Create human actor
human_actor_id = create_actor(
    conn,
    tenant_id=tenant_id,
    actor_type="human",
    actor_name="Dr. Jane Smith",
    actor_role="physician"
)

# 8. Start review session
review_id = create_review_session(
    conn,
    note_id=note_id,
    actor_id=human_actor_id,
    ui_surface="web"
)

# 9. Create edited version
final_version_id = create_note_version(
    conn,
    note_id=note_id,
    created_by_actor_id=human_actor_id,
    source="human_edit",
    content="Reviewed and edited note content...",
    prev_version_id=ai_version_id,
    diff_stats={"chars_added": 50, "chars_removed": 10, "lines_changed": 2}
)

# 10. End review session
end_review_session(
    conn,
    review_id=review_id,
    interaction_metrics={"scroll_depth": 0.98, "keystrokes": 67},
    red_flag=False
)

# 11. Finalize note
update_note_status(conn, note_id, "finalized", final_version_id)

# 12. Create attestation
attestation_id = create_attestation(
    conn,
    note_id=note_id,
    version_id=final_version_id,
    actor_id=human_actor_id,
    oversight_level="line_by_line_edit",
    attestation_text="I attest that I have reviewed this note...",
    meaning="author"
)

# 13. Create signature
signature_id = create_signature(
    conn,
    attestation_id=attestation_id,
    signature_type="x509",
    signed_hash=hash_content(f"{note_id}{final_version_id}"),
    signature_blob="base64signature...",
    time_source="rfc3161_tsa"
)

# 14. Create audit events for each action
create_audit_event(
    conn,
    tenant_id=tenant_id,
    object_type="note",
    object_id=note_id,
    action="finalize",
    event_payload={
        "note_hash": hash_content("note content"),
        "version_id": final_version_id,
        "attestation_id": attestation_id
    },
    actor_id=human_actor_id
)

# 15. Verify audit chain
verification = verify_audit_chain(conn, tenant_id)
print(f"Audit chain valid: {verification['valid']}")

conn.close()
```

## Security Considerations

### Tenant Isolation

All tables include `tenant_id` foreign keys to ensure data isolation. Patient hashes use tenant ID as salt to prevent cross-tenant correlation.

### No PHI in Audit Events

Audit event payloads must contain only:
- Hashes (SHA-256)
- References (IDs, URIs)
- Metadata (timestamps, counts)

Never store plaintext PHI in audit events.

### Time Source Trust

For maximum defensibility, use RFC 3161 Time Stamp Authority (TSA):

```python
signature_id = create_signature(
    conn,
    attestation_id=attestation_id,
    signature_type="x509",
    signed_hash="...",
    signature_blob="...",
    time_source="rfc3161_tsa",  # Trusted time source
    certificate_chain="..."
)
```

### Retention and Deletion

Part 11 requires retention of records. "Delete" operations are never actual deletions:

```python
# Record delete request in audit log
create_audit_event(
    conn,
    tenant_id=tenant_id,
    object_type="note",
    object_id=note_id,
    action="delete_requested",
    event_payload={
        "requested_by": actor_id,
        "reason": "Patient request",
        "retention_end_date": "2031-01-01"
    },
    actor_id=actor_id
)

# Note: Record remains in database, just marked for deletion
```

## Testing

The implementation includes comprehensive tests covering:

1. Tenant creation and retrieval
2. Encounter creation with hashed patient references
3. Note lifecycle with versioning
4. AI generation tracking
5. Human review session tracking
6. Attestation and signature creation
7. Audit event hash chaining
8. Audit chain verification
9. Tampering detection
10. Defense bundle creation
11. Patient reference hashing consistency
12. Tenant isolation
13. Content hashing
14. PHI-free audit events

Run tests:

```bash
cd gateway
python -m pytest tests/test_part11_compliance.py -v
```

## Compliance Checklist

### Part 11 Requirements Satisfied

- ✅ **§11.10(a)** - System validation via tested schema constraints
- ✅ **§11.10(c)** - Secure, timestamped audit trails (audit_events table)
- ✅ **§11.10(d)** - Copy operations (defense_bundles)
- ✅ **§11.10(e)** - Timestamping with configurable time sources
- ✅ **§11.10(k)(1)** - Ability to determine who changed what (audit_events + note_versions)
- ✅ **§11.10(k)(2)** - Ability to generate accurate copies (defense_bundles)
- ✅ **§11.50** - Electronic signatures with binding to data
- ✅ **§11.70** - Signature uniqueness via per-tenant keys
- ✅ **§11.100** - General requirements for electronic records
- ✅ **§11.200** - Electronic signature components and controls

### Additional Healthcare Compliance

- ✅ **HIPAA PHI Protection**: Patient references hashed, no plaintext PHI in audit log
- ✅ **FHIR Provenance Alignment**: Data model maps cleanly to FHIR Provenance resources
- ✅ **CMS AI Guidance**: Minimum necessary principle for AI-generated content

## Future Enhancements

### Planned Features

1. **Ledger Anchoring**: Implement periodic Merkle root anchoring to external TSA
2. **FHIR Export**: Map internal data model to FHIR Provenance and Signature resources
3. **Blockchain Integration**: Optional blockchain anchoring for public verifiability
4. **Automated Compliance Reports**: Generate Part 11 compliance reports on demand
5. **Clinical Fact Extraction**: Populate clinical_facts from EHR/FHIR resources
6. **Similarity Scoring**: Implement note cloning detection algorithms

## References

1. [21 CFR Part 11 - Electronic Records; Electronic Signatures](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11)
2. [FHIR Provenance Resource](https://build.fhir.org/provenance.html)
3. [FHIR Signature Guidance](https://build.fhir.org/signatures.html)
4. [CMS Guidance for Responsible Use of AI](https://security.cms.gov/policy-guidance/guidance-responsible-use-artificial-intelligence-ai-cms)
5. [NIST SP 800-92 - Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final)

## Support

For questions or issues with the Part 11 implementation:

1. Review this documentation
2. Check test suite for usage examples
3. Verify database schema in `part11_schema.sql`
4. Examine operations in `part11_operations.py`
5. Review models in `part11.py`
