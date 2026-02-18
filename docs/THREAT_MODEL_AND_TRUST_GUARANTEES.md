# Threat Model and Trust Guarantees

## Document Version
- **Version**: 2.0 (Security Hardened)
- **Date**: 2026-02-18
- **Status**: Production-Ready Architecture

## Executive Summary

CDIL (Clinical Documentation Integrity Layer) provides cryptographic integrity guarantees for AI-generated clinical documentation. This document defines the security boundaries, trust model, threat landscape, and explicit guarantees that CDIL provides.

**Critical Change**: Version 2.0 introduces identity binding, per-tenant key isolation, and replay protection - fundamentally changing the trust model from "cryptographic integrity only" to "authenticated, tenant-isolated, non-repudiable integrity."

---

## 1. Security Architecture Overview

### 1.1 Core Security Principles

1. **Identity Binding**: All operations require JWT authentication. Tenant context derived from cryptographically verified identity.
2. **Cryptographic Boundary = Tenant Boundary**: Each tenant has isolated cryptographic keys. Cross-tenant forgery is cryptographically impossible.
3. **Client Authority = Zero**: Clients cannot control tenant_id, timestamps, nonces, or key selection.
4. **Replay Protection**: Each signature includes a nonce that can only be used once per tenant.
5. **PHI Discipline**: Only hashes stored. Logs sanitized. Exceptions scrubbed.

### 1.2 Trust Boundaries

```
┌─────────────────────────────────────────────────────┐
│ TRUSTED ZONE (CDIL Server)                          │
│                                                      │
│  ┌──────────────┐         ┌──────────────┐          │
│  │ JWT Validator│◄────────│ Identity     │          │
│  │ (RS256/HS256)│         │ Provider     │          │
│  └──────────────┘         └──────────────┘          │
│         │                                            │
│         ▼                                            │
│  ┌──────────────┐         ┌──────────────┐          │
│  │ Key Registry │◄────────│ Per-Tenant   │          │
│  │ (Tenant Keys)│         │ Keys (DB)    │          │
│  └──────────────┘         └──────────────┘          │
│         │                                            │
│         ▼                                            │
│  ┌──────────────┐         ┌──────────────┐          │
│  │ Nonce        │────────►│ Certificate  │          │
│  │ Tracker      │         │ Signer       │          │
│  └──────────────┘         └──────────────┘          │
│                                                      │
└─────────────────────────────────────────────────────┘
                    │
                    │ HTTPS/TLS
                    ▼
┌─────────────────────────────────────────────────────┐
│ UNTRUSTED ZONE (Clients)                            │
│                                                      │
│  • Cannot forge JWT                                 │
│  • Cannot choose tenant_id                          │
│  • Cannot replay signatures                         │
│  • Cannot access other tenant's certificates        │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## 2. Identity Binding Model

### 2.1 Authentication Flow

**Before**: Client supplies X-Tenant-Id header (forgeable).  
**After**: Server extracts tenant_id from validated JWT (non-forgeable).

```
1. Client obtains JWT from identity provider (e.g., Auth0, Cognito)
   JWT contains: {sub, tenant_id, role, exp}

2. Client includes JWT in Authorization: Bearer <token>

3. CDIL validates:
   - Signature (cryptographic verification)
   - Expiration (prevents stale tokens)
   - Required claims (sub, tenant_id, role)
   - Role authorization (clinician/auditor/admin)

4. Server uses tenant_id from JWT for all operations
```

### 2.2 Role-Based Access Control

| Role       | Can Issue Certificates | Can Verify | Can Query Audit Logs | Can Rotate Keys |
|------------|------------------------|------------|----------------------|-----------------|
| clinician  | ✅                     | ❌          | ❌                    | ❌               |
| auditor    | ❌                     | ✅          | ✅                    | ❌               |
| admin      | ✅                     | ✅          | ✅                    | ✅               |

---

## 3. Per-Tenant Key Isolation

### 3.1 Key Architecture

**Problem (V1.0)**: Single global key pair. If compromised, attacker can forge certificates for ALL tenants.

**Solution (V2.0)**: Each tenant has isolated key pairs.

```
Tenant A:
  - key-uuid7-aaa (active)
  - key-uuid7-bbb (rotated, still verifiable)

Tenant B:
  - key-uuid7-ccc (active)
  - key-uuid7-ddd (rotated, still verifiable)
