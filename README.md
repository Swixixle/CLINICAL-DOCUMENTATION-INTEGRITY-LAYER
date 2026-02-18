# Clinical Documentation Integrity Layer (CDIL)

> **"If it's not exportable and understandable by a lawyer, it didn't happen."**

CDIL provides cryptographically verifiable integrity certificates for AI-generated clinical documentation. Every certificate is **exportable, independently verifiable, and legally defensible**.

---

## Evidence Mode: The Primary Use Case

CDIL is designed for **evidentiary use cases** — providing tamper-evident proof that can be handed to auditors, regulators, and legal counsel.

### What You Hand to a Lawyer

When questioned about AI-generated clinical documentation, you provide:

1. **Certificate PDF** — Formal document showing model version, policy version, human review status, and cryptographic seal
2. **Evidence Bundle** — Complete ZIP archive containing certificate.json, certificate.pdf, verification_report.json, and README_VERIFICATION.txt
3. **Verification Proof** — Demonstrate that the certificate passes all integrity checks (timing, chain hash, signature)

---

## 📋 Security Documentation

**Critical:** Before production deployment, review the comprehensive security documentation:

- **[Threat Model & Trust Guarantees](./docs/THREAT_MODEL_AND_TRUST_GUARANTEES.md)** - Complete security contract, attacker model, STRIDE analysis, and vulnerability assessment
- **[Security Audit Summary](./docs/SECURITY_AUDIT_SUMMARY.md)** - Executive summary with critical findings and remediation timeline
- **[Security Documentation Guide](./docs/README_SECURITY.md)** - Navigation guide for security docs and automated tests

**Key findings:**
- ⚠️ **Critical Gap**: Single global key enables cross-tenant forgery (pre-production blocker)
- ✅ PHI properly hashed, never stored in plaintext
- ✅ Tenant isolation at DB layer works correctly
- ✅ 11 automated security tests passing

See [remediation timeline](./docs/SECURITY_AUDIT_SUMMARY.md#9-remediation-timeline) for production readiness requirements.

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

### 3. Export Evidence Bundle

```bash
GET /v1/certificates/{id}/bundle
Headers: X-Tenant-Id: hospital-alpha
```

Returns ZIP with: certificate.json, certificate.pdf, verification_report.json, README_VERIFICATION.txt

### 4. Query Certificates for Audit

```bash
POST /v1/certificates/query
Body: {"tenant_id": "hospital-alpha", "date_from": "...", "human_reviewed": true}
```

Filters: tenant_id, date range, model_version, policy_version, human_reviewed, pagination

---

## API Endpoints

### Certificate Issuance
- `POST /v1/clinical/documentation` — Issue certificate

### Certificate Retrieval
- `GET /v1/certificates/{id}` — Get certificate (requires X-Tenant-Id)
- `POST /v1/certificates/{id}/verify` — Verify certificate (requires X-Tenant-Id)

### Evidence Export
- `GET /v1/certificates/{id}/pdf` — Download PDF (requires X-Tenant-Id)
- `GET /v1/certificates/{id}/bundle` — Download evidence bundle (requires X-Tenant-Id)

### Audit & Reporting
- `POST /v1/certificates/query` — Query with filters

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

Test endpoints:
```bash
curl -X POST http://localhost:8000/v1/clinical/documentation \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"test","model_version":"gpt-4","note_text":"Test note","human_reviewed":true,...}'
```

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

# Test ROI endpoint
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

1. **Regulatory Audit** — Export evidence bundles, demonstrate offline verification
2. **Medical Malpractice Litigation** — Prove note content unchanged since issuance
3. **Internal Quality Review** — Audit trail of AI-generated notes
4. **Financial Planning** — ROI modeling for CDIL deployment business case

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
