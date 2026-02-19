# Clinical Documentation Integrity Layer (CDIL)

> **"We detect preventable revenue loss caused by documentation evidence gaps — without touching your EMR."**

## What CDIL Is

CDIL is a **cryptographically verifiable documentation integrity and audit reconstruction engine** for AI-generated clinical notes.
CDIL is a **Verifiable Evidence Layer** for AI-generated clinical documentation. This implementation provides:

1. **Shadow Mode Sidecar** - Run alongside existing workflows without EMR integration
2. **Defense Bundles** - Litigation-grade, payer/audit-ready evidence artifacts
3. **Executive Dashboard** - Proof-of-concept metrics that answer exec questions in 10 seconds

**Primary Use Cases:**
- Shadow Mode pilot deployments (no EMR integration required)
- Export evidence bundles for payer appeals, litigation, and compliance audits
- Documentation quality analysis and risk identification
- Cryptographic proof of integrity for AI-generated clinical notes

**Value Proposition (Pick One):**

### For Hospital CFOs: Revenue Protection
Detect documentation-driven revenue loss **before** claims are submitted. Shadow Mode analyzes notes in pilot mode to identify evidence deficits that lead to denials.

- ✅ No EMR integration required (pilot-friendly)
- ✅ Measurable ROI from first deployment
- ✅ Deterministic, explainable scoring (no black-box AI)

### For Hospital CISOs: AI Governance Infrastructure
Provide cryptographic proof that AI clinical documentation was generated under governance, reviewed by humans, and hasn't been tampered with.

- ✅ Per-tenant signing keys (no cross-tenant forgery)
- ✅ Exportable evidence bundles for legal/audit defense
- ✅ Courtroom-grade integrity certificates

### For Compliance Teams: Audit Defense
Create defensible audit trails for AI-generated documentation with offline-verifiable evidence bundles.

- ✅ Exportable JSON/ZIP bundles with verification instructions
- ✅ No API access needed for verification
- ✅ Designed to support **FDA 21 CFR Part 11** electronic signature and audit trail requirements
- ✅ Tamper-evident hash chaining with verifiable integrity
- ✅ Complete version history with human attestation tracking

**New: Part 11 Compliance**  
CDIL now includes a comprehensive database schema designed to support FDA 21 CFR Part 11 requirements, including:
- Secure, tamper-evident audit trails (hash-chained event ledger)
- Binding electronic signatures with certificate chains
- Complete version history with diff tracking
- PHI-safe storage with hashed patient references
- Defense bundle exports for litigation and payer appeals

See [Part 11 Compliance Documentation](docs/PART11_COMPLIANCE.md) for details.

---

## What CDIL Is NOT

CDIL is **infrastructure**, not a complete solution. It is:

- ❌ Not a full RCM (Revenue Cycle Management) platform
- ❌ Not a CDI (Clinical Documentation Improvement) coding engine
- ❌ Not an Epic plugin or EHR integration
- ❌ Not a billing optimizer

CDIL sits **between AI output and payer/auditor scrutiny**, providing cryptographic integrity and evidence deficit intelligence.

---

## Phase 1 Scope

This implementation focuses exclusively on **Evidence Bundle Export** and **Shadow Mode (Revenue Risk Intelligence)**:

### Evidence Integrity (Cryptographic)
- **Evidence Bundles (JSON)** - Structured bundles with certificate, verification instructions, and public key references
- **Evidence Bundles (ZIP)** - Complete archive with certificate.json, certificate.pdf, evidence_bundle.json, verification_report.json
- **Per-Tenant Keys** - Cryptographic isolation across organizations (no cross-tenant forgery)
## 🎯 Shadow Mode: The Most Incredible Sidecar

CDIL can run **alongside** existing documentation workflows (AI or non-AI) without requiring Epic integration. This makes it perfect for specialist pilots and proof-of-concept deployments.

### What Shadow Mode Does

**Ingest & Analyze (Read-Only):**
- `POST /v1/shadow/intake` - Ingest clinical notes for retrospective analysis
- PHI-safe by default: only hashes stored (plaintext NOT stored unless explicitly configured)
- Tenant-isolated: per-organization cryptographic keys and data separation

**Issue Verifiable Certificates:**
- Cryptographically signed integrity certificates
- SHA-256 hashing of note content
- Tamper-evident with offline verification support

**Export Defense Bundles:**
- `GET /v1/certificates/{id}/evidence-bundle.zip` - Complete evidence package
- Includes: certificate.json, certificate.pdf, verification_report.json, public_key.pem, README.txt
- OpenSSL-compatible offline verification
- Courtroom/appeal-ready artifacts

