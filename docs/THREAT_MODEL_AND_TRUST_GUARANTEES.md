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
