# Clinical Documentation Integrity Layer (CDIL)

> Cryptographically signed integrity certificates for AI-generated clinical documentation — exportable as a tamper-evident defense bundle, offline-verifiable without API access.

## System Scope (Authoritative Contract)

This repository implements an AI integrity gateway producing:

- HALO v1 tamper-evident chains
- ECDSA P-256 signatures over canonical messages
- Self-contained defense bundles
- Offline CLI verification

The authoritative contract is defined by OpenAPI (`/docs`) and the defense bundle schema in [`docs/BUNDLE_SPEC.md`](docs/BUNDLE_SPEC.md).

Endpoints or workflows not present in the OpenAPI spec at `/docs` are not implemented.

---

## What It Does

- **Issue integrity certificates** for AI-generated clinical notes (ECDSA P-256 / SHA-256, ASN.1 DER signature)
- **Hash-chain every certificate** to a per-tenant append-only ledger (prevents insertion / backdating)
- **Export defense bundles** (ZIP) containing certificate, canonical message, public key, and verification report
- **Verify offline** using [`tools/verify_bundle.py`](tools/verify_bundle.py) — no internet or API required
- **Score documentation** for evidence deficits and denial risk (deterministic MEAT rules, no LLM)
- **PHI-safe by default** — only SHA-256 hashes of note content and patient identifiers are stored

---

## Defense Bundle (Integrity Certificate)

A defense bundle is a ZIP archive downloaded via `GET /v1/certificates/{id}/defense-bundle`.

**Contents:**

| File | Description |
|---|---|
| `certificate.json` | Full certificate with all provenance fields |
| `canonical_message.json` | Exact JSON object that was signed (for hash recomputation) |
| `verification_report.json` | Verification status at time of bundle generation |
| `public_key.pem` | Signer's EC P-256 public key |
| `README.txt` | Step-by-step offline verification instructions |

**Cryptographic details:**
- Signature algorithm: **ECDSA P-256 / SHA-256**
- Signature encoding: **ASN.1 DER, Base64**
- HALO block hash spec: `sha256:hex(SHA256(UTF8(json_c14n_v1(block))))`
  - `json_c14n_v1` = sorted keys, no whitespace, UTF-8 (see [`gateway/app/services/c14n.py`](gateway/app/services/c14n.py))

---

## One-Press Workflow

1. Issue a certificate via `POST /v1/clinical/documentation`
2. The response contains a `certificate_id`
3. Download the defense bundle in one request:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/certificates/{certificate_id}/defense-bundle \
  -o bundle.zip
```

4. Verify offline (see next section)

For a demo walkthrough, see [`docs/DEMO.md`](docs/DEMO.md).

---

## Offline Verification

No network access, no API, no trust in a third party required.

```bash
python tools/verify_bundle.py bundle.zip
```

**What the verifier checks (4/4):**

| Check | What it verifies |
|---|---|
| 1. Canonical hash | `canonical_message.json` re-hashed from scratch — must match certificate |
| 2. ECDSA signature | `public_key.pem` verifies signature over canonical bytes |
| 3. Chain integrity | `chain_hash` and `previous_hash` linkage present and consistent |
| 4. Human attestation | `human_reviewed`, `human_reviewer_id_hash`, `human_attested_at_utc` are present in signed fields |

**Exit codes:**

| Code | Meaning |
|---|---|
| `0` | PASS — certificate valid and unmodified |
| `1` | FAIL — tampering detected or verification failed |
| `2` | ERROR — invalid bundle or technical error |

Source: [`tools/verify_bundle.py`](tools/verify_bundle.py)

---

## Trusted Time (TSA)

> **Status: Roadmap.** TSA integration is designed but not yet implemented in the current codebase. The env vars below are reserved for the planned implementation. See [`docs/TSA.md`](docs/TSA.md) for the full design.

CDIL is designed to support RFC 3161 Trusted Timestamp Authority (TSA) stamping of the certificate's canonical hash digest, providing an independent third-party time anchor.

**Only the SHA-256 digest of the canonical message is sent to the TSA — no PHI, no note content.**

**Planned environment variables:**

| Variable | Values | Description |
|---|---|---|
| `TSA_ENABLED` | `true` / `false` | Enable TSA stamping at issuance |
| `TSA_MODE` | `mock` / `real` | `mock` uses a local stub; `real` calls an RFC 3161 endpoint |
| `TSA_REQUIRED` | `true` / `false` | Fail certificate issuance if TSA is unavailable |
| `TSA_URL` | URL | RFC 3161 TSA endpoint (only used when `TSA_MODE=real`) |
| `TSA_TIMEOUT_MS` | integer | Request timeout in milliseconds |

**Important:** `TSA_MODE=mock` provides a timestamp stub for testing and demo purposes. It is **not** courtroom-grade by itself. `TSA_MODE=real` with a trusted RFC 3161 provider produces a legally significant time anchor.

See [`docs/TSA.md`](docs/TSA.md) for an explanation of what RFC 3161 provides and what is verified offline.

---

## API Endpoints

Full request/response details: [`docs/API.md`](docs/API.md)

Complete snapshot with auth requirements: [`docs/CONTRACT_SNAPSHOT.md`](docs/CONTRACT_SNAPSHOT.md)

This list is derived verbatim from the OpenAPI spec at `/docs`.

### Service

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | None | Service root / liveness |
| GET | `/healthz` | None | Simple liveness check |
| GET | `/v1/health/status` | None | Detailed service status |

### Certificate Lifecycle

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/v1/clinical/documentation` | JWT | Issue integrity certificate |
| GET | `/v1/certificates/{id}` | JWT | Retrieve certificate |
| POST | `/v1/certificates/{id}/verify` | JWT | Verify certificate integrity |
| POST | `/v1/certificates/query` | JWT | List / filter certificates |