**Surface Outcomes via Dashboard:**
- `GET /v1/dashboard/executive-summary` - Notes reviewed, risk indicators, defensibility metrics
- `GET /v1/dashboard/risk-queue` - Prioritized worklist for CDI specialists
- `POST /v1/defense/simulate-alteration` - Proof demo (PASS original, FAIL mutated)

### Shadow Mode Benefits

✅ **No EMR Integration Required** - Pilot without vendor dependencies  
✅ **PHI-Safe by Default** - Only hashes stored, not plaintext  
✅ **Litigation-Grade Evidence** - Cryptographically verifiable bundles  
✅ **Executive Dashboard** - Prove it works in 10 seconds  
✅ **Tenant Isolation** - Per-organization keys and data separation  
✅ **Offline Verification** - No API required to verify integrity  

---

## Phase 1 Scope (This PR)

This implementation focuses on **Shadow Mode Sidecar + Evidence Bundle Export + Executive Dashboard**:

- **Shadow Mode Ingestion** - Read-only note intake with PHI-safe hashing
- **Evidence Bundles (JSON)** - Structured bundles with certificate, verification instructions, and public key references
- **Evidence Bundles (ZIP)** - Complete archive with certificate.json, certificate.pdf, evidence_bundle.json, verification_report.json, README.txt, public_key.pem
- **Executive Dashboard** - Summary metrics, risk queue, and defense simulation
- **Per-Tenant Keys** - Cryptographic isolation across organizations
- **Offline Verification** - Bundles can be verified without API access

### Shadow Mode (Revenue Intelligence)
- **Evidence Deficit Scoring** - Deterministic analysis of documentation gaps
- **Revenue Risk Modeling** - Transparent calculations of potential denial risk
- **Executive Dashboard** - CFO-friendly metrics (% defensible, annual revenue leakage)
- **No EMR Integration** - Operates on exported note batches for pilot deployments

**Not Included in Phase 1:**
- Vendor Registry (Phase 2)
- Model Governance (Phase 3)
- Gatekeeper Mode (Phase 4)

These features will be implemented in separate PRs with dedicated threat models, migrations, and tests.

---

## 🚀 Quick Start: Shadow Mode Pilot

### 1. Deploy with Docker Compose

```bash
# Generate JWT secret
export JWT_SECRET_KEY=$(openssl rand -base64 32)

# Start CDIL
docker-compose up -d

# Check health
curl http://localhost:8000/v1/health/status
```

### 2. Ingest Clinical Notes (Shadow Mode)

```bash
# Get JWT token (in production, use proper authentication)
TOKEN="your-jwt-token"

# Ingest a note
curl -X POST http://localhost:8000/v1/shadow/intake \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "note_text": "Patient presents with acute chest pain...",
    "encounter_id": "ENC-12345",
    "note_type": "progress"
  }'

# Response includes shadow_id, note_hash, timestamp
```

### 3. View Executive Dashboard

```bash
# Get summary metrics
curl http://localhost:8000/v1/dashboard/executive-summary \
  -H "Authorization: Bearer $TOKEN"

# Get risk queue (high-risk notes needing review)
curl http://localhost:8000/v1/dashboard/risk-queue?band=HIGH \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Issue Certificates & Export Bundles

```bash
# Issue certificate for AI-generated note
curl -X POST http://localhost:8000/v1/clinical/documentation \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "note_text": "Patient presents with...",
    "model_version": "gpt-4-medical-v1",
    "patient_hash": "..."
  }'

# Export defense bundle (ZIP)
curl http://localhost:8000/v1/certificates/{cert-id}/evidence-bundle.zip \
  -H "Authorization: Bearer $TOKEN" \
  -o evidence-bundle.zip
```

### 5. Demonstrate Tamper Detection

```bash
# Simulate alteration to show PASS vs FAIL
curl -X POST http://localhost:8000/v1/defense/simulate-alteration \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "certificate_id": "cert-123",
    "mutated_note_text": "Patient presents with ALTERED CONTENT..."
  }'

