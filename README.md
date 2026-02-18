# Clinical Documentation Integrity Layer (CDIL)

> **"If it's not exportable and understandable by a lawyer, it didn't happen."**

CDIL is a **Verifiable Evidence Layer** that provides cryptographically verifiable integrity certificates for AI-generated clinical documentation. It serves three critical stakeholders:

1. **Hospitals** - Export evidence bundles for payer appeals, litigation, and compliance audits
2. **AI Vendors** - Register models and participate in governed, multi-vendor ecosystems  
3. **EHR Vendors** - Enable gatekeeper mode to ensure only verified notes are committed

Every certificate is **exportable, independently verifiable, and legally defensible**.

---

## Architecture Overview

CDIL provides a complete trust infrastructure for AI-generated clinical documentation:

- **Evidence Bundles** - Self-contained packages for legal proceedings and audits
- **Vendor Registry** - Track AI models, versions, and vendor public keys
- **Model Governance** - Tenant-level allowlists for approved AI models
- **Gatekeeper Mode** - EHR integration point for pre-commit verification
- **Per-Tenant Keys** - Cryptographic isolation across organizations

---

## Evidence Mode: The Primary Use Case

CDIL is designed for **evidentiary use cases** — providing tamper-evident proof that can be handed to auditors, regulators, and legal counsel.

### What You Hand to a Lawyer

When questioned about AI-generated clinical documentation, you provide:

1. **Evidence Bundle (JSON)** — Structured bundle with certificate, verification instructions, and public key references
2. **Evidence Bundle (ZIP)** — Complete archive with certificate.json, certificate.pdf, evidence_bundle.json, verification_report.json, README_VERIFICATION.txt
3. **Verification Proof** — Demonstrate that the certificate passes all integrity checks (timing, chain hash, signature)

---

## 📋 Security Documentation

**Critical:** Before production deployment, review the comprehensive security documentation:

- **[Genie Roadmap](./docs/GENIE_ROADMAP.md)** - Evolution into Verifiable Evidence Layer (Hospitals + AI Vendors + EHRs)
- **[Integrity Artifact Spec](./docs/INTEGRITY_ARTIFACT_SPEC.md)** - Canonical formats for certificates and evidence bundles
- **[Threat Model & Trust Guarantees](./docs/THREAT_MODEL_AND_TRUST_GUARANTEES.md)** - Complete security contract, attacker model, STRIDE analysis
- **[Security Audit Summary](./docs/SECURITY_AUDIT_SUMMARY.md)** - Executive summary with critical findings and remediation timeline
- **[Security Documentation Guide](./docs/README_SECURITY.md)** - Navigation guide for security docs and automated tests

**Security Hardening (Implemented):**
- ✅ **Per-tenant cryptographic keys** - No cross-tenant forgery possible (Phase 5 complete)
- ✅ PHI properly hashed, never stored in plaintext
- ✅ Tenant isolation at API and DB layers
- ✅ Nonce-based replay protection
- ✅ Role-based access control (clinician, auditor, admin, ehr_gateway)
- ✅ 50+ automated security tests passing

See [GENIE_ROADMAP.md](./docs/GENIE_ROADMAP.md) for production readiness requirements.

---

## Core Workflow

### 1. Issue Certificate at Note Finalization

```bash
POST /v1/clinical/documentation
```

**What CDIL Does:**
- ✅ Validates note_text for PHI patterns (rejects SSN, phone, email)
- ✅ Hashes note content (never stores plaintext)
- ✅ Sets server-side finalization timestamp (prevents backdating)
- ✅ Links to tenant's integrity chain (prevents insertion)
- ✅ Computes policy hash (proves governance)
- ✅ Cryptographically signs certificate

### 2. Verify Certificate (API or Offline)

```bash
POST /v1/certificates/{id}/verify
Headers: X-Tenant-Id: hospital-alpha
```

Returns human-friendly report with status, summary, reason, recommended action.

**CLI Verification:**
```bash
python tools/verify_certificate_cli.py certificate.json
```

Outputs color-coded PASS (green) or FAIL (red) with exit codes.

