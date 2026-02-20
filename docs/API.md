# CDIL API Reference

All endpoints are served at `http://{host}:{port}`. Default port: `8000`.

**Authentication:** All protected endpoints require a JWT Bearer token in the `Authorization` header unless noted otherwise. Use `JWT_SECRET_KEY` and `JWT_ALGORITHM` from your environment configuration.

**Tenant isolation:** The `tenant_id` is derived from the authenticated JWT identity — it is never read from the request body for privileged operations.

**PHI policy:** Request and response bodies never contain plaintext note text or raw patient identifiers. Only SHA-256 hashes are accepted and returned.

---

## Health

### `GET /healthz`

Simple liveness check. No authentication required.

**Response `200 OK`:**
```json
{"status": "ok"}
```

---

### `GET /v1/health/status`

Detailed service status. No authentication required.

**Response `200 OK`:**
```json
{
  "status": "healthy",
  "service": "CDIL Gateway",
  "version": "0.1.0",
  "database": "connected"
}
```

---

## Certificate Lifecycle

### `POST /v1/clinical/documentation`

Issue an integrity certificate for an AI-generated clinical note.

**Headers:**
```
Authorization: Bearer <jwt>
Content-Type: application/json
```

**Request body:**
```json
{
  "note_text": "<plaintext note — hashed before storage, never persisted by default>",
  "model_version": "<model identifier string, e.g. gpt-4-v1>",
  "patient_hash": "<sha256-hex of patient identifier — caller-computed>",
  "human_reviewed": false,
  "human_reviewer_id": "<reviewer id string — hashed before storage, optional>",
  "governance_policy_version": "<policy version string, optional>",
  "prompt_version": "<prompt template version, optional>"
}
```

**Response `200 OK`:**
```json
{
  "certificate_id": "<uuid7>",
  "status": "issued",
  "tenant_id": "<tenant>",
  "issued_at_utc": "2024-01-15T10:00:00Z",
  "note_hash": "sha256:<hex>",
  "model_version": "<model identifier>",
  "human_reviewed": false,
  "signature": {
    "algorithm": "ECDSA_SHA_256",
    "key_id": "<key-id>",
    "signature": "<base64-encoded ASN.1 DER signature>"
  },
  "integrity_chain": {
    "chain_hash": "<sha256-hex>",
    "previous_hash": "<sha256-hex or null>"
  }
}
```

---

### `GET /v1/certificates/{certificate_id}`

Retrieve a certificate by ID.

**Headers:**
```
Authorization: Bearer <jwt>
```

**Response `200 OK`:** Full certificate object (same structure as issuance response).

**Response `404`:** Certificate not found or belongs to a different tenant.

---

### `POST /v1/certificates/{certificate_id}/verify`

Verify the cryptographic integrity of a certificate.

**Headers:**
```
Authorization: Bearer <jwt>
```

**Response `200 OK`:**
```json
{
  "valid": true,
  "status": "PASS",
  "summary": "Certificate is valid and unmodified",
  "checks": {
    "chain_hash": "valid",
    "signature": "valid",
    "key": "found"
  },
  "failures": [],
  "human_friendly_report": {
    "status": "PASS",
    "summary": "Certificate is valid and unmodified",
    "reason": null,
    "recommended_action": null
  }
}
```

**Response when invalid:**
```json
{
  "valid": false,
  "status": "FAIL",
  "failures": [
    {
      "check": "signature",
      "code": "invalid_signature",
      "detail": null
    }
  ]
}
```

---

### `POST /v1/certificates/query`

List and filter certificates for the authenticated tenant.

**Headers:**
```
Authorization: Bearer <jwt>
Content-Type: application/json
```

**Request body (all fields optional):**
```json
{
  "date_from": "2024-01-01T00:00:00Z",
  "date_to": "2024-12-31T23:59:59Z",
  "model_version": "<filter by model version>",
  "human_reviewed": true,
  "limit": 50,
  "offset": 0
}
```

**Response `200 OK`:**
```json
{
  "total": 42,
  "certificates": [
    {
      "certificate_id": "<uuid7>",
      "issued_at_utc": "2024-01-15T10:00:00Z",
      "model_version": "<model>",
      "human_reviewed": true,
      "note_hash_prefix": "sha256:a3f9...",
      "chain_hash_prefix": "a1b2..."
    }
  ]
}
```

> **Note:** This is a demo/dev posture endpoint. In production, ensure pagination is enforced and tenant scoping is validated server-side.

---

## Evidence Export

### `GET /v1/certificates/{certificate_id}/defense-bundle`

Download a tamper-evident defense bundle (ZIP) for offline verification.

**Headers:**
```
Authorization: Bearer <jwt>
```

**Response `200 OK`:**
- Content-Type: `application/zip`
- Body: ZIP archive containing `certificate.json`, `canonical_message.json`, `verification_report.json`, `public_key.pem`, `README.txt`

**Verify offline:**
```bash
python tools/verify_bundle.py bundle.zip
```

---

### `GET /v1/certificates/{certificate_id}/evidence-bundle.json`

Evidence bundle as structured JSON (primary format for programmatic use).

**Headers:**
```
Authorization: Bearer <jwt>
```

**Response `200 OK`:**
```json
{
  "bundle_version": "2.0",
  "generated_at": "2024-01-15T10:01:00Z",
  "certificate": { "...": "full certificate object" },
  "metadata": { "certificate_id": "...", "tenant_id": "...", "algorithm": "ECDSA_SHA_256" },
  "hashes": { "note_hash": "sha256:...", "hash_algorithm": "SHA-256" },
  "human_attestation": { "reviewed": false, "reviewer_hash": null },
  "verification_instructions": {
    "offline_cli": "python tools/verify_bundle.py bundle.zip",
    "api_endpoint": "POST /v1/certificates/{id}/verify"
  }
}
```

