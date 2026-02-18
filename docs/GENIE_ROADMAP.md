# CDIL "Genie" Roadmap - Verifiable Evidence Layer

## Vision

Evolve CDIL from "note integrity certificates" into a **Verifiable Evidence Layer** that serves three critical stakeholders:

1. **Hospitals** - Produce exportable evidence bundles for appeals, litigation, and compliance
2. **AI Vendors** - Register models and participate in governed, multi-vendor ecosystems
3. **EHR Vendors** - Enable gatekeeper mode to ensure only verified notes are committed

## Architecture Overview

### Current State (Phase 1)
- Single-tenant certificate issuance with cryptographic signatures
- Per-tenant key isolation
- Basic verification endpoints
- PDF certificate generation

### Target State (Phase 6)
- **Evidence Bundles**: Self-contained packages with certificates, verification instructions, and public keys
- **Vendor Registry**: Track AI models, versions, and vendor public keys
- **Model Governance**: Tenant-level allowlists for approved AI models
- **Gatekeeper Mode**: EHR integration point for pre-commit verification
- **Attribution Metadata**: Track AI vs human contribution without storing PHI

## New Artifacts

### 1. Evidence Bundle (JSON)

Complete exportable package containing:

```json
{
  "certificate_id": "cert-uuid7",
  "tenant_id": "hospital-alpha",
  "issued_at": "2026-02-18T10:30:00Z",
  "key_id": "tenant-key-001",
  "algorithm": "ECDSA_SHA_256",
  "canonical_message": { ... },
  "note_hash": "sha256:abc123...",
  "hash_algorithm": "SHA-256",
  "model_info": {
    "model_id": "model-uuid",
    "model_name": "GPT-4-Turbo",
    "model_version": "2024-11",
    "vendor_name": "OpenAI",
    "policy_hash": "sha256:policy123..."
  },
  "human_attestation": {
    "reviewed": true,
    "reviewer_hash": "sha256:reviewer...",
    "timestamp": "2026-02-18T10:29:50Z"
  },
  "attribution": {
    "ai_generated_pct": 60,
    "human_edited_pct": 40,
    "source_mix": {
      "ai": 60,
      "dictation": 20,
      "prior_note": 20
    }
  },
  "verification_instructions": {
    "offline_cli": "python verify_certificate_cli.py certificate.json",
    "api_endpoint": "POST /v1/certificates/{id}/verify",
    "public_key_reference": "GET /v1/keys/{key_id}"
  },
  "signature": "base64-signature..."
}
```

### 2. Commit Token (EHR Gatekeeper)

Short-lived JWT binding a verified certificate to an EHR commit:

```json
{
  "token_type": "cdil_commit_authorization",
  "tenant_id": "hospital-alpha",
  "certificate_id": "cert-uuid7",
  "ehr_commit_id": "ehr-opaque-id",
  "authorized_at": "2026-02-18T10:30:00Z",
  "expires_at": "2026-02-18T10:35:00Z",
  "signature": "server-signature..."
}
```

## New Endpoints

### Evidence Export (Phase 1)
- `GET /v1/certificates/{certificate_id}/evidence-bundle` - JSON evidence bundle
- `GET /v1/certificates/{certificate_id}/evidence-bundle.pdf` - Optional PDF rendering

### Vendor Registry (Phase 2)
- `POST /v1/vendors/register-model` - Register AI model with vendor public key (admin only)
- `POST /v1/vendors/rotate-model-key` - Rotate model key (admin only)
- `GET /v1/vendors/models` - List registered models (admin only)
- `GET /v1/tenants/{tenant_id}/allowed-models` - Show approved models for tenant (admin only)

### Model Governance (Phase 3)
- `POST /v1/governance/models/allow` - Approve model for tenant (admin only)
- `POST /v1/governance/models/block` - Block model for tenant (admin only)
- `GET /v1/governance/models/status` - Get model authorization status (admin only)

### EHR Gatekeeper (Phase 4)
- `POST /v1/gatekeeper/verify-and-authorize` - Verify certificate and issue commit token (ehr_gateway role)

## Trust Boundaries

### 1. Tenant Boundary (Existing - Enhanced)
- **Cryptographic isolation**: Per-tenant signing keys
- **Data isolation**: Cross-tenant read/verify returns 404
- **Enforcement**: tenant_id derived from JWT identity only

### 2. Vendor Boundary (New)
- **Model registration**: Only admin can register/rotate vendor keys
- **Attestation**: Vendor public keys stored separately from tenant keys
- **Verification**: Vendor signatures can be verified independently

### 3. Model Allowlist Boundary (New)
- **Authorization**: Tenant admins control which models can issue certificates
- **Enforcement**: Issuance fails (403) if model not in tenant allowlist
- **Isolation**: Tenant A cannot see Tenant B's allowlist configuration

### 4. Gatekeeper Boundary (New)
- **Role separation**: `ehr_gateway` role separate from `clinician` and `auditor`
- **Token lifecycle**: Commit tokens are short-lived (5 minutes)
- **Binding**: Token cryptographically binds certificate_id to ehr_commit_id

## Threat Model Deltas

