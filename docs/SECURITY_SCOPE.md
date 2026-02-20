# CDIL Security Scope — Truth Table & Threat Model

This document states in plain language what CDIL cryptographically proves, what it does not prove, and the threat model it is designed to address.

---

## Truth Table

### What CDIL Proves

| Claim | Mechanism | Where to verify |
|---|---|---|
| **Note content has not changed since certification** | SHA-256 hash of note text is embedded in the signed canonical message | `canonical_message.json` → `note_hash` |
| **Certificate has not been tampered with** | ECDSA P-256 signature over the canonical message; any field change invalidates the signature | `python tools/verify_bundle.py bundle.zip` |
| **Certificate belongs to its chain (no insertion)** | Each certificate's `chain_hash` includes the previous certificate's hash; gaps or reordering break the chain | `certificate.json` → `integrity_chain` |
| **Governance policy version was recorded at issuance** | `governance_policy_hash` and `governance_policy_version` are part of the signed canonical message | `canonical_message.json` → `governance_policy_hash` |
| **Human review flag was set at issuance (not retroactively)** | `human_reviewed`, `human_reviewer_id_hash`, and `human_attested_at_utc` are all part of the signed canonical message | `canonical_message.json` → `human_reviewed` |
| **Offline verification is possible without trusting CDIL** | The defense bundle contains the public key; verification requires only `cryptography` (standard Python lib) | [`tools/verify_bundle.py`](../tools/verify_bundle.py) |
| **Note text was not stored in plaintext by default** | By default, only the SHA-256 hash is persisted; plaintext requires explicit `STORE_NOTE_TEXT=true` | [`gateway/app/routes/clinical.py`](../gateway/app/routes/clinical.py) |

### What CDIL Does NOT Prove

| Claim | Why not | Notes |
|---|---|---|
| **Identity of the human reviewer** | Only a SHA-256 hash of the reviewer's ID is stored; the mapping from hash to identity is not held by CDIL | The reviewer ID hash is signed, so it cannot be retroactively changed |
| **That the specific AI model actually executed** | `model_version` is a string label provided by the caller; CDIL does not have a channel to the model's execution environment | This would require cryptographic attestation from the model provider (Phase 2/3 roadmap) |
| **Clinical accuracy or appropriateness of the note** | CDIL is an integrity layer, not a clinical quality system | Use clinical documentation improvement (CDI) tooling for quality |
| **HIPAA compliance certification** | CDIL is a technical component; HIPAA compliance requires a full organizational program, BAA, risk analysis, and more | CDIL supports PHI-safe design patterns but cannot certify compliance |
| **Trusted third-party timestamp (TSA)** | TSA integration is not yet implemented | Planned: RFC 3161 support. See [`docs/TSA.md`](TSA.md) |
| **That the note was not altered before being submitted to CDIL** | CDIL signs what it receives; pre-submission alteration is outside CDIL's trust boundary | The signing window should be as close to note finalization as possible |

---

## What Is Hashed / Signed / Timestamped

### Hashed (SHA-256)

| Data | Stored as | Notes |
|---|---|---|
| Note text content | `note_hash` | Only the hash is stored by default |
| Patient identifier | `patient_hash` | Caller-provided hash; CDIL never sees raw patient ID |
| Reviewer identifier | `human_reviewer_id_hash` | Hash of the reviewer's ID token/username |
| Governance policy document | `governance_policy_hash` | Hash of the policy document at time of issuance |

### Signed (ECDSA P-256 / SHA-256, ASN.1 DER)

The canonical message — the exact byte sequence that is signed — includes:

```
certificate_id, chain_hash, governance_policy_hash, governance_policy_version,
human_attested_at_utc, human_reviewed, human_reviewer_id_hash, issued_at_utc,
key_id, model_name, model_version, note_hash, nonce, prompt_version,
server_timestamp, tenant_id
```

Canonicalization: sorted keys, no whitespace, UTF-8 (`json_c14n_v1`).
Source: [`gateway/app/services/c14n.py`](../gateway/app/services/c14n.py)

### Chain-Linked (Hash Ledger)

Each certificate includes:
- `chain_hash`: SHA-256 hash of the current certificate's core fields plus `previous_hash`
- `previous_hash`: Hash of the previous certificate in the tenant's chain

This prevents insertion (adding a certificate between two existing ones) and reordering.

### Not Yet Timestamped by Third Party

Server-side `issued_at_utc` and `server_timestamp` are set at issuance using the server clock. RFC 3161 TSA stamping (independent third-party time anchor) is on the roadmap. See [`docs/TSA.md`](TSA.md).

---

## Threat Model

### Assets Protected

1. **Note integrity** — proof that note content has not changed since certification
2. **Audit trail authenticity** — proof that the chain of certificates has not been modified
3. **Governance provenance** — proof that the stated policy version was in effect at issuance
4. **Human attestation record** — proof that the human review flag was set at issuance

### Attacker Model

| Attacker | Capability | CDIL Defends Against? |
|---|---|---|
| External attacker with bundle copy | Modifies `certificate.json` or `canonical_message.json` | Yes — ECDSA signature will fail |
| External attacker with bundle copy | Substitutes a different public key | Yes — the certificate embeds `key_id`; verifier checks chain |
| Insider with DB write access | Modifies stored certificate | Yes — stored signature will fail verification |
| Insider with DB write access | Inserts a certificate into the chain | Yes — `chain_hash` and `previous_hash` chain breaks |
| Insider with DB write access | Modifies audit events | Yes — audit ledger is hash-chained; any modification breaks the chain |
| Caller (API client) | Submits falsified `model_version` string | No — CDIL signs what it receives; model execution is not verified |
| Caller (API client) | Submits falsified `patient_hash` | No — the hash is signed, but the mapping from hash to identity is not verified by CDIL |
| Adversary with access to private key | Forges a certificate | No defense once private key is compromised; key rotation mitigates |
| Network attacker | Replay attack | Mitigated — each certificate uses a UUID7 nonce, recorded in the DB |

### Out of Scope

- Pre-submission alteration of note text before it reaches the API
- Compromise of the signing key (mitigate via key rotation and HSM)
- Regulatory compliance certification (HIPAA, SOC 2, etc.)
- Clinical quality or accuracy of AI-generated notes

---

## PHI Handling

- Note text is **hashed before storage** using SHA-256
- Patient identifiers are **hashed by the caller** before submission; CDIL never receives raw patient IDs
- Reviewer IDs are **hashed before storage**
- API responses never include note text (only hash values)
- Validation errors return sanitized messages (no request body echoed)
- TSA (when implemented): only the SHA-256 digest of the canonical message will be sent to the TSA — no PHI, no note text

---

See also:
- [`docs/TSA.md`](TSA.md) — TSA design and what is verified offline
- [`docs/DEPLOYMENT_HARDENING.md`](DEPLOYMENT_HARDENING.md) — Production security hardening
- [`docs/PART11_COMPLIANCE.md`](PART11_COMPLIANCE.md) — FDA 21 CFR Part 11 schema