### 3. Export Evidence Bundle (JSON or ZIP)

**JSON Bundle (Primary Format):**
```bash
GET /v1/certificates/{id}/evidence-bundle
Headers: Authorization: Bearer <JWT>
```

Returns structured JSON bundle with:
- Certificate metadata (certificate_id, tenant_id, issued_at, key_id, algorithm)
- Canonical message (what was signed)
- Content hashes (note_hash, patient_hash, reviewer_hash)
- Model info (model_version, policy_version, policy_hash)
- Human attestation (reviewed, reviewer_hash, timestamp)
- Verification instructions (CLI, API, manual)
- Public key reference

**ZIP Bundle (Convenience Format):**
```bash
GET /v1/certificates/{id}/bundle
Headers: Authorization: Bearer <JWT>
```

Returns ZIP with: certificate.json, certificate.pdf, evidence_bundle.json, verification_report.json, README_VERIFICATION.txt

### 4. Query Certificates for Audit

```bash
POST /v1/certificates/query
Body: {"tenant_id": "hospital-alpha", "date_from": "...", "human_reviewed": true}
```

Filters: tenant_id, date range, model_version, policy_version, human_reviewed, pagination

---

## API Endpoints

### Certificate Issuance
- `POST /v1/clinical/documentation` — Issue certificate (clinician role)

### Certificate Retrieval & Verification
- `GET /v1/certificates/{id}` — Get certificate
- `POST /v1/certificates/{id}/verify` — Verify certificate (auditor role)

### Evidence Export (Phase 1 - Hospitals)
- `GET /v1/certificates/{id}/evidence-bundle` — Get evidence bundle JSON (primary format)
- `GET /v1/certificates/{id}/bundle` — Get evidence bundle ZIP (convenience format)
- `GET /v1/certificates/{id}/pdf` — Download PDF certificate

### Vendor Registry (Phase 2 - AI Vendors)
- `POST /v1/vendors/register` — Register AI vendor (admin only)
- `POST /v1/vendors/register-model` — Register AI model with optional public key (admin only)
- `POST /v1/vendors/rotate-model-key` — Rotate model key (admin only)
- `GET /v1/vendors/models` — List registered models (admin only)
- `GET /v1/allowed-models` — Get allowed models for tenant (admin only)

### Model Governance (Phase 3 - Multi-party)
- `POST /v1/governance/models/allow` — Allow model for tenant (admin only)
- `POST /v1/governance/models/block` — Block model for tenant (admin only)
- `GET /v1/governance/models/status` — Get model authorization status (admin only)

### EHR Gatekeeper (Phase 4 - EHR Vendors)
- `POST /v1/gatekeeper/verify-and-authorize` — Verify certificate and issue commit token (ehr_gateway role)
- `POST /v1/gatekeeper/verify-commit-token` — Verify commit token (ehr_gateway role)

### Audit & Reporting
- `POST /v1/certificates/query` — Query with filters

### Evidence Export
- `GET /v1/certificates/{id}/pdf` — Download PDF (requires X-Tenant-Id)
- `GET /v1/certificates/{id}/bundle` — Download evidence bundle (requires X-Tenant-Id)

### Audit & Reporting
- `POST /v1/certificates/query` — Query with filters

---

## Stakeholder Use Cases

### For Hospitals: Revenue Protection & Litigation Armor

**Problem**: Payers deny AI-generated documentation claims. Appeals require proof of integrity.

**Solution**: Export evidence bundles for appeals.

```bash
# Get evidence bundle for certificate
GET /v1/certificates/{cert_id}/evidence-bundle
```

**Value**:
- **Payer Appeals** - Submit evidence bundle showing note was generated under governance
- **Litigation Defense** - Prove documentation hasn't been altered since creation
- **Compliance Audits** - Demonstrate AI oversight and human review
- **ROI**: 6-8x return via reduced denials and successful appeals

See [ROI Calculator](./docs/ROI_CALCULATOR_TEMPLATE.md) for detailed financial modeling.

### For AI Vendors: Trust-as-a-Service

**Problem**: Hospitals hesitant to adopt AI without governance proof and liability protection.

