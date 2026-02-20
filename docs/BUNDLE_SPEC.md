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

All fields below are present in `canonical_message.json` and covered by the ECDSA signature.
Source: `gateway/app/routes/clinical.py` (message construction) and `gateway/app/services/signer.py` (enhanced fields).

| Field | Source | Description |
|---|---|---|
| `certificate_id` | caller | Certificate identifier |
| `chain_hash` | server | This block's chain hash (incorporates `previous_hash`; prevents chain forgery) |
| `governance_policy_hash` | caller | SHA-256 of the governance policy version string |
| `governance_policy_version` | caller | Governance policy version label |
| `human_attested_at_utc` | server | Human attestation timestamp (null if not reviewed) |
| `human_reviewed` | caller | Human review flag |
| `human_reviewer_id_hash` | caller | SHA-256 of reviewer identifier (null if not reviewed) |
| `issued_at_utc` | server | Issuance timestamp (server clock; client cannot forge) |
| `key_id` | signer | Signing key identifier (added by `sign_generic_message`) |
| `model_name` | caller | AI model name (e.g. `gpt-4`) |
| `model_version` | caller | AI model version label |
| `nonce` | signer | UUID7 nonce for replay protection (added by `sign_generic_message`) |
| `note_hash` | server | SHA-256 of clinical note content |
| `prompt_version` | caller | Prompt template version label |
| `server_timestamp` | signer | Server-controlled timestamp added by `sign_generic_message` |
| `tenant_id` | server | Issuing tenant identifier |

### Fields NOT Signed

| Field | Reason |
|---|---|
| `patient_hash` | Present in `certificate.json` but **not** in `canonical_message.json`; not covered by signature |
| `previous_hash` | Stored in `integrity_chain` but **not** directly in canonical message; indirectly protected because `chain_hash` (which is signed) is computed from it |
| Plaintext note content | Never stored or transmitted; only the hash is kept |
| Raw patient identifiers | Never stored; only the caller-supplied hash is kept |
| `verification_report.json` | Generated at bundle-download time; reflects state at that moment |
| `public_key.pem` | The key is identified by `key_id` in the signed message |
| `README.txt` | Informational only; not part of the signed record |

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

### Signed (covered by ECDSA signature)

- Note content hash (`note_hash`)
- Model name and version (`model_name`, `model_version`)
- Governance policy hash and version (`governance_policy_hash`, `governance_policy_version`)
- Human review flag and reviewer hash (`human_reviewed`, `human_reviewer_id_hash`)
- Human attestation timestamp (`human_attested_at_utc`)
- Certificate ID and issuance timestamp (`certificate_id`, `issued_at_utc`)
- HALO chain hash (`chain_hash`)
- Tenant identifier (`tenant_id`)
- Signing key identifier (`key_id`)
- Prompt version (`prompt_version`)
- Replay-protection nonce and server timestamp (`nonce`, `server_timestamp`)

### NOT Signed

- `patient_hash` — present in `certificate.json` but not in the canonical message; not covered by the signature
- `previous_hash` — stored in `integrity_chain` but not directly in the canonical message; indirectly protected because `chain_hash` is computed from it
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