---

### `GET /v1/certificates/{certificate_id}/evidence-bundle.zip`

Evidence bundle as ZIP archive (convenience format).

**Response:** ZIP containing `certificate.json`, `certificate.pdf`, `evidence_bundle.json`, `verification_report.json`, `README_VERIFICATION.txt`.

---

### `GET /v1/certificates/{certificate_id}/pdf`

PDF certificate document.

**Headers:**
```
Authorization: Bearer <jwt>
```

**Response `200 OK`:**
- Content-Type: `application/pdf`

---

## Ledger & Keys

### `GET /v1/keys/{key_id}`

Retrieve a tenant's public key for offline verification.

**Auth:** Not required (public key is public information).

**Response `200 OK`:**
```json
{
  "key_id": "<key-id>",
  "algorithm": "EC",
  "curve": "P-256",
  "public_key_pem": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n",
  "public_jwk": { "kty": "EC", "crv": "P-256", "x": "...", "y": "..." }
}
```

---

### `GET /v1/transactions/{transaction_id}`

Retrieve a HALO accountability packet (AI gateway transaction record).

**Response `200 OK`:** Full HALO chain packet.

---

### `POST /v1/transactions/{transaction_id}/verify`

Verify the HALO chain integrity of a transaction.

**Response `200 OK`:**
```json
{
  "valid": true,
  "failures": [],
  "checks": { "halo_chain": "valid", "signature": "valid" }
}
```

---

## Shadow Mode (Revenue Intelligence)

### `POST /v1/shadow/intake`

Ingest a clinical note for PHI-safe shadow analysis.

**Headers:**
```
Authorization: Bearer <jwt>
Content-Type: application/json
```

**Request body:**
```json
{
  "note_text": "<placeholder note text>",
  "encounter_id": "<encounter identifier>",
  "note_type": "progress"
}
```

**Response `200 OK`:**
```json
{
  "shadow_id": "<id>",
  "note_hash": "sha256:<hex>",
  "timestamp": "2024-01-15T10:00:00Z",
  "phi_safe": true
}
```

---

### `POST /v1/shadow/evidence-deficit`

Score a single note for documentation evidence deficits (MEAT criteria).

**Headers:**
```
Authorization: Bearer <jwt>
Content-Type: application/json
```

**Request body:**
```json
{
  "note_text": "<placeholder note text>",
  "encounter_type": "outpatient",
  "service_line": "medicine",
  "diagnoses": ["<diagnosis label>"],
  "procedures": [],
  "labs": [],
  "vitals": [],
  "problem_list": ["<problem>"],
  "meds": ["<medication>"]
}
```

**Response `200 OK`:**
```json
{
  "evidence_sufficiency": { "score": 75, "band": "low", "explain": [] },
  "deficits": [],
  "denial_risk": { "score": 25, "band": "low", "primary_reasons": [] },
  "revenue_estimate": 0.0,
  "headline": "Low denial risk: documentation appears sufficient for submission.",
  "next_best_actions": []
}
```

---

### `GET /v1/shadow/dashboard`

Denial risk dashboard with aggregate metrics.

**Query params:** `annual_note_volume` (integer, optional)

**Response `200 OK`:**
```json
{
  "total_notes": 100,
  "high_risk_count": 12,
  "moderate_risk_count": 28,
  "low_risk_count": 60,
  "estimated_annual_revenue_at_risk": 42000.0
}
```

---

## Dashboard & Defense Demo

### `GET /v1/dashboard/executive-summary`

Executive summary metrics.

**Headers:** `Authorization: Bearer <jwt>`

---

### `GET /v1/dashboard/risk-queue`

Prioritized risk queue for CDI review.

**Query params:** `band` (`HIGH` / `MODERATE` / `LOW`), `limit` (integer)

**Headers:** `Authorization: Bearer <jwt>`

---

### `POST /v1/defense/simulate-alteration`

Demonstrate tamper detection: show that modifying note content invalidates the certificate.

**Headers:**
```
Authorization: Bearer <jwt>
Content-Type: application/json
```

**Request body:**
```json
{
  "certificate_id": "<uuid7>",
  "modified_note_text": "<placeholder altered content — no real PHI>"
}
```

**Response `200 OK`:**
```json
{
  "tamper_detected": true,
  "reason": "NOTE_HASH_MISMATCH",
  "original_hash": "<original note hash>",
  "modified_hash": "<hash of modified text>",
  "verification_failed": true,
  "summary": "Tampering detected! The note content has been altered since certification."
}
```

---

### `GET /v1/defense/demo-scenario`

Pre-packaged tamper detection demo for presentations (uses synthetic data, no real PHI).

**Headers:** `Authorization: Bearer <jwt>`

**Response:** Full demo scenario with original cert, verification result, simulated alteration, and failure result.

---

## Error Responses

All error responses follow this structure to prevent PHI leakage:

```json
{
  "error": "<error_code>",
  "message": "<human-readable message — sanitized>"
}
```

Common codes: `certificate_not_found`, `validation_error`, `internal_error`, `unauthorized`.

Validation errors (422) include field names but **not field values**:

```json
{
  "error": "validation_error",
  "message": "Request validation failed",
  "details": [
    { "field": "body -> note_text", "type": "missing", "message": "Field required" }
  ]
}
```