### Evidence Export

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/v1/certificates/{id}/defense-bundle` | JWT | Download tamper-evident defense bundle (ZIP) |
| GET | `/v1/certificates/{id}/evidence-bundle.json` | JWT | Evidence bundle (structured JSON) |
| GET | `/v1/certificates/{id}/evidence-bundle.zip` | JWT | Evidence bundle (ZIP archive) |
| GET | `/v1/certificates/{id}/pdf` | JWT | PDF certificate |

### Keys & Transactions

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/v1/keys` | None | List public keys |
| GET | `/v1/keys/{key_id}` | None | Retrieve public key for offline verification |
| GET | `/v1/transactions/{id}` | None | Retrieve HALO accountability packet |
| POST | `/v1/transactions/{id}/verify` | None | Verify HALO chain integrity |

### Shadow Mode (Revenue Intelligence)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/v1/shadow/intake` | JWT | Ingest note for PHI-safe shadow analysis |
| GET | `/v1/shadow/items` | JWT | List shadow intake items |
| GET | `/v1/shadow/items/{shadow_id}` | JWT | Retrieve shadow intake item by ID |
| POST | `/v1/shadow/analyze` | JWT | Batch note analysis |
| POST | `/v1/shadow/evidence-deficit` | JWT | MEAT scoring for a single note |
| GET | `/v1/shadow/dashboard` | JWT | Denial risk dashboard |
| POST | `/v1/shadow/leakage-report` | JWT | Revenue leakage report |

### Dashboard & Defense Demo

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/v1/dashboard/executive-summary` | JWT | Executive metrics |
| GET | `/v1/dashboard/risk-queue` | JWT | Prioritized high-risk note queue |
| POST | `/v1/defense/simulate-alteration` | JWT | Demonstrate PASS then FAIL on tampered note |
| GET | `/v1/defense/demo-scenario` | JWT | Pre-packaged tamper demo for presentations |

### AI Gateway & Analytics

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/v1/ai/call` | None | AI call with HALO accountability packet |
| POST | `/v1/mock/summarize` | None | Mock AI summarization (dev/test) |
| POST | `/v2/analytics/roi-projection` | None | ROI projection (no PHI, stateless computation) |