# Response shows:
# - Original: PASS (integrity confirmed)
# - Mutated: FAIL (hash mismatch detected)
# - Explanation of what broke and why
```

---

## 📋 Security Documentation

**Phase 1 Security Boundaries:**
- Per-tenant cryptographic keys (no cross-tenant forgery)
- PHI properly hashed, never stored in plaintext (unless STORE_NOTE_TEXT=true)
- Tenant isolation at API and DB layers
- Nonce-based replay protection
- Role-based access control (clinician, auditor, admin)

**For detailed security analysis, see:**
- [Deployment Hardening Guide](./docs/DEPLOYMENT_HARDENING.md) - TLS, key rotation, logging, backups, hospital network deployment
- [Integrity Artifact Spec](./docs/INTEGRITY_ARTIFACT_SPEC.md) - Canonical formats for certificates and evidence bundles
- [Threat Model & Trust Guarantees](./docs/THREAT_MODEL_AND_TRUST_GUARANTEES.md) - Security contract, attacker model, STRIDE analysis

**Known Limitations:**
- This is a Phase 1 implementation focused on Shadow Mode and evidence export
- Production deployment requires additional hardening (see Deployment Hardening Guide)
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

## Deployment

### Quick Start with Docker

```bash
# Build image
docker build -t cdil-gateway:v1.0.0 .

# Run with Docker Compose
docker-compose up -d

# Check health
curl http://localhost:8000/healthz
```

### Running Without Docker

For development or environments where Docker is not available:

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export PYTHONPATH=$(pwd)
export CDIL_DB_PATH=./data/eli_sentinel.db

# Run directly with uvicorn
uvicorn gateway.app.main:app --host 0.0.0.0 --port 8000
```

**See [docs/RUNNING_WITHOUT_DOCKER.md](docs/RUNNING_WITHOUT_DOCKER.md) for complete non-Docker setup instructions including:**
- Virtual environment setup
- Environment configuration
- Development vs. production modes
- Process management with systemd
- Performance tuning
- Troubleshooting

### Production Deployment

**See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for complete production deployment instructions including:**

- Environment variables and secrets management
- TLS/HTTPS configuration
- Key rotation procedures
- Logging, monitoring, and PHI handling
- High availability and scaling guidance
- Kubernetes manifests and examples

**⚠️ CRITICAL:** Production deployments MUST NOT use the dev secret key (it is committed to git and COMPROMISED). Use AWS Secrets Manager, Azure Key Vault, or GCP Secret Manager.

**Security Documentation:**
- [Per-Tenant Key Security](docs/PER_TENANT_KEY_SECURITY.md) - Guarantees about cross-tenant isolation
- [Production Readiness Checklist](docs/PRODUCTION_READINESS.md) - Complete hardening checklist
- [Threat Model](docs/THREAT_MODEL_AND_TRUST_GUARANTEES.md) - Security architecture and trust boundaries

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
# Run smoke tests (verifies basic functionality)
./tools/smoke-test-local.sh   # Test local deployment
./tools/smoke-test-docker.sh  # Test Docker deployment

# Run unit tests
PYTHONPATH=$PWD ENV=TEST DISABLE_RATE_LIMITS=1 pytest

