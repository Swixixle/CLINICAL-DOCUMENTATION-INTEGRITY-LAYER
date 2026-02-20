# Contract Snapshot

**Authoritative source:** OpenAPI spec served at `/docs` by the running application.

This file is generated from the deployed contract and must be updated whenever routes change.
No endpoint documented here may be added unless it appears in `/docs`.

---

## Endpoint List (from OpenAPI)

### Service

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | None | Service root / liveness |
| GET | `/healthz` | None | Simple liveness check |
| GET | `/v1/health/status` | None | Detailed service status |

### Certificate Lifecycle

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/v1/clinical/documentation` | JWT | Issue integrity certificate for an AI-generated clinical note |
| GET | `/v1/certificates/{certificate_id}` | JWT | Retrieve a certificate by ID |
| POST | `/v1/certificates/{certificate_id}/verify` | JWT | Verify cryptographic integrity of a certificate |
| POST | `/v1/certificates/query` | JWT | List and filter certificates for the authenticated tenant |

### Evidence Export

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/v1/certificates/{certificate_id}/defense-bundle` | JWT | Download tamper-evident defense bundle (ZIP) |
| GET | `/v1/certificates/{certificate_id}/evidence-bundle.json` | JWT | Evidence bundle as structured JSON |
| GET | `/v1/certificates/{certificate_id}/evidence-bundle.zip` | JWT | Evidence bundle as ZIP archive |
| GET | `/v1/certificates/{certificate_id}/pdf` | JWT | PDF certificate document |

### Keys & Transactions

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/v1/keys` | None | List all public keys for the service |
| GET | `/v1/keys/{key_id}` | None | Retrieve a specific public key by ID |
| GET | `/v1/transactions/{transaction_id}` | None | Retrieve a HALO accountability packet |
| POST | `/v1/transactions/{transaction_id}/verify` | None | Verify HALO chain integrity of a transaction |

### Shadow Mode (Revenue Intelligence)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/v1/shadow/intake` | JWT | Ingest a clinical note for PHI-safe shadow analysis |
| GET | `/v1/shadow/items` | JWT | List shadow intake items with optional filters |
| GET | `/v1/shadow/items/{shadow_id}` | JWT | Retrieve a specific shadow intake item |
| POST | `/v1/shadow/analyze` | JWT | Batch note analysis |
| POST | `/v1/shadow/evidence-deficit` | JWT | MEAT scoring / evidence-deficit analysis for a single note |
| GET | `/v1/shadow/dashboard` | JWT | Denial risk dashboard with aggregate metrics |
| POST | `/v1/shadow/leakage-report` | JWT | Revenue leakage report |

### Dashboard & Defense Demo

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/v1/dashboard/executive-summary` | JWT | Executive summary metrics |
| GET | `/v1/dashboard/risk-queue` | JWT | Prioritized high-risk note queue |
| POST | `/v1/defense/simulate-alteration` | JWT | Demonstrate tamper detection (PASS → FAIL on modified note) |
| GET | `/v1/defense/demo-scenario` | JWT | Pre-packaged tamper detection demo (synthetic data, no PHI) |

### AI Gateway & Analytics

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/v1/ai/call` | None | AI call with full HALO governance and accountability packet |
| POST | `/v1/mock/summarize` | None | Mock AI summarization endpoint (dev/test only) |
| POST | `/v2/analytics/roi-projection` | None | ROI projection (no PHI, stateless computation) |

---

## Defense Bundle Schema

The defense bundle is a ZIP archive downloaded via
`GET /v1/certificates/{certificate_id}/defense-bundle`.

### ZIP Contents

| File | Description |
|---|---|
| `certificate.json` | Complete certificate with all provenance fields |
| `canonical_message.json` | Exact JSON object that was signed (for hash recomputation) |
| `verification_report.json` | Verification status at time of bundle generation |
| `public_key.pem` | Signer's EC P-256 public key |
| `README.txt` | Step-by-step offline verification instructions |

### `certificate.json` Top-Level Fields

| Field | Type | Description |
|---|---|---|
| `certificate_id` | string (UUID7) | Unique certificate identifier |
| `tenant_id` | string | Issuing tenant |
| `issued_at_utc` | ISO 8601 string | Issuance timestamp |
| `note_hash` | `sha256:<hex>` | SHA-256 hash of note content |
| `patient_hash` | `sha256:<hex>` | SHA-256 hash of patient identifier |
| `model_version` | string | Model label at issuance |
| `human_reviewed` | boolean | Human review flag |
| `human_reviewer_id_hash` | string \| null | Hash of reviewer ID (if reviewed) |
| `human_attested_at_utc` | ISO 8601 string \| null | Human attestation timestamp |
| `governance_policy_hash` | string | Hash of governance policy version |
| `signature` | object | Cryptographic signature bundle (see below) |
| `integrity_chain` | object | HALO chain linkage (see below) |

### `certificate.json` → `signature` Fields

| Field | Type | Description |
|---|---|---|
| `algorithm` | string | `ECDSA_SHA_256` |
| `key_id` | string | Identifier of signing key |
| `signature` | string | Base64-encoded ASN.1 DER signature over canonical message |
| `canonical_message` | object | The exact object that was signed |

### `certificate.json` → `integrity_chain` Fields

| Field | Type | Description |
|---|---|---|
| `chain_hash` | `sha256:<hex>` | Hash of this certificate block |
| `previous_hash` | `sha256:<hex>` \| null | Hash of preceding certificate (null for first) |

### Cryptographic Parameters

| Parameter | Value |
|---|---|
| Signature algorithm | ECDSA_SHA_256 |
| Curve | P-256 (secp256r1) |
| Signature encoding | ASN.1 DER, Base64 |
| Hash function | SHA-256 |
| Canonicalization | `json_c14n_v1` — sorted keys, no whitespace, UTF-8 |
| HALO version | v1 |

### `canonical_message.json` Fields (All Included in Signature)

All fields below are covered by the ECDSA signature. See [`docs/BUNDLE_SPEC.md`](BUNDLE_SPEC.md) for the complete list of what is signed vs. not signed.

- `certificate_id`
- `chain_hash`
- `governance_policy_hash`
- `human_attested_at_utc`
- `human_reviewed`
- `human_reviewer_id_hash`
- `issued_at_utc`
- `model_version`
- `note_hash`
- `patient_hash`
- `previous_hash`

### Offline Verification

```bash
python tools/verify_bundle.py bundle.zip
```

Exit codes:

| Code | Meaning |
|---|---|
| `0` | PASS — certificate valid and unmodified |
| `1` | FAIL — tampering detected or verification failed |
| `2` | ERROR — invalid bundle or technical error |

---

## Confirmation

All 29 endpoints listed above are present in the OpenAPI spec served by the deployed application.
No endpoint documented here is speculative or roadmap-only.
Roadmap items are documented in [README.md — Roadmap](../README.md#roadmap).