```

**Cryptographic Guarantee**: Even if Tenant A's key is compromised, Tenant B's certificates remain unforgeable.

### 3.2 Key Rotation Policy

- Keys can be rotated at any time without invalidating existing certificates
- Old certificates remain verifiable using their embedded `key_id`
- New certificates signed with new `key_id`
- Rotated keys marked as "rotated" but retained for verification

**Rotation Trigger Events**:
1. Periodic rotation (e.g., every 90 days)
2. Suspected compromise
3. Employee departure
4. Compliance requirement

---

## 4. Replay Protection

### 4.1 Mechanism

Every signed payload includes:
- `nonce`: UUID7 (time-ordered, globally unique)
- `server_timestamp`: UTC ISO 8601
- All original certificate fields

**Database Tracking**:
```sql
CREATE TABLE used_nonces (
    tenant_id TEXT NOT NULL,
    nonce TEXT NOT NULL,
    used_at_utc TEXT NOT NULL,
    PRIMARY KEY (tenant_id, nonce)
);
```

**Attack Prevention**:
1. Client submits certificate issuance request
2. Server generates nonce (UUID7)
3. Server adds nonce + timestamp to payload
4. Server signs payload
5. Server records nonce in database (atomic)
6. If same nonce appears again → REJECT (replay attack detected)

### 4.2 Nonce Cleanup

Nonces older than 30 days can be purged (configurable). Replay attacks using very old signatures are detectable via timestamp validation.

---

## 5. Threat Landscape

### 5.1 Threats Mitigated (NEW in V2.0)

| Threat                           | Mitigation                                      | Severity Reduced |
|----------------------------------|-------------------------------------------------|------------------|
| Cross-tenant forgery             | Per-tenant keys                                 | Critical → None  |
| Client-controlled tenant context | JWT-derived tenant_id                           | Critical → None  |
| Replay attacks                   | Nonce tracking                                  | High → None      |
| Timestamp manipulation           | Server-controlled timestamps                    | Medium → None    |
| Role escalation                  | JWT-based RBAC                                  | High → Low       |
| Key compromise blast radius      | Tenant isolation limits impact                  | Critical → High  |
| PHI leakage via errors           | Sanitized exception handling                    | Medium → Low     |

### 5.2 Residual Threats

| Threat                           | Status                                          | Mitigation Strategy         |
|----------------------------------|-------------------------------------------------|-----------------------------|
| JWT secret compromise            | Residual Risk (High if HS256)                   | Use RS256, rotate secrets   |
| Database exfiltration            | Residual Risk (Medium)                          | Encrypt DB, audit access    |
| Server compromise                | Residual Risk (Critical)                        | HSM/KMS, audit logging      |
| Side-channel attacks             | Residual Risk (Low)                             | Timing-safe comparisons     |
| DoS via rate limiting bypass     | Residual Risk (Medium)                          | WAF, DDoS protection        |

---

## 6. Explicit Security Guarantees

### What CDIL DOES Guarantee

✅ **Integrity**: If a certificate verifies successfully, its content has not been tampered with since issuance.

✅ **Non-repudiation**: A valid certificate can only have been issued by CDIL (assuming key security).

✅ **Tenant Isolation**: Tenant A cannot forge, access, or verify Tenant B's certificates.

✅ **Replay Prevention**: A signature cannot be reused (nonce enforcement).

✅ **Timestamp Integrity**: Timestamps are server-controlled, not client-supplied.

✅ **Role Enforcement**: Only authorized roles can perform specific operations.

✅ **PHI Protection**: Plaintext PHI is never stored; only hashes persisted.

### What CDIL DOES NOT Guarantee

❌ **Clinical Correctness**: CDIL does not validate the medical accuracy of AI-generated notes.

❌ **EHR Integration**: CDIL does not enforce that certificates are recorded in the EHR.

❌ **Model Trustworthiness**: CDIL does not audit or certify the AI model itself.

❌ **Human Review Quality**: CDIL records whether review occurred, not its thoroughness.

❌ **Regulatory Compliance**: CDIL provides tools for compliance but does not ensure it.

❌ **Key Security**: CDIL assumes keys are stored securely (HSM/KMS recommended).

---

## 7. Attack Scenarios (Security Test Cases)

### 7.1 Tenant Impersonation Attack

**Scenario**: Attacker modifies JWT to change tenant_id from "tenant-a" to "tenant-b".

**Expected Behavior**:
- JWT signature validation FAILS
- Request rejected with 401 Unauthorized
- No certificate issued

**Test**: `test_adversarial_security.py::test_tenant_impersonation_via_jwt`

### 7.2 Replay Attack

**Scenario**: Attacker captures a valid signature and resubmits it.

**Expected Behavior**:
- Nonce already exists in database
- Signing fails with "Nonce already used"
- No duplicate certificate issued

**Test**: `test_adversarial_security.py::test_replay_attack`

### 7.3 Signature Tampering

**Scenario**: Attacker modifies a certificate's content after issuance.

**Expected Behavior**:
- Signature verification FAILS
- Certificate marked as invalid
- Failures include "invalid_signature"

**Test**: `test_adversarial_security.py::test_signature_tampering`

### 7.4 Key Rotation Compatibility

**Scenario**: Certificate signed with old key, new key rotated, verification attempted.

**Expected Behavior**:
- Old key retrieved via key_id
- Signature verification SUCCEEDS
- Certificate remains valid

**Test**: `test_adversarial_security.py::test_key_rotation_backward_compatibility`

### 7.5 Canonicalization Attack

**Scenario**: Attacker reorders JSON fields to create same content hash but different signature.

**Expected Behavior**:
- Canonicalization (C14N) ensures deterministic serialization
- Reordered payload produces same signature
- Attack ineffective

**Test**: `test_c14n_vectors.py` (existing)

---

## 8. Operational Security

### 8.1 Key Management

**Development**:
- Keys stored in SQLite database
- Auto-generated per tenant on first use

**Production**:
- Keys should be stored in AWS KMS, GCP KMS, or Azure Key Vault
- CDIL KeyRegistry provides abstraction layer
- Private keys never leave HSM

### 8.2 JWT Configuration

**HS256 (Symmetric)**:
- ✅ Simple, fast
- ❌ Secret must be shared
- ❌ Single point of compromise
- **Recommendation**: Development only

**RS256 (Asymmetric)**:
- ✅ Public key distribution safe
- ✅ Identity provider controls keys
- ✅ Key rotation easier
- **Recommendation**: Production

### 8.3 Rate Limiting

**Current Limits**:
- Certificate issuance: 30 requests/minute per IP
- Verification: 100 requests/minute per IP
- PDF/Bundle generation: 100 requests/minute per IP
- Query: 100 requests/minute per IP

**Production**: Use identity-based limiting instead of IP-based.

### 8.4 Audit Logging

**Current**: Basic stdout logging (development).

**Production**: Structured logging with:
- Request ID
- User ID (from JWT)
- Tenant ID
- Operation type
- Timestamp
- Result (success/failure)
- NO PHI (sanitized)

---

## 9. Compliance Mapping

| Requirement                     | CDIL Implementation                            |
|---------------------------------|------------------------------------------------|
| 21 CFR Part 11 (e-signatures)   | ECDSA P-256 signatures, non-repudiation        |
| HIPAA Security Rule             | PHI hashing, access controls, audit logs       |
| GDPR Article 32 (security)      | Encryption, pseudonymization (hashing)         |
| ISO 27001 (access control)      | JWT RBAC, tenant isolation                     |
| SOC 2 (logical access)          | Identity binding, rate limiting                |

---

## 10. Future Enhancements

**Phase 11**: HSM/KMS Integration
- Replace database key storage with KMS
- Hardware-backed key generation
- Audit trail for key usage

**Phase 12**: Advanced Audit Logging
- Structured JSON logs
- Centralized log aggregation
- Real-time anomaly detection

**Phase 13**: Multi-Factor Authentication
- Support for MFA-issued JWTs
- Step-up auth for key rotation

**Phase 14**: Zero-Knowledge Proofs
- Prove governance compliance without revealing note content
- zkSNARKs for chain integrity

---

## 11. References

- [ECDSA Signature Standard (FIPS 186-4)](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.186-4.pdf)
- [JWT Specification (RFC 7519)](https://datatracker.ietf.org/doc/html/rfc7519)
- [HIPAA Security Rule](https://www.hhs.gov/hipaa/for-professionals/security/index.html)
- [21 CFR Part 11 (FDA)](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/part-11-electronic-records-electronic-signatures-scope-and-application)

---

## Document Control

- **Author**: CDIL Security Team
- **Reviewer**: [Pending]
- **Approval**: [Pending]
- **Next Review**: 2026-05-18 (90 days)
# CDIL Threat Model & Trust Guarantees (v1.0)

## 0. Purpose

This document defines the **security contract** for CDIL (Clinical Document Integrity Layer): what it **guarantees**, what it **explicitly does not guarantee**, and the **threat model** used to evaluate design and implementation.

CDIL is an integrity system, not a truth system. It exists to make tampering **detectable**, not to prove clinical correctness.

---

## 1. Scope

### In scope

* Issuance of integrity artifacts (receipts/certificates) for generated clinical notes.
* Cryptographic signing and verification logic.
* Tenant isolation and key boundaries.
* Storage and retrieval of integrity artifacts.
* Server-side logging and telemetry controls ("Zero-PHI" discipline).
* Operational controls: migrations, key rotation, incident response.

### Out of scope

* Clinical accuracy, medical appropriateness, billing correctness.
* Identity proofing of the clinician beyond the platform's auth.
* EHR authorization decisions (unless explicitly integrated).
* Endpoint security of client devices or clinician workstations.

---

## 2. System invariants ("Machine Phase" rules)

### Zero-PHI

CDIL services must not ingest, persist, or log PHI or raw clinical note text. Allowed inputs are:

* `note_hash` (cryptographic hash of note text computed client-side or in the non-PHI boundary)
* Non-PHI metadata required for integrity chain (timestamps, tenant ID, model/version IDs, policy IDs)
* Optional: salted/derived identifiers that are provably non-reversible (must be documented)

**Current implementation:** Note text is accepted but immediately hashed (SHA-256) before storage. PHI pattern detection rejects SSN, phone numbers, and email addresses.

### Server-side sovereignty

All signing operations occur **server-side**; clients never receive signing private keys.

**Current implementation:** Private keys stored in `gateway/app/dev_keys/dev_private.pem`, loaded server-side only.

### Tenant isolation

A tenant's cryptographic materials and integrity namespace must be isolated such that compromise of one tenant cannot be used to forge artifacts for another tenant.

**Current implementation status:** ⚠️ **PARTIAL** - See Section 14 (Security Gaps).

---

## 3. Current Architecture (Reality Check)

### Runtime Stack

* **Framework:** FastAPI 0.109.0+
* **Database:** SQLite (local file: `gateway/app/db/eli_sentinel.db`)
* **Cryptography:** Python `cryptography` library (ECDSA P-256, SHA-256)
* **Deployment:** Single server (MVP/development configuration)
* **No queue, no Redis, no external KMS** (current MVP state)

### Tenant Model

**What is a tenant?** A tenant is a hospital organization, healthcare facility, or customer account using CDIL for integrity certification.

**Tenant identifier:** `tenant_id` (string field, e.g., `"hospital-alpha"`, `"clinic-beta"`)

**Tenant boundaries:**
* Each tenant has an independent integrity chain (per-tenant chain head)
* Certificates stored with `tenant_id` index
* Retrieval/verification requires `X-Tenant-Id` header
* **Issuance accepts `tenant_id` from request body** (not derived from auth)

### Signing Key Model (Current State)

**Key location:** Filesystem - `gateway/app/dev_keys/dev_private.pem`

**Key scope:** ⚠️ **GLOBAL** - Single key (`dev-key-01`) signs certificates for ALL tenants

**Intended design (per problem statement):** Per-tenant keys with tenant→key mapping

**Security implication:** A compromised tenant's auth can sign certificates as ANY tenant, because:
1. `tenant_id` is client-supplied in request body
2. Signer uses the same global key regardless of `tenant_id`
3. No server-side tenant→key mapping enforcement

---

## 4. Data Flow

### Certificate Issuance Flow

```
Client → POST /v1/clinical/documentation
  ↓
  Request body: {tenant_id, note_text, model_version, ...}
  ↓
  Server: Validate PHI patterns (reject SSN/phone/email)
  ↓
  Server: Hash note_text → note_hash (SHA-256)
  ↓
  Server: Hash patient_reference → patient_hash
  ↓
  Server: Get tenant chain head (previous_hash)
  ↓
  Server: Compute chain_hash (links to previous cert)
  ↓
  Server: Sign canonical_message with dev-key-01 (GLOBAL KEY)
  ↓
  Server: Store certificate in DB with tenant_id
  ↓
  Response: {certificate_id, certificate, verify_url}
