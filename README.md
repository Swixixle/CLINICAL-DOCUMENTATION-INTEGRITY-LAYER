# Clinical Documentation Integrity Layer (CDIL)

> **"If it's not exportable and understandable by a lawyer, it didn't happen."**

CDIL is a **Verifiable Evidence Layer** for AI-generated clinical documentation. This Phase 1 implementation provides cryptographically verifiable integrity certificates and evidence bundles.

**Primary Use Case:** Export evidence bundles for payer appeals, litigation, and compliance audits.

Every certificate is **exportable, independently verifiable, and legally defensible**.

---

## Phase 1 Scope (This PR)

This implementation focuses exclusively on **Evidence Bundle Export**:

- **Evidence Bundles (JSON)** - Structured bundles with certificate, verification instructions, and public key references
- **Evidence Bundles (ZIP)** - Complete archive with certificate.json, certificate.pdf, evidence_bundle.json, verification_report.json, README_VERIFICATION.txt
- **Per-Tenant Keys** - Cryptographic isolation across organizations
- **Offline Verification** - Bundles can be verified without API access

**Not Included in Phase 1:**
- Vendor Registry (Phase 2)
- Model Governance (Phase 3)
- Gatekeeper Mode (Phase 4)

These features will be implemented in separate PRs with dedicated threat models, migrations, and tests.

---

## 📋 Security Documentation

**Phase 1 Security Boundaries:**
- Per-tenant cryptographic keys (no cross-tenant forgery)
- PHI properly hashed, never stored in plaintext
- Tenant isolation at API and DB layers
- Nonce-based replay protection
- Role-based access control (clinician, auditor, admin)

**For detailed security analysis, see:**
- [Integrity Artifact Spec](./docs/INTEGRITY_ARTIFACT_SPEC.md) - Canonical formats for certificates and evidence bundles
- [Threat Model & Trust Guarantees](./docs/THREAT_MODEL_AND_TRUST_GUARANTEES.md) - Security contract, attacker model, STRIDE analysis

**Known Limitations:**
- This is a Phase 1 implementation focused on evidence export
- Production deployment requires additional hardening (see threat model)
- Security testing is ongoing

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
GET /v1/certificates/{id}/evidence-bundle.json
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

**ZIP Bundle (Complete Archive):**
```bash
GET /v1/certificates/{id}/evidence-bundle.zip
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

## API Endpoints (Phase 1)

### Certificate Issuance
- `POST /v1/clinical/documentation` — Issue certificate (clinician role)

### Certificate Retrieval & Verification
- `GET /v1/certificates/{id}` — Get certificate
- `POST /v1/certificates/{id}/verify` — Verify certificate (auditor role)

### Evidence Export
- `GET /v1/certificates/{id}/evidence-bundle.json` — Get evidence bundle JSON (primary format)
- `GET /v1/certificates/{id}/evidence-bundle.zip` — Get evidence bundle ZIP (complete archive)
- `GET /v1/certificates/{id}/pdf` — Download PDF certificate

### Certificate Query
- `POST /v1/certificates/query` — Query certificates with filters

### Key Management
- `GET /v1/keys/{key_id}` — Get public key (for offline verification)

**Phase 2-4 Features (Not Included):**
- Vendor Registry (AI Vendors) - Separate PR
- Model Governance (Multi-party) - Separate PR
- Gatekeeper Mode (EHR Vendors) - Separate PR
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

## Use Case: Hospital Revenue Protection & Litigation Armor

**Problem**: Payers deny AI-generated documentation claims. Appeals require proof of integrity.

**Solution**: Export evidence bundles for appeals.

```bash
# Get JSON evidence bundle
GET /v1/certificates/{cert_id}/evidence-bundle.json

# Get complete ZIP archive
GET /v1/certificates/{cert_id}/evidence-bundle.zip
```

**Value**:
- **Payer Appeals** - Submit evidence bundle showing note was generated under governance
- **Litigation Defense** - Prove documentation hasn't been altered since creation
- **Compliance Audits** - Demonstrate AI oversight and human review
- **Offline Verification** - Legal and audit teams can verify without API access

---

## Development

### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
uvicorn gateway.app.main:app --reload --port 8000

# Run tests (rate limiting disabled automatically)
ENV=TEST pytest gateway/tests/test_evidence_bundle.py -v
```

### Testing

```bash
# Run Phase 1 tests
pytest gateway/tests/test_evidence_bundle.py -v

# Run all Phase 1 tests
pytest gateway/tests/test_clinical_endpoints.py -v
pytest gateway/tests/test_phase1_security.py -v
```

---

## Shadow Mode (Revenue Risk Intelligence)

**Shadow Mode** enables retrospective analysis of clinical documentation to identify evidence deficits and estimate revenue at risk - **without requiring EMR integration**.

### Key Features

- **Evidence Sufficiency Scoring** - Deterministic, rule-based analysis of whether documentation supports assigned diagnosis codes
- **Revenue Impact Modeling** - Transparent calculations to estimate potential claim denial risk
- **Defensibility Dashboard** - Executive-friendly metrics showing percent defensible, percent at risk, and estimated annual revenue leakage
- **No EMR Integration Required** - Operates on exported note batches for pilot deployments

### Use Case: Preventable Revenue Loss Detection

**Problem**: Documentation gaps in AI-generated notes lead to claim denials. Hospitals need to identify these gaps before claims are submitted.

**Solution**: Analyze batches of notes to find documentation deficiencies.

```bash
# Analyze a batch of notes
POST /v1/shadow/analyze
Body: {
  "notes": [
    {
      "note_text": "Patient with severe malnutrition...",
      "diagnosis_codes": ["E43"],
      "claim_value": 24000
    }
  ],
  "average_claim_value": 20000,
  "denial_probability": 0.08
}

# Get executive dashboard
GET /v1/shadow/dashboard?annual_note_volume=10000
```

### Supported High-Value Diagnoses

Shadow Mode includes evidence rules for:
- **Malnutrition** (E43, E44) - BMI, albumin, weight loss, dietary assessment
- **Sepsis** (A41.9) - SIRS criteria, infection source, labs, vitals
- **Heart Failure** (I50.9, I50.23, I50.33) - Ejection fraction, symptoms, physical exam
- **Acute Kidney Injury** (N17.9) - Creatinine, baseline renal function, urine output
- **Respiratory Failure** (J96.00, J96.90) - ABG results, oxygen saturation, clinical presentation

### Design Principles

- **Deterministic > AI** - Reviewable, rule-based logic instead of black-box ML
- **CFO-Readable** - Transparent revenue calculations and executive metrics
- **Pilot-Friendly** - No infrastructure changes required
- **Secure** - JWT authentication, tenant isolation, no PHI logging

### Security

- JWT authentication required for all endpoints
- Tenant ID derived from authenticated identity (never from request)
- Cross-tenant isolation enforced
- No PHI stored or logged in responses
- Rate limiting applies (disabled in test mode with ENV=TEST)

---

## Next Steps (Future PRs)

### Phase 2: Vendor Registry (AI Vendors)
- Register AI vendors and models
- Track model versions and metadata
- Vendor public key management with rotation support

### Phase 3: Model Governance (Multi-party)
- Tenant-level model allowlists
- Governance policy enforcement
- Cross-tenant isolation

### Phase 4: Gatekeeper Mode (EHR Vendors)
- Pre-commit verification for EHR integration
- Commit token issuance
- EHR-side enforcement

Each phase will have:
- Dedicated threat model updates
- Database migrations
- Comprehensive test coverage
- Rollback procedures

---

## License

See LICENSE file for details.
