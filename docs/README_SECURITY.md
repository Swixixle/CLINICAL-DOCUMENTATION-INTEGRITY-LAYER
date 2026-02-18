# CDIL Security Documentation

This directory contains comprehensive security documentation for the Clinical Documentation Integrity Layer (CDIL).

## Documents

### 1. [THREAT_MODEL_AND_TRUST_GUARANTEES.md](./THREAT_MODEL_AND_TRUST_GUARANTEES.md)

**Comprehensive threat model and security contract document (18 sections)**

This is the primary security reference for CDIL. Read this first to understand:

- **System invariants** - Core security rules ("Zero-PHI", server-side sovereignty, tenant isolation)
- **Current architecture** - Reality check on runtime stack, tenant model, and signing keys
- **Data flow** - How PHI is handled from client to storage
- **Assets & trust boundaries** - What we protect and where boundaries exist
- **Security guarantees** - What CDIL promises (and doesn't promise)
- **Attacker model** - Four threat actor profiles
- **STRIDE analysis** - Complete threat analysis with mitigations
- **Key management policy** - Current and target keying strategies
- **Security gaps** - Critical vulnerabilities and remediation plans
- **Signer adversarial audit** - Line-by-line security review with exploit path

**Sections:**
1. Purpose & Scope
2. System Invariants
3. Current Architecture (Runtime, Tenant Model, Signing Keys)
4. Data Flow
5. Assets
6. Trust Boundaries (A-E)
7. Security Guarantees (G1-G5)
8. Non-Guarantees
9. Attacker Model (A-D)
10. Threat Analysis (STRIDE)
11. Key Management Policy
12. Migrations & Integrity-Chain Stability
13. Logging & Observability Contract
14. Security Test Checklist
15. Security Gaps & Remediation Plan
16. Residual Risk
17. Signer Service Adversarial Audit
18. Conclusion

**Key findings:**
- ❌ **FAIL**: Single global key enables cross-tenant forgery
- ⚠️ `tenant_id` accepted from request body (not auth-derived)
- ✅ PHI properly hashed, never stored in plaintext
- ✅ Tenant isolation at DB layer works correctly

### 2. [SECURITY_AUDIT_SUMMARY.md](./SECURITY_AUDIT_SUMMARY.md)

**Executive summary answering specific security audit questions**

Quick-reference document that answers:

1. **Repo reality check** - Runtime stack, deployment shape
2. **Tenant model** - What is a tenant? Field name? (`tenant_id`)
3. **Signing flow** - Where keys live (filesystem), current intent (global key - GAP)
4. **Data flow** - Zero-PHI confirmation (with important nuance)
5. **Artifacts** - Links to signer.py, models, API routes
6. **Adversarial audit results** - Pass/fail verdict (FAIL), exploit path
7. **Minimal hardening patch** - Three-part fix
8. **Security test requirements** - Critical tests to add
9. **Remediation timeline** - Phase 1/2/3 priorities

**Use this for:**
- Quick answers to security questions
- Understanding critical vulnerabilities
- Planning remediation work
- Explaining security posture to stakeholders

### 3. [test_security_boundaries.py](../gateway/tests/test_security_boundaries.py)

**Automated security tests validating threat model requirements**

**11 security tests (all passing):**

1. ✅ `test_cross_tenant_read_isolation` - T2 cannot retrieve T1's certificates
2. ✅ `test_cross_tenant_verify_isolation` - T2 cannot verify T1's certificates
3. ✅ `test_missing_tenant_header_rejected` - X-Tenant-Id required for GET/verify
4. ✅ `test_phi_pattern_detection_ssn` - SSN patterns rejected
5. ✅ `test_phi_pattern_detection_phone` - Phone patterns rejected
6. ✅ `test_phi_pattern_detection_email` - Email patterns rejected
7. ✅ `test_note_text_never_persisted` - Plaintext note never in DB
8. ✅ `test_patient_and_reviewer_hashed` - Patient/reviewer IDs hashed
9. ✅ `test_chain_integrity_per_tenant` - Chains don't cross tenants
10. ✅ `test_signature_verification_valid` - Signatures verify correctly
11. ✅ `test_query_certificates_tenant_isolation` - Query enforces tenant scope

**Run tests:**
```bash
pytest gateway/tests/test_security_boundaries.py -v
```

**Coverage:**
- Tenant boundary enforcement
- PHI leakage prevention
- Cryptographic integrity
- Authorization enforcement

---

## Quick Start

### For Security Reviewers

1. Read [SECURITY_AUDIT_SUMMARY.md](./SECURITY_AUDIT_SUMMARY.md) first (10 min)
2. Review critical findings in Section 6 (adversarial audit results)
3. Check remediation timeline (Section 9)
4. Dive into [THREAT_MODEL_AND_TRUST_GUARANTEES.md](./THREAT_MODEL_AND_TRUST_GUARANTEES.md) for full details

### For Developers

1. Review [THREAT_MODEL_AND_TRUST_GUARANTEES.md](./THREAT_MODEL_AND_TRUST_GUARANTEES.md) Sections 2-4 (invariants, architecture, data flow)
2. Read Section 15 (security gaps) for what needs fixing
3. Run security tests: `pytest gateway/tests/test_security_boundaries.py -v`
4. Implement fixes from Section 17 (minimal hardening patch)

### For Compliance/Legal

1. Read [SECURITY_AUDIT_SUMMARY.md](./SECURITY_AUDIT_SUMMARY.md) Section 4 (Zero-PHI confirmation)
2. Review [THREAT_MODEL_AND_TRUST_GUARANTEES.md](./THREAT_MODEL_AND_TRUST_GUARANTEES.md) Section 7 (guarantees)
3. Review Section 8 (non-guarantees)
4. Review Section 16 (residual risk)

---

## Critical Findings Summary

### ❌ Cross-Tenant Certificate Forgery (Critical)

**Issue:** Any authenticated user can forge certificates for ANY tenant.

**Root cause:** 
- Single global signing key (`dev-key-01`) for all tenants
- `tenant_id` accepted from request body (not auth-derived)

**Impact:** Reputation damage, regulatory liability, trust violation

**Remediation:** See [THREAT_MODEL_AND_TRUST_GUARANTEES.md](./THREAT_MODEL_AND_TRUST_GUARANTEES.md) Section 17 (minimal patch)

**Timeline:** Phase 1 (pre-production blocker)

### ✅ Zero-PHI Discipline (Working)

**Status:** PHI properly hashed, never stored in plaintext

**Evidence:** Security tests validate no plaintext in database

**Caveat:** Server DOES receive plaintext momentarily (hashes server-side)

**Future:** Consider client-side hashing for defense-in-depth

### ⚠️ Missing Authentication (Gap)

**Status:** No authentication layer in MVP

**Impact:** Anyone can issue certificates

**Remediation:** Phase 2 (before production)

### ⚠️ No Audit Logging (Gap)

**Status:** No structured logging with PHI controls

**Impact:** Forensic investigation impossible, PHI leakage undetected

**Remediation:** Phase 2 (before production)

---

## Document Updates

**Last updated:** 2026-02-18  
**Threat model version:** 1.0  
**Status:** Initial release (MVP security baseline)

These documents should be updated when:
- Architecture changes (new components, key storage migration)
- Security controls added (authentication, KMS, logging)
- Vulnerabilities discovered or fixed
- Production deployment planned

---

## Questions?

For security questions or to report vulnerabilities:
- Review threat model first: [THREAT_MODEL_AND_TRUST_GUARANTEES.md](./THREAT_MODEL_AND_TRUST_GUARANTEES.md)
- Check executive summary: [SECURITY_AUDIT_SUMMARY.md](./SECURITY_AUDIT_SUMMARY.md)
- Run security tests: `pytest gateway/tests/test_security_boundaries.py -v`
- Create GitHub issue with "security" label

**Do not include PHI or sensitive data in issues or pull requests.**