```

### Zero-PHI Confirmation

**Server never receives in plaintext:**
* ❌ False - `note_text` IS sent to server, but:
  * Hashed immediately upon receipt
  * Never persisted (only `note_hash` stored)
  * PHI pattern detection rejects obvious patterns
  * Not logged (should be verified with logging tests)

**Server stores only:**
* ✅ `note_hash` (SHA-256)
* ✅ `patient_hash` (SHA-256 of patient_reference, if provided)
* ✅ `reviewer_hash` (SHA-256 of human_reviewer_id, if provided)
* ✅ Non-PHI metadata: timestamps, model versions, policy versions

**Exceptions:** None documented. No debug mode, support tooling exemptions.

---

## 5. Assets (what we protect)

1. **Signing private keys** (highest sensitivity)
   * Current location: `gateway/app/dev_keys/dev_private.pem`
   * Current access control: Filesystem permissions only
   * Future: KMS, HSM, per-tenant key isolation

2. **Integrity artifacts** (receipts/certificates)
   * Stored in `certificates` table
   * Indexed by `tenant_id` for isolation
   * Contains no plaintext PHI (only hashes)

3. **Tenant boundary controls** (tenant_id enforcement, authz)
   * GET/verify endpoints require `X-Tenant-Id` header
   * Issuance endpoint accepts `tenant_id` from body
   * ⚠️ Gap: No authentication/authorization layer yet

4. **Audit logs** (must be non-PHI but still tamper-evident/forensically useful)
   * Current status: Not implemented
   * Required: Structured logging with allowlist, no PHI keys

5. **Database integrity chain state** (migrations must not break verifiability)
   * Schema: `gateway/app/db/schema.sql`
   * Migration: `ensure_schema()` idempotent setup

---

## 6. Trust boundaries

### Boundary A: Client / Note Generation Boundary

* Where `note_text` exists.
* `note_hash` computed by server upon receipt (not client-side in current impl).
* Algorithm: SHA-256 over UTF-8 encoded text.
* This boundary is assumed to contain PHI.

### Boundary B: CDIL Gateway/API

* Receives `note_text` + metadata.
* ⚠️ Currently accepts `tenant_id` from request body (should derive from auth).
* Enforces PHI pattern detection (basic regex for SSN/phone/email).
* Hashes note text immediately.
* Calls signer service with certificate data.

### Boundary C: Signer Service

* Holds access to private keys (`signer.py` loads `dev_private.pem`).
* ⚠️ **Currently does NOT enforce tenant-scoped key selection.**
* Signs with global `dev-key-01` regardless of `tenant_id`.
* **Target state:** Must enforce tenant→key mapping, refuse to sign if mismatch.

### Boundary D: Persistence Layer

* Stores certificates/receipts in SQLite.
* ✅ Enforces tenant row-level isolation via `WHERE tenant_id = ?` queries.
* ✅ Supports schema migrations via `ensure_schema()`.
* Historical verification supported (payload stored in `certificate_json`).

### Boundary E: Observability/Logging

* ⚠️ Not implemented.
* **Required:** Provably non-PHI logging with automated controls.
* Must include allowlist-based structured logging.
* Must fail CI if forbidden keys (`note_text`, `patient_id`) appear in logs.

---

## 7. Security guarantees (what CDIL promises)

### G1 — Tamper detection (integrity)

Any modification to `note_hash` or signed payload fields after issuance results in verification failure with probability ~1 (cryptographic assumption).

**Implementation:** ECDSA P-256 signature over canonical JSON (canonicalized via `json_c14n_v1`).

### G2 — Non-repudiation within the system boundary

Given control of private keys, CDIL can prove that a certificate was issued by the CDIL signing service using a specific key and key version.

**Current limitation:** Single global key means all certificates signed by same key, no tenant-specific attribution.

### G3 — Tenant cryptographic isolation (target guarantee)

**Target:** A valid integrity artifact for tenant **T1** cannot be forged using a compromised key from tenant **T2**, because:
* signing keys are unique per tenant (and ideally per key-version), and
* signer enforces strict tenant→key mapping.

**Current status:** ⚠️ **NOT ACHIEVED** - Global key used for all tenants. See Section 14 (Security Gaps).

### G4 — Chain continuity

If CDIL uses an integrity chain (hash chaining receipts), then:
* Removing, reordering, or altering an issued link breaks chain verification.

**Implementation:** ✅ Per-tenant chain with `previous_hash` linkage. Chain hash recomputed during verification.

### G5 — Zero-PHI discipline (negative guarantee)

CDIL will not store or emit PHI, assuming upstream components adhere to the contract.

**Implementation:**
* ✅ No plaintext `note_text` persisted (only `note_hash`)
* ✅ No plaintext patient/reviewer IDs (only hashes)
* ✅ PHI pattern detection rejects obvious patterns
* ⚠️ Logging discipline not enforced (no automated tests)

---

## 8. Non-guarantees (explicit exclusions)

* CDIL does **not** validate clinical correctness, completeness, or appropriateness.
* CDIL does **not** prove the note was authored by a particular clinician absent separate identity controls.
* CDIL does **not** prevent an authorized user from generating a malicious note; it only preserves detectability of modifications **after issuance**.
* CDIL does **not** protect against compromise of client devices where PHI and `note_text` live.
* CDIL does **not** guarantee availability (DoS resistance) beyond deployed infrastructure controls.
* CDIL does **not** currently enforce authentication/authorization (MVP relies on trust of client-supplied `tenant_id`).

---

## 9. Attacker model

### A. External attacker (no credentials)

* Tries to forge certificates, exploit endpoints, or cause denial of service.
* **Mitigation:** Cryptographic signatures prevent forgery (public key verification).
* **Gap:** No rate limiting, no authentication required for issuance.

### B. Malicious tenant user (valid tenant credentials)

* Attempts to forge artifacts, tamper with chain history, or exfiltrate other tenant data.
* **Mitigation:** Tenant isolation in DB queries (X-Tenant-Id header enforcement).
* **Gap:** ⚠️ Can sign certificates as OTHER tenants by supplying different `tenant_id` in body.

### C. Compromised tenant key scenario

* Tenant key leaked (worst case).
* Primary question: does that enable cross-tenant forgery?
* **Current answer:** ⚠️ YES - because all tenants share the same global key.

### D. Insider / Operator risk

* Misconfiguration, log leakage, accidental exposure.
* "Break-glass" operational access.
* **Mitigation:** Access to private key requires filesystem access to server.
* **Gap:** No KMS, no audit logging, no break-glass controls.

---

## 10. Threat analysis (STRIDE) and mitigations

### S — Spoofing

**Threat:** attacker submits requests as another tenant.

**Current mitigations:**
* ⚠️ **NONE** - `tenant_id` accepted from request body, not derived from auth.

**Required mitigations:**
* AuthN ties session token to `tenant_id`.
* Server ignores client-supplied `tenant_id`; derives from auth context.
* All DB queries filtered by authenticated `tenant_id`.
* Centralized enforcement with integration tests.

### T — Tampering

**Threat:** modify stored receipts/certificates or chain state.

**Mitigations:**
* ✅ Sign canonical payload; verify on read.
* ✅ Chain hash links certificates (prevents insertion/reordering).
* ⚠️ No database-level immutability constraints.

**Additional recommendations:**
* Append-only receipts table.
* Database-level immutability constraints for issued artifacts.

### R — Repudiation

**Threat:** tenant claims CDIL fabricated or altered issuance.

**Mitigations:**
* ✅ Include issuance timestamp, `tenant_id`, `key_id`, `key_version` in signed payload.
* ⚠️ No non-PHI audit logs with `request_id` and `certificate_id`.

**Required:**
* Maintain structured audit logs.
* Include request/response correlation IDs.

### I — Information disclosure

**Threat:** PHI leaks via logs, errors, traces, analytics.

**Current mitigations:**
* ✅ PHI pattern detection in note text.
* ✅ No plaintext PHI in database.
* ⚠️ No log sanitization middleware.
* ⚠️ No automated tests for PHI in logs.

**Required mitigations:**
* Log sanitization middleware that redacts forbidden fields.
* Automated tests that fail build if forbidden keys appear in logs.
* Structured logging allowlist, not blocklist.

### D — Denial of service

**Threat:** flooding signer or verification endpoints.

**Current mitigations:**
* ⚠️ **NONE**

**Required mitigations:**
* Rate limiting per tenant and per IP.
* Request size caps.
* Circuit breakers around signer/KMS calls.

### E — Elevation of privilege

**Threat:** exploit to sign using another tenant's key.

**Current vulnerability:** ⚠️ **CRITICAL GAP**
* Signer uses global `dev-key-01` for all tenants.
* `tenant_id` accepted from request body, not enforced against auth.
* No tenant→key mapping.

**Required mitigations:**
* Signer must map `tenant_id` → `key_id` server-side.
* Key material must be partitioned per tenant (KMS key per tenant or per-tenant keyring).
* Authorization checks before signing; deny if tenant mismatch.
* Explicit tests: "T2 cannot sign payload labeled T1."

---

## 11. Key management policy (v1.0)

### Current Keying Strategy (MVP)

* **Single global development key:**
  * `key_id`: `dev-key-01`
  * Algorithm: ECDSA P-256
  * Location: `gateway/app/dev_keys/dev_private.pem`
  * Public key: `gateway/app/dev_keys/dev_public.jwk.json`

### Target Keying Strategy (Production)

* **Unique signing key per tenant** (minimum), with versioning:
  * `(tenant_id, key_version)` selects a private key
  * Public keys available for verification (JWKS-like endpoint or API)
  * Keys stored in KMS (AWS KMS, GCP KMS, Azure Key Vault) or HSM

### Rotation

* Rotation creates a new `key_version` for the tenant.
* New receipts are signed with newest version.
* Historical receipts remain verifiable using historical public keys.
* Public key history maintained in `keys` table.

### Compromise Response

* If tenant private key is compromised:
  * Mark `key_version` as "compromised at time X"
  * Optionally re-issue trust anchors / rotate immediately
  * Verification must surface "valid signature but issued under compromised key after X" as a **policy warning**.

### Migration Path: Global → Per-Tenant Keys

1. **Phase 1 (Current):** Single global dev key for MVP
2. **Phase 2:** Implement per-tenant key generation API
3. **Phase 3:** Migrate signer to enforce tenant→key mapping
4. **Phase 4:** Deprecate global key, require per-tenant keys
5. **Phase 5:** Integrate KMS for production key storage

---

## 12. Migrations & integrity-chain stability

### Requirement

Schema changes must not invalidate historical verification.

### Current Implementation

* Schema version not tracked in signed payload (⚠️ gap).
* `certificate_json` stores complete certificate as JSON blob.
* Verification reconstructs canonical message from stored fields.

### Required Controls

* Version signed payload schema (`payload_schema_version` field).
* DB migrations must preserve stored signed payload bytes or canonical fields.
* Verification must support multiple schema versions.
* Add schema version to canonical message in future iterations.

---

## 13. Logging and observability contract (Zero-PHI enforcement)

### Forbidden in logs/traces

* `note_text`, `patient_id`, `patient_reference`, MRN, DOB, names, addresses, free-text clinical content.

### Current Status

* ⚠️ Not implemented.
* No logging middleware.
* No automated tests for PHI leakage.

### Required controls

* Central logger wrapper with allowlist keys.
* CI test suite that simulates typical requests and asserts logs contain no forbidden keys.
* Error responses must avoid echoing request bodies.
* Structured logging (JSON) with explicit field allowlist.

### Implementation Checklist

- [ ] Create `gateway/app/middleware/logging_middleware.py`
- [ ] Define allowed log fields (allowlist)
- [ ] Add pytest fixture that captures logs during tests
- [ ] Add test: `test_no_phi_in_logs` that submits request and asserts forbidden keys absent
- [ ] Integrate middleware in `main.py`

---

## 14. Security test checklist (v1.0)

### Current Tests (from test_clinical_endpoints.py)

* ✅ Certificate issuance with minimal fields
* ✅ Certificate issuance with full PHI (hashed)
* ✅ Chain linkage verification (second cert links to first)
* ✅ PHI never stored in plaintext (database inspection)
* ✅ Timing integrity (finalized_at vs ehr_referenced_at)

### Required Security Tests (Missing)

* ❌ **Cross-tenant signing negative tests** (T2 cannot sign as T1)
* ❌ **Cross-tenant read isolation tests** (T2 cannot fetch T1 receipts via X-Tenant-Id)
* ❌ **Replay tests** (same request_id cannot mint a second distinct certificate)
* ❌ **Canonicalization tests** (same note_text => same note_hash under defined rules)
* ❌ **Log redaction tests** (forbidden keys never appear in logs)
* ❌ **Key rotation tests** (old certs verify; new certs use new key_version)

### Test Implementation Plan

1. **Cross-tenant signing test:**
   ```python
   def test_cannot_sign_as_other_tenant():
       # Issue cert as tenant A
       # Attempt to issue cert as tenant B with same auth/session
       # Assert: should fail (once tenant→key mapping enforced)
   ```

2. **Cross-tenant read isolation test:**
   ```python
   def test_cannot_read_other_tenant_cert():
       # Issue cert for tenant A
       # Attempt GET with X-Tenant-Id: B
       # Assert: 404 (not 403, to avoid revealing existence)
   ```

3. **Log redaction test:**
   ```python
   def test_phi_not_in_logs(caplog):
       # Submit request with note_text containing PHI
       # Assert: caplog.text does not contain note_text content
       # Assert: caplog.text does not contain "patient_reference"
   ```

---

## 15. Security Gaps & Remediation Plan

### Critical Gaps (Must Fix for Production)

#### Gap 1: Global Signing Key

**Issue:** Single `dev-key-01` signs certificates for all tenants.

**Risk:** Compromised tenant can forge certificates for other tenants.

**Remediation:**
1. Implement per-tenant key generation in `signer.py`
2. Add `tenant_keys` table mapping `tenant_id` → `key_id`
3. Modify `sign_generic_message()` to accept `tenant_id` parameter
4. Enforce tenant→key lookup in signer (fail if mismatch)
5. Update tests to verify cross-tenant signing prevention

**Timeline:** Phase 2 (before production)

#### Gap 2: Client-Supplied tenant_id

**Issue:** `tenant_id` accepted from request body, not derived from authentication.

**Risk:** Any authenticated user can issue certificates as any tenant.

**Remediation:**
1. Implement authentication middleware (JWT, OAuth, API keys)
2. Extract `tenant_id` from auth token claims
3. Ignore `tenant_id` in request body for issuance
4. Add integration tests verifying auth-derived tenant enforcement

**Timeline:** Phase 2 (before production)

#### Gap 3: No Audit Logging

**Issue:** No structured logging of certificate issuance/verification events.

**Risk:** Forensic investigation impossible, PHI leakage undetected.

**Remediation:**
1. Implement logging middleware with PHI allowlist
2. Log: `certificate_id`, `tenant_id`, `timestamp`, `action`, `result`
3. Exclude: `note_text`, `patient_reference`, `human_reviewer_id`
4. Add pytest tests asserting forbidden keys never logged

**Timeline:** Phase 2 (before production)

### Medium Priority Gaps

#### Gap 4: No Rate Limiting

**Remediation:** Add per-tenant and per-IP rate limiting (e.g., 100 req/min per tenant).

#### Gap 5: No KMS Integration

**Remediation:** Integrate AWS KMS, GCP KMS, or Azure Key Vault for production key storage.

#### Gap 6: Schema Versioning

**Remediation:** Add `payload_schema_version` to canonical message.

### Low Priority Gaps

* No database-level immutability constraints
* No request_id correlation in responses
* No circuit breakers around signer

---

## 16. Residual risk (known limitations)

* If an attacker controls the **client boundary** where note text is created, they can generate malicious content and still receive valid integrity artifacts.
* If the CDIL operator environment is compromised, keys may be exposed unless protected by KMS/HSM + tight IAM.
* Availability is dependent on infrastructure and rate-limiting correctness.
* MVP lacks authentication/authorization (planned for Phase 2).
* Single global key in MVP means no cryptographic tenant isolation (planned for Phase 2).

---

## 17. Signer Service Adversarial Audit

### File: `gateway/app/services/signer.py`

#### Function: `sign_generic_message(message_obj: Dict[str, Any]) -> Dict[str, Any]`

**Line 173-190:** Signs arbitrary message with global `dev-key-01`.

**Vulnerabilities:**
1. ❌ No `tenant_id` parameter accepted
2. ❌ No tenant→key mapping enforcement
3. ❌ Same key used for all tenants
4. ❌ No authorization check before signing

**Exploit path:**
```python
# Attacker with valid session for tenant "evil-corp"
# Crafts message with victim's tenant_id
canonical_message = {
    "certificate_id": "...",
    "tenant_id": "victim-hospital",  # ← Forged
    "timestamp": "...",
    "chain_hash": "...",
    "note_hash": "...",
    "governance_policy_version": "..."
}

