# Defense Bundle Specification

Formal description of the CDIL defense bundle produced by
`GET /v1/certificates/{certificate_id}/defense-bundle`.

---

## Overview

A defense bundle is a ZIP archive that contains every artifact required to
independently verify an integrity certificate **without network access, without
API access, and without trusting any third party**.

The bundle is suitable for:

- Legal proceedings and expert witness testimony
- Payer appeals and compliance audits
- Offline archival and regulatory submissions

---

## Bundle Format

The bundle is returned as `application/zip` with the filename:
`defense-bundle-{certificate_id}.zip`

### ZIP Contents

| File | Role |
|---|---|
| `certificate.json` | Complete certificate — all provenance fields, no PHI |
| `canonical_message.json` | Exact JSON object that was signed |
| `verification_report.json` | Verification status captured at bundle generation time |
| `public_key.pem` | Signer's EC P-256 public key (PEM, SubjectPublicKeyInfo) |
| `README.txt` | Step-by-step offline verification instructions |

---

## Field-by-Field: `certificate.json`

### Top-Level Fields

| Field | Type | Notes |
|---|---|---|
| `certificate_id` | string (UUID7) | Unique, time-ordered identifier for this certificate |
| `tenant_id` | string | Issuing tenant; never a patient or user identifier |
| `issued_at_utc` | ISO 8601 string | Timestamp at moment of issuance (server clock) |
| `note_hash` | `sha256:<hex>` | SHA-256 of note text; plaintext is never stored |
| `patient_hash` | `sha256:<hex>` | SHA-256 of patient identifier; raw ID is never stored |
| `model_version` | string | Model label supplied by caller at issuance |
| `prompt_version` | string \| null | Prompt template version label, if provided |
| `governance_policy_version` | string \| null | Governance policy version label, if provided |
| `governance_policy_hash` | `sha256:<hex>` | Hash of the policy version string; included in signed message |
| `human_reviewed` | boolean | Whether a human reviewer attested to this note |
| `human_reviewer_id_hash` | `sha256:<hex>` \| null | Hash of reviewer identifier; raw ID never stored |
| `human_attested_at_utc` | ISO 8601 string \| null | Timestamp of human attestation, if present |
| `signature` | object | Cryptographic signature bundle — see below |
| `integrity_chain` | object | HALO chain linkage — see below |

### `signature` Sub-Object

| Field | Type | Notes |
|---|---|---|
| `algorithm` | string | Always `ECDSA_SHA_256` |
| `key_id` | string | References the signing key in `/v1/keys/{key_id}` |
| `signature` | string | Base64-encoded ASN.1 DER signature |
| `canonical_message` | object | The exact object that was signed (also exported as `canonical_message.json`) |

### `integrity_chain` Sub-Object

| Field | Type | Notes |
|---|---|---|
| `chain_hash` | `sha256:<hex>` | Hash of this certificate block (sha256 of canonical JSON of this block) |
| `previous_hash` | `sha256:<hex>` \| null | Hash of the preceding certificate; `null` for the first certificate in a tenant chain |

---

## Field-by-Field: `canonical_message.json`

This file is the exact object that was signed. It is also embedded as
`certificate.signature.canonical_message` in `certificate.json`.

### Canonicalization Rules (`json_c14n_v1`)

1. All keys are sorted alphabetically (Unicode code point order, recursive).
2. No whitespace between tokens.
3. UTF-8 encoding.
4. No BOM.

The SHA-256 of the canonical bytes is what the ECDSA signature covers.

### Signed Fields

> **The canonical message is the sole source of cryptographic truth.** Only fields present in `canonical_message.json` are covered by the ECDSA signature.
> Source: [`gateway/app/routes/clinical.py`](../gateway/app/routes/clinical.py) and [`gateway/app/services/signer.py`](../gateway/app/services/signer.py).

| Field | Description |
|---|---|
| `certificate_id` | Certificate identifier |
| `chain_hash` | This block's chain hash (prevents chain forgery; also indirectly protects `previous_hash`) |
| `governance_policy_hash` | Policy version hash (binds issuance to a policy snapshot) |
| `governance_policy_version` | Policy version label |
| `human_attested_at_utc` | Human attestation timestamp (null if not reviewed) |
| `human_reviewed` | Human review flag |
| `human_reviewer_id_hash` | Reviewer identity hash (null if not reviewed) |
| `issued_at_utc` | Issuance timestamp |
| `key_id` | Signing key identifier (added by signer at signing time) |
| `model_name` | AI model name |
| `model_version` | Model label |
| `nonce` | UUID7 replay-protection token (added by signer at signing time) |
| `note_hash` | Hash of the clinical note content |
| `prompt_version` | Prompt template version label |
| `server_timestamp` | Server-controlled timestamp (added by signer at signing time) |
| `tenant_id` | Issuing tenant identifier |

### Indirectly Protected Fields

These fields are **not signed directly**, but tampering with them would break a signed value:

| Field | Protection Mechanism |
|---|---|
| `previous_hash` | Not in the canonical message, but included in computing `chain_hash` (which IS signed). Altering `previous_hash` changes `chain_hash`, which breaks the ECDSA signature. |

### Fields NOT Signed

| Field | Reason |
|---|---|
| `patient_hash` | Not included in `canonical_message.json`; see the note below |
| Plaintext note content | Never stored or transmitted; only the hash is kept |
| Raw patient identifiers | Never stored; only the caller-supplied hash is kept |
| Tenant secrets or keys | Keys are referenced by ID only |
| `verification_report.json` | Generated at bundle-download time; reflects state at that moment |
| `public_key.pem` | The key is identified by `key_id` in the signed message |
| `README.txt` | Bundle metadata only |