**Solution**: Register models and provide vendor attestations.

```bash
# Register vendor
POST /v1/vendors/register
Body: {"vendor_name": "Anthropic"}

# Register model with public key
POST /v1/vendors/register-model
Body: {
  "vendor_id": "...",
  "model_name": "Claude-3",
  "model_version": "opus-20240229",
  "public_jwk": {...}
}

# Rotate keys when needed
POST /v1/vendors/rotate-model-key
```

**Value**:
- **Differentiation** - "Our models are certifiable and auditable"
- **Enterprise Sales** - Governance proof required for hospital procurement
- **Liability Reduction** - Cryptographic proof of model version and policy compliance
- **Partnership** - Multi-vendor ecosystems with hospitals

### For EHR Vendors: Liability Firewall

**Problem**: EHRs liable if unverified AI notes cause harm or billing fraud.

**Solution**: Gatekeeper mode prevents unverified notes from being committed.

```bash
# EHR checks certificate before commit
POST /v1/gatekeeper/verify-and-authorize
Body: {
  "certificate_id": "cert-123",
  "ehr_commit_id": "ehr-opaque-id"
}

# Returns commit token if verified
Response: {
  "authorized": true,
  "commit_token": "eyJhbGc...",  # 5-minute expiry
  "verification_passed": true
}

# EHR uses commit token to prove compliance
POST /v1/gatekeeper/verify-commit-token
```

**Value**:
- **Risk Reduction** - Only verified notes reach the medical record
- **Audit Trail** - Commit tokens prove EHR enforced verification
- **Competitive Advantage** - "Our EHR has built-in AI governance"
- **Partnership** - Enable multi-vendor AI ecosystems

---

## Security Guarantees

### PHI Protection
- Never stores plaintext note_text (only SHA-256 hash)
- Rejects SSN, phone, email patterns in note_text
- Returns `phi_detected_in_note_text` error

### Tenant Isolation
- All endpoints require X-Tenant-Id header or tenant_id parameter
- Returns `tenant_mismatch` error (404) for cross-tenant access
- Never reveals certificate existence to other tenants

### Timing Integrity
- Server sets finalized_at (never client-supplied)
- Verification fails if finalized_at > ehr_referenced_at (backdating)
- Returns `finalized_after_ehr_reference` error

### Cryptographic Integrity
- Chain hash links certificates (prevents insertion/reordering)
- ECDSA P-256 signature (prevents forgery)
- Offline verification supported

---

## Installation & Setup

```bash
pip install -r requirements.txt
uvicorn gateway.app.main:app --reload --port 8000
```

**Authentication**: All endpoints require JWT authentication with Bearer token:

```bash
curl -X POST http://localhost:8000/v1/clinical/documentation \
  -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{
    "model_version":"gpt-4-turbo",
    "note_text":"Test note",
    "human_reviewed":true,
    ...
  }'
```

**Roles**:
- `clinician` - Issue certificates
- `auditor` - Verify certificates and query audit logs
- `admin` - Full access (vendor registry, model governance)
- `ehr_gateway` - Verify certificates and issue commit tokens

---

## Business Case / ROI Tools

CDIL provides **CFO-ready ROI modeling** to quantify the financial impact of deploying integrity certificates for AI-generated clinical documentation.

### Documentation

- **[ROI Calculator Template](./docs/ROI_CALCULATOR_TEMPLATE.md)** — Comprehensive Excel/Sheets template with formulas, worked examples, and sensitivity analysis
- **[ROI One-Pager](./docs/ROI_ONE_PAGER.md)** — Executive-friendly summary with "denial insurance" framing and key assumptions
- **[ROI Implementation Summary](./docs/ROI_IMPLEMENTATION_SUMMARY.md)** — Technical implementation details and test results

### ROI Projection API

**Endpoint:** `POST /v2/analytics/roi-projection`

Calculate ROI projections programmatically for demos, financial modeling, and business case development.

> **⚠️ No PHI Processed:** This endpoint performs pure financial modeling with no database access and no patient health information. It's fully stateless computation.