# Run specific test files
pytest gateway/tests/test_evidence_bundle.py -v
pytest gateway/tests/test_clinical_endpoints.py -v
pytest gateway/tests/test_part11_compliance.py -v
```

**Smoke Tests**: Always run smoke tests before submitting a PR to ensure the gateway can start and respond to health checks. See [tools/README.md](tools/README.md) for details.

**Copilot Guidelines**: See [.github/copilot-instructions.md](.github/copilot-instructions.md) for important rules when working with Copilot on this repository.

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

---

## 🛡️ Denial Shield: Deterministic MEAT Scorer

The Denial Shield MEAT Scorer is a **deterministic, explainable** risk assessment engine that evaluates clinical documentation for denial risk based on **MEAT criteria** (Monitor/Evaluate/Assess/Treat). 

### What It Does

Analyzes documentation for high-value diagnoses and checks for MEAT anchors:
- **Diabetes** (Type 1 & 2)
- **Hypertension**
- **Congestive Heart Failure (CHF)**

### Key Features

✅ **Deterministic** - Same input always produces same output (no LLM calls)  
✅ **Explainable** - Every point deduction has a stable rule_id and reason  
✅ **Actionable** - Provides specific fix guidance for each deficit  
✅ **Revenue-Aware** - Estimates preventable revenue loss ($142 for outpatient E/M Level 5→3 downcoding)

### API Endpoint

```bash
POST /v1/shadow/evidence-deficit
```

**Request Example:**

```json
{
  "note_text": "Patient with diabetes presents for follow-up. A1C 7.5% today...",
  "encounter_type": "outpatient",
  "service_line": "medicine",
  "diagnoses": ["Type 2 diabetes mellitus"],
  "procedures": [],
  "labs": [],
  "vitals": [],
  "problem_list": ["Diabetes"],
  "meds": ["Metformin 1000mg"]
}
```

**Response Structure:**

```json
{
  "evidence_sufficiency": {
    "score": 75,
    "band": "low",
    "explain": [
      {
        "rule_id": "DIAB_MONITOR_MISSING",
        "impact": 25,
        "reason": "Diabetes documented but no monitoring data (glucose, A1C, CGM)"
      }
    ]
  },
  "deficits": [
    {
      "id": "DEF-DIAB-M",
      "title": "Diabetes: Missing Monitor",
      "category": "monitor",
      "condition": "diabetes",
      "missing": ["A1C", "glucose monitoring", "fingerstick"],
      "fix": "Add A1C value or state CGM/fingerstick monitoring plan (frequency + target range)."
    }
  ],
  "denial_risk": {
    "score": 25,
    "band": "low",
    "primary_reasons": [
      "Diabetes documented but no monitoring data (glucose, A1C, CGM)"
    ]
  },
  "revenue_estimate": 0.0,
  "headline": "Low denial risk: documentation appears sufficient for submission.",
  "next_best_actions": [
    "Address the missing MEAT items listed.",
    "Add explicit clinical rationale linking assessment to plan.",
    "Re-run Denial Shield after edits before claim submission."
  ]
}
```

### Risk Bands

| Risk Score | Band | Meaning |
|---|---|---|
| 0-30 | **LOW** | Documentation appears sufficient |
| 31-60 | **MODERATE** | Improve specificity to prevent downcoding |
| 61-80 | **HIGH** | Missing MEAT anchors likely to trigger denials |
| 81-100 | **CRITICAL** | Fix documentation before submission |

### Scoring Rules

**General Rules:**
- Note < 400 chars: +15 risk
- No diagnoses provided: +20 risk
- Vague plan (e.g., "continue current", "follow up"): +10 risk

**MEAT Rules (per diagnosis):**
- Missing **Monitor**: +25 risk (e.g., no A1C for diabetes, no BP for HTN)
- Missing **Evaluate**: +15 risk (e.g., no "controlled/uncontrolled" status)
- Missing **Assess**: +15 risk (e.g., diagnosis not mentioned in assessment section)
- Missing **Treat**: +25 risk (e.g., no medications documented)

### Revenue Estimate

- **Outpatient** encounter with **risk > 60**: $142.00 (estimated delta for Level 5→3 downcode)
- All other scenarios: $0.00

### MEAT Anchor Keywords

**Diabetes:**
- Monitor: `glucose`, `blood sugar`, `fingerstick`, `A1C`, `HbA1c`, `CGM`
- Evaluate: `controlled`, `uncontrolled`, `at goal`, `above goal`, `improving`, `worsening`
- Treat: `metformin`, `insulin`, `GLP-1`, `semaglutide`, `ozempic`, `dose`, `increase`, `decrease`

**Hypertension:**
- Monitor: `BP`, `blood pressure`, `home BP`, `ambulatory`, `log`
- Evaluate: `controlled`, `uncontrolled`, `at goal`, `improving`
- Treat: `lisinopril`, `amlodipine`, `losartan`, `HCTZ`, `metoprolol`, `carvedilol`

**CHF:**
- Monitor: `weight`, `daily weight`, `edema`, `swelling`, `I/O`, `dyspnea`
- Evaluate: `euvolemic`, `volume overloaded`, `improving`, `worsening`, `stable`, `exacerbation`
- Assess: `HFrEF`, `HFpEF`, `EF`, `ejection fraction`, `NYHA`
- Treat: `furosemide`, `Lasix`, `Entresto`, `beta blocker`, `spironolactone`, `SGLT2i`, `diuretic`

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

## Contributing & PR Management

### Managing Copilot PRs

This repository uses GitHub Copilot for automated development. To manage stale or failed PRs:

**Quick cleanup of stale PRs:**
```bash
# List stale [WIP] PRs (dry run)
python tools/manage_stale_prs.py --dry-run

# Close stale PRs with no activity in 7+ days
python tools/manage_stale_prs.py --days 7 --close
```

**Manual cleanup with GitHub CLI:**
```bash
# List open Copilot PRs
gh pr list --author Copilot --state open

# Close specific PRs
gh pr close <PR_NUMBER> --comment "Closing stale [WIP] PR"
```

**For detailed guidance, see:**
- [Managing Copilot PRs Guide](docs/MANAGING_COPILOT_PRS.md) - Complete guide for handling failed/stale PRs
- Automated cleanup runs weekly via GitHub Actions (`.github/workflows/close-stale-prs.yml`)

---

## License

See LICENSE file for details.