> **Important — `patient_hash` scope:** `patient_hash` is stored in `certificate.json` as a chain-of-custody reference but is **not** included in the ECDSA-signed canonical message. A post-issuance modification of `patient_hash` would not invalidate the signature. Relying parties that require cryptographic binding of patient identity to the certificate must include `patient_hash` in their own attestation layer or require it to be added to the canonical message.

---

## Field-by-Field: `verification_report.json`

Snapshot of the verification result captured at bundle-download time.

| Field | Type | Notes |
|---|---|---|
| `valid` | boolean | `true` if all checks passed |
| `status` | string | `PASS` or `FAIL` |
| `summary` | string | Human-readable summary |
| `checks` | object | Per-check results (`chain_hash`, `signature`, `key`) |
| `failures` | array | List of failure objects (empty on PASS) |
| `human_friendly_report` | object | Plain-language explanation for non-technical audiences |

---

## Cryptographic Parameters

| Parameter | Value |
|---|---|
| Signature algorithm | ECDSA_SHA_256 |
| Elliptic curve | P-256 (secp256r1 / prime256v1) |
| Signature encoding | ASN.1 DER, Base64 (standard) |
| Hash function | SHA-256 |
| Canonicalization spec | `json_c14n_v1` (sorted keys, no whitespace, UTF-8) |
| HALO chain version | v1 |
| Key format (public) | PEM SubjectPublicKeyInfo (`public_key.pem`) and JWK (`/v1/keys/{key_id}`) |

---

## What Is Signed vs. What Is NOT Signed

> **The canonical message is the sole source of cryptographic truth.** Only fields present in `canonical_message.json` are covered by the ECDSA signature; everything else is bundle metadata or certificate context.

See the complete, authoritative breakdown in the [canonical_message.json field tables](#signed-fields) above. In summary:

### Signed (covered by ECDSA signature)

All 16 fields in `canonical_message.json`: `certificate_id`, `chain_hash`, `governance_policy_hash`, `governance_policy_version`, `human_attested_at_utc`, `human_reviewed`, `human_reviewer_id_hash`, `issued_at_utc`, `key_id`, `model_name`, `model_version`, `nonce`, `note_hash`, `prompt_version`, `server_timestamp`, `tenant_id`.

### Indirectly Protected

- `previous_hash` — not in the canonical message, but included in computing `chain_hash` (which IS signed). See [Indirectly Protected Fields](#indirectly-protected-fields).

### NOT Signed

- `patient_hash` (not in `canonical_message.json` — see [Fields NOT Signed](#fields-not-signed) and the scope note)
- The verification report (generated at bundle-download time, not at issuance)
- The public key PEM (the key is identified by `key_id` in the signed message)
- The `README.txt` in the bundle
- Any field not listed in `canonical_message.json`

---

## What the Bundle Proves

### Truth Table

| Claim | Proven | Not Proven |
|---|---|---|
| Note content has not changed since certification | ✓ | |
| HALO chain integrity (no insertion or reordering) | ✓ | |
| Signature authenticity (key matches certificate) | ✓ | |
| Governance policy hash binding | ✓ | |
| Human review flag was recorded at issuance | ✓ | |
| Offline verification is possible (no network) | ✓ | |
| Real-world identity of `human_reviewer_id_hash` | | ✓ |
| Real-world identity of `patient_hash` caller | | ✓ |
| The specific AI model actually executed this note | | ✓ (`model_version` is a label, not execution proof) |
| Clinical accuracy or appropriateness of the note | | ✓ |
| HIPAA compliance certification | | ✓ (component only; requires full program review) |
| Trusted third-party time anchor (TSA) | | ✓ (TSA integration is on the roadmap; see [`docs/TSA.md`](../docs/TSA.md)) |

---

## Offline Verification

```bash
python tools/verify_bundle.py bundle.zip
```

### Checks Performed (4/4)

| Check | What It Verifies |
|---|---|
| Canonical hash | `canonical_message.json` re-hashed from scratch — must match certificate |
| ECDSA signature | `public_key.pem` verifies signature over canonical bytes |
| Chain integrity | `chain_hash` and `previous_hash` linkage present and consistent |
| Human attestation | `human_reviewed`, `human_reviewer_id_hash`, `human_attested_at_utc` present in signed fields |

### Exit Codes

| Code | Meaning |
|---|---|
| `0` | PASS — certificate valid and unmodified |
| `1` | FAIL — tampering detected or verification failed |
| `2` | ERROR — invalid bundle or technical error |

---

## Manual Verification Steps (OpenSSL)

```bash
# 1. Extract canonical bytes (sorted keys, no whitespace)
python -c "import json,sys; d=json.load(open('canonical_message.json')); print(json.dumps(d,sort_keys=True,separators=(',',':')),end='')" > message.bin

# 2. Decode the base64 DER signature from certificate.json
python -c "import json,base64; c=json.load(open('certificate.json')); sig=c['signature']['signature']; open('sig.der','wb').write(base64.b64decode(sig))"

# 3. Verify with OpenSSL
openssl dgst -sha256 -verify public_key.pem -signature sig.der message.bin
# Outputs: Verified OK  (or Verification Failure)
```

---

## Source References

| Component | Source |
|---|---|
| Defense bundle generation | `gateway/app/services/evidence_bundle.py` — `generate_defense_bundle()` |
| Canonicalization | `gateway/app/services/c14n.py` |
| ECDSA signing | `gateway/app/services/signer.py` |
| HALO chain construction | `gateway/app/services/halo.py` |
| Offline verifier CLI | `tools/verify_bundle.py` |
| Download endpoint | `GET /v1/certificates/{certificate_id}/defense-bundle` |