# Calls POST /v1/clinical/documentation with forged tenant_id
# Server accepts tenant_id from body, calls sign_generic_message()
# Signer uses global dev-key-01, signs the forged payload
# Result: Valid certificate for victim-hospital, signed by CDIL
```

**Pass/Fail Verdict:** ❌ **FAIL** - Cryptographic boundary does NOT equal tenant boundary.

#### Minimal Patch to Harden

**Patch 1: Add tenant_id parameter and mapping (signer.py)**

```python
def sign_generic_message(message_obj: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    """
    Sign an arbitrary message object using the tenant's private key.
    
    Args:
        message_obj: Dictionary to sign (will be canonicalized)
        tenant_id: Tenant identifier (must match key selection)
        
    Returns:
        Dictionary containing signature bundle
        
    Raises:
        ValueError: If tenant_id in message doesn't match tenant_id parameter
        ValueError: If no key found for tenant
    """
    # Validate tenant_id consistency
    if message_obj.get("tenant_id") != tenant_id:
        raise ValueError(f"Message tenant_id '{message_obj.get('tenant_id')}' does not match auth tenant_id '{tenant_id}'")
    
    # Load tenant-specific key
    key_id, private_key = _load_tenant_key(tenant_id)
    
    # Canonicalize and sign
    canonical_bytes = json_c14n_v1(message_obj)
    signature = private_key.sign(
        canonical_bytes,
        ec.ECDSA(hashes.SHA256())
    )
    
    signature_b64 = base64.b64encode(signature).decode('utf-8')
    
    return {
        "algorithm": "ECDSA_SHA_256",
        "key_id": key_id,
        "canonical_message": message_obj,
        "signature": signature_b64
    }


def _load_tenant_key(tenant_id: str) -> tuple[str, Any]:
    """
    Load the private key for a specific tenant.
    
    Args:
        tenant_id: Tenant identifier
        
    Returns:
        Tuple of (key_id, private_key)
        
    Raises:
        ValueError: If no key found for tenant
    """
    from gateway.app.services.storage import get_tenant_key_id
    
    key_id = get_tenant_key_id(tenant_id)
    if not key_id:
        raise ValueError(f"No signing key found for tenant '{tenant_id}'")
    
    # For MVP: still use dev key but validate tenant has access
    # For production: load per-tenant key from KMS
    key_path = Path(__file__).parent.parent / "dev_keys" / "dev_private.pem"
    
    with open(key_path, 'rb') as f:
        private_key = serialization.load_pem_private_key(
            f.read(),
            password=None
        )
    
    return key_id, private_key
```

**Patch 2: Enforce tenant_id from auth (clinical.py)**

```python
@router.post("/v1/clinical/documentation", response_model=CertificateIssuanceResponse)
async def issue_certificate(
    request: ClinicalDocumentationRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id")  # ← Required from header
) -> CertificateIssuanceResponse:
    """
    Issue an integrity certificate for finalized clinical documentation.
    
    X-Tenant-Id header MUST match request.tenant_id (defense in depth).
    In production, x_tenant_id would be derived from auth token, not header.
    """
    
    # Enforce tenant_id from auth (header in MVP, token claims in prod)
    if request.tenant_id != x_tenant_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tenant_mismatch",
                "message": "Request tenant_id does not match authenticated tenant"
            }
        )
    
    # ... rest of issuance logic ...
    
    # Pass authenticated tenant_id to signer
    signature_bundle = sign_generic_message(canonical_message, tenant_id=x_tenant_id)
```

---

## 18. Conclusion

CDIL provides a solid foundation for clinical documentation integrity with cryptographic signatures and integrity chains. However, **critical security gaps** exist in the MVP implementation that must be addressed before production deployment:

1. **Global signing key** must be replaced with per-tenant keys
2. **Client-supplied tenant_id** must be replaced with auth-derived tenant context
3. **Audit logging** with PHI allowlist must be implemented
4. **Security tests** for cross-tenant isolation must be added

This threat model document will be updated as these gaps are addressed and the system evolves toward production readiness.

---

**Document Version:** 1.0
**Last Updated:** 2026-02-18
**Status:** Initial Release (MVP Security Baseline)