> **Note:** The `POST /v1/certificates/query` listing endpoint returns certificates scoped to the authenticated tenant. In production, ensure pagination limits are enforced. See [Roadmap](#roadmap).

---

## Truth Table

What CDIL **proves** and what it explicitly **does not prove**:

| Claim | Proven? | How |
|---|---|---|
| Note content has not changed since certification | Yes | SHA-256 hash of note text is signed |
| Certificate has not been tampered with | Yes | ECDSA P-256 signature over canonical message |
| Certificate belongs to its chain (no insertion) | Yes | `chain_hash` links to previous certificate |
| Governance policy version was recorded | Yes | `governance_policy_hash` is in signed message |
| Human review flag was set at issuance | Yes | `human_reviewed` + `human_reviewer_id_hash` are signed |
| Offline verification is possible | Yes | `tools/verify_bundle.py` requires no network |
| Identity of the reviewer is proven | No | Only a hash of the reviewer ID is stored |
| The specific AI model actually executed | No | `model_version` is a label, not a model execution proof |
| Clinical accuracy or appropriateness | No | CDIL is an integrity layer, not a clinical validator |
| HIPAA compliance certification | No | CDIL is a component; compliance requires a full program review |
| Trusted third-party timestamp (TSA) | Not yet | TSA support is on the roadmap; see [`docs/TSA.md`](docs/TSA.md) |

See [`docs/SECURITY_SCOPE.md`](docs/SECURITY_SCOPE.md) for the full threat model.

---

## Security Posture

- **PHI-safe:** Note text is hashed (SHA-256) before storage. Plaintext is never persisted unless `STORE_NOTE_TEXT=true` (off by default).
- **Patient references:** Hashed before storage. Raw patient IDs are never written to disk.
- **Per-tenant signing keys:** ECDSA P-256. No key material is shared across tenants.
- **Nonce-based replay protection:** Each certificate issuance consumes a UUID7 nonce recorded in the database.
- **Append-only ledger:** Audit events are hash-chained; modifying any event breaks the chain.
- **Dev auth boundary:** The default JWT key (`dev-key-01`) is committed to this repo and is **NOT safe for production**. Replace with a secret from AWS Secrets Manager, Azure Key Vault, or similar before any production deployment.

See [`docs/SECURITY_SCOPE.md`](docs/SECURITY_SCOPE.md) and [`docs/DEPLOYMENT_HARDENING.md`](docs/DEPLOYMENT_HARDENING.md).

---

## Quickstart

### Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set required env vars
export PYTHONPATH=$(pwd)
export JWT_SECRET_KEY=$(openssl rand -base64 32)
export CDIL_DB_PATH=./data/cdil.db

# Start the server
uvicorn gateway.app.main:app --reload --port 8000

# Health check
curl http://localhost:8000/healthz
```

### Run with Docker Compose

```bash
export JWT_SECRET_KEY=$(openssl rand -base64 32)
docker-compose up -d
curl http://localhost:8000/v1/health/status
```

### Issue a Certificate and Verify Offline

```bash
TOKEN="your-jwt-token"

# 1. Issue certificate
CERT_ID=$(curl -s -X POST http://localhost:8000/v1/clinical/documentation \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "note_text": "<placeholder — replace with note text, no real PHI in demos>",
    "model_version": "gpt-4-v1",
    "patient_hash": "<sha256-hex-of-patient-id>"
  }' | python -c "import sys,json; print(json.load(sys.stdin)['certificate_id'])")

# 2. Download defense bundle
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/v1/certificates/$CERT_ID/defense-bundle" \
  -o bundle.zip

# 3. Verify offline
python tools/verify_bundle.py bundle.zip
# Exit 0 = PASS
```

For a 60-second end-to-end walkthrough including tamper detection, see [`docs/DEMO.md`](docs/DEMO.md).

### Run Tests

```bash
# Unit tests (rate limiting disabled automatically in TEST mode)
PYTHONPATH=$PWD ENV=TEST DISABLE_RATE_LIMITS=1 pytest

# Smoke tests
./tools/smoke-test-local.sh
./tools/smoke-test-docker.sh
```

---

## Roadmap

- **Tenant scoping for listing endpoints** — `POST /v1/certificates/query` is currently scoped to the authenticated tenant; add explicit pagination limits and cursor-based paging for large deployments.
- **Production auth** — Replace dev JWT with an org-managed identity provider (OIDC/SAML). The current dev secret key is committed to this repo.
- **TSA integration (RFC 3161)** — Add mock and real TSA stamping at issuance; add TSA imprint match to offline verifier. See [`docs/TSA.md`](docs/TSA.md).
- **Full TSA PKI chain validation** — Offline verifier will optionally validate the TSA token's certificate chain against a trusted root.
- **Vendor Registry (Phase 2)** — Register AI vendors, models, and public keys.
- **Model Governance (Phase 3)** — Per-tenant model allowlists and governance policy enforcement.
- **Gatekeeper Mode (Phase 4)** — Pre-commit EHR verification and commit token issuance.

---

## Additional Documentation

| Document | Description |
|---|---|
| [`docs/CONTRACT_SNAPSHOT.md`](docs/CONTRACT_SNAPSHOT.md) | Authoritative endpoint list (from OpenAPI) + defense bundle schema |
| [`docs/BUNDLE_SPEC.md`](docs/BUNDLE_SPEC.md) | Formal defense bundle field-by-field specification |
| [`docs/DEMO.md`](docs/DEMO.md) | 60-second demo: issue, verify, tamper, FAIL |
| [`docs/API.md`](docs/API.md) | Full API reference with example payloads |
| [`docs/TSA.md`](docs/TSA.md) | TSA design: mock vs real, RFC 3161, offline imprint check |
| [`docs/SECURITY_SCOPE.md`](docs/SECURITY_SCOPE.md) | Truth Table + threat model in plain language |
| [`docs/DEPLOYMENT_HARDENING.md`](docs/DEPLOYMENT_HARDENING.md) | TLS, key rotation, logging, backups |
| [`docs/PART11_COMPLIANCE.md`](docs/PART11_COMPLIANCE.md) | FDA 21 CFR Part 11 schema and compliance notes |
| [`docs/RUNNING_WITHOUT_DOCKER.md`](docs/RUNNING_WITHOUT_DOCKER.md) | Local setup without Docker |
| [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) | Full production deployment guide |
| [`tools/README.md`](tools/README.md) | CLI tools reference |

---

## License

See LICENSE file for details.