### New Attack Surfaces

1. **Vendor Key Compromise**
   - *Risk*: Attacker gains vendor private key, forges model attestations
   - *Mitigation*: Key rotation, separate vendor/tenant key stores, audit logging

2. **Model Allowlist Bypass**
   - *Risk*: Attacker issues certificate with unapproved model
   - *Mitigation*: Enforce allowlist at issuance time (pre-signature), 403 on violation

3. **Commit Token Replay**
   - *Risk*: Attacker reuses commit token for multiple EHR commits
   - *Mitigation*: Short expiration (5 min), one-time-use nonce, server-side tracking

4. **Cross-Tenant Model Configuration Leakage**
   - *Risk*: Tenant A discovers which models Tenant B has approved
   - *Mitigation*: Return 404 on cross-tenant queries, no existence disclosure

### Mitigations Applied

- **Zero-PHI Discipline**: All new logs sanitized, no note_text in error responses
- **Role-Based Access**: Admin role required for vendor/governance endpoints
- **Nonce Protection**: All signed messages include replay-protected nonces
- **Audit Trail**: All vendor registration and allowlist changes logged with timestamps
- **Key Rotation**: Support for model key rotation without breaking old certificates

## Production Readiness Checklist

### Ready for Production
- ✅ Per-tenant key isolation
- ✅ Nonce-based replay protection
- ✅ Cross-tenant access returns 404
- ✅ Zero-PHI logging discipline
- ✅ Evidence bundle generation

### Not Yet Production-Ready (Require Additional Work)
- ⚠️ **Key Management**: External HSM/KMS integration not implemented
- ⚠️ **Rate Limiting**: Per-tenant rate limits not enforced (global only)
- ⚠️ **Audit Logging**: No structured audit log export (events logged but not queryable)
- ⚠️ **Nonce Cleanup**: No automated cleanup of old used_nonces table entries
- ⚠️ **Vendor Key Verification**: Manual vendor key validation (no PKI integration)

### Required for Healthcare Production
- 🔒 HIPAA compliance audit (PHI handling, access controls, encryption)
- 🔒 SOC 2 Type II certification
- 🔒 Disaster recovery plan and tested backup procedures
- 🔒 Incident response plan for key compromise scenarios
- 🔒 External security audit of vendor registry and gatekeeper components

## Rollout Strategy

### Phase 1: Evidence Bundles (Hospitals)
- **Impact**: Low risk, high value
- **Stakeholders**: Compliance teams, legal counsel
- **Timeline**: 2 weeks
- **Validation**: Generate bundle for test certificate, verify offline

### Phase 2: Vendor Registry (AI Vendors)
- **Impact**: Medium risk, medium value
- **Stakeholders**: AI vendors, governance committees
- **Timeline**: 3 weeks
- **Validation**: Register test model, rotate key, verify old certs still valid

### Phase 3: Model Governance (Hospitals + Vendors)
- **Impact**: Medium risk, high value
- **Stakeholders**: Hospital admins, AI vendors
- **Timeline**: 2 weeks
- **Validation**: Block test model, confirm issuance fails with 403

### Phase 4: Gatekeeper Mode (EHR Vendors)
- **Impact**: High risk, high value
- **Stakeholders**: EHR vendors, integration teams
- **Timeline**: 4 weeks
- **Validation**: Mock EHR integration, verify commit token lifecycle

### Phase 5: Legacy Cleanup
- **Impact**: Low risk, security improvement
- **Stakeholders**: Internal engineering
- **Timeline**: 1 week
- **Validation**: Test suite confirms no legacy signing paths

### Phase 6: Documentation
- **Impact**: No risk, sales enablement
- **Stakeholders**: Sales, marketing, buyers
- **Timeline**: 1 week
- **Validation**: Sales team reviews one-pagers

## Success Metrics

### Hospitals
- Evidence bundles successfully used in 1+ payer appeals
- Compliance team adopts bundle export for quarterly audits
- Legal counsel confirms bundles meet evidentiary standards

### AI Vendors
- 3+ vendors register models in production
- Vendor keys rotated without breaking existing certificates
- Vendors report "trust-as-a-service" as competitive advantage

### EHR Vendors
- 1+ EHR integrates gatekeeper mode
- Zero unauthorized notes committed (gatekeeper blocks)
- EHR team reports reduced liability exposure

## Open Questions

1. **Vendor Key Distribution**: How do vendors securely provide public keys? (Manual upload? JWKS endpoint?)
2. **Model Version Granularity**: Should allowlist be per-model or per-model-version?
3. **Commit Token Persistence**: Should commit tokens be stored for audit, or ephemeral?
4. **Evidence Bundle Format**: Should bundles be ZIP or JSON? (Current: both, JSON primary)
5. **Offline Verification**: Should public keys be embedded in bundles or referenced? (Current: referenced)

## Next Steps

1. ✅ Create this roadmap document
2. ✅ Create INTEGRITY_ARTIFACT_SPEC.md
3. ⏭ Implement Phase 1 (Evidence Bundle Export)
4. ⏭ Write tests for new security boundaries
5. ⏭ Update threat model docs with new attack surfaces