**Example Request:**
```json
{
  "annual_revenue": 500000000,
  "denial_rate": 0.08,
  "documentation_denial_ratio": 0.40,
  "appeal_recovery_rate": 0.25,
  "denial_prevention_rate": 0.05,
  "appeal_success_lift": 0.05,
  "cost_per_appeal": 150,
  "annual_claim_volume": 200000,
  "cdil_annual_cost": 250000
}
```

**Example Response:**
```json
{
  "total_denied_revenue": 40000000.0,
  "documentation_denied_revenue": 16000000.0,
  "prevented_denials_revenue": 800000.0,
  "remaining_documentation_denied_revenue": 15200000.0,
  "current_recovered_revenue": 3800000.0,
  "incremental_recovery_gain": 760000.0,
  "appeals_avoided_count": 320.0,
  "admin_savings": 48000.0,
  "total_preserved_revenue": 1608000.0,
  "roi_multiple": 6.432,
  "roi_note": null,
  "assumptions": { ...input echo... }
}
```

**Run Locally:**
```bash
# Start server
uvicorn gateway.app.main:app --reload --port 8000

# Test ROI endpoint with curl
curl -X POST http://localhost:8000/v2/analytics/roi-projection \
  -H "Content-Type: application/json" \
  -d '{
    "annual_revenue": 500000000,
    "denial_rate": 0.08,
    "documentation_denial_ratio": 0.40,
    "appeal_recovery_rate": 0.25,
    "denial_prevention_rate": 0.05,
    "appeal_success_lift": 0.05,
    "cost_per_appeal": 150,
    "annual_claim_volume": 200000,
    "cdil_annual_cost": 250000
  }'

# Or run the interactive demo (shows conservative/moderate/aggressive scenarios)
./demo/roi_endpoint_demo.sh

# Run ROI tests
pytest gateway/tests/test_roi_projection.py -v
```

**Use Cases:**
- CFO presentations with customized hospital metrics
- Product demos with live ROI calculations
- Financial modeling for business case approval
- Revenue cycle team validation of assumptions

### Important Disclaimers

⚠️ **ROI Projections Are Estimates:**
- ROI outputs are projections based on your inputs; **not guarantees** of actual results
- Actual ROI will vary based on hospital operations, payer mix, and implementation quality
- Defaults are conservative (5% prevention rate, 5% appeal lift); your finance team should adjust assumptions based on your hospital's baseline metrics

⚠️ **Recommended Approach:**
- Start with conservative assumptions (5%/5%) for initial presentations
- Validate assumptions with your revenue cycle and finance teams
- Use sensitivity analysis to understand range of potential outcomes
- Monitor actual performance against projections after deployment

---

## Use Cases

1. **Payer Appeals** — Export evidence bundles to contest denied claims
2. **Medical Malpractice Litigation** — Prove note content unchanged since issuance
3. **Regulatory Audits** — Demonstrate AI governance and human oversight
4. **Multi-Vendor AI Ecosystems** — Enable hospitals to use multiple AI vendors with unified governance
5. **EHR Gatekeeper** — Prevent unverified AI notes from reaching medical records
6. **Financial Planning** — ROI modeling for CDIL deployment business case

---

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
pytest gateway/tests/ -v

# Run specific test suites
pytest gateway/tests/test_evidence_bundle.py -v     # Phase 1: Evidence bundles
pytest gateway/tests/test_vendor_registry.py -v     # Phase 2: Vendor registry
pytest gateway/tests/test_model_governance.py -v    # Phase 3: Model governance
pytest gateway/tests/test_gatekeeper.py -v          # Phase 4: EHR gatekeeper
pytest gateway/tests/test_phase5_cleanup.py -v      # Phase 5: Security cleanup

# 50+ automated security tests
```

---

## Legal Notice

**CDIL provides cryptographic proof of:**
- Which AI model generated documentation
- Which governance policy was applied
- That note content has not been altered
- That certificate was not backdated

**CDIL does NOT:**
- Replace clinical judgment
- Guarantee accuracy of content
- Satisfy all regulatory requirements

Consult legal counsel for litigation/compliance use.

---

**CDIL: Making AI clinical documentation auditably defensible.**
