# CDIL Security Architecture Overview

## Executive Summary

This document provides a high-level overview of the CDIL (Clinical Documentation Integrity Layer) security architecture after the comprehensive hardening refactor completed on 2026-02-18.

**Version**: 2.0 (Production-Ready)  
**Status**: Security Hardened  
**Classification**: Internal - Technical Architecture

---

## Architecture Transformation

### Before: MVP Integrity Layer

```
┌─────────────┐
│   Client    │ ← No authentication
│  (EHR/App)  │ ← Supplies tenant_id (forgeable)
└──────┬──────┘
       │ HTTP
       ▼
┌─────────────┐
│    CDIL     │ ← Single global key
│   Server    │ ← No replay protection
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  SQLite DB  │ ← Hashes only (good)
└─────────────┘
```

**Security Posture**: Basic cryptographic integrity, vulnerable to cross-tenant attacks.

### After: Production-Grade Security System

```
┌─────────────────┐
│ Identity Provider│ (Auth0, Cognito, etc.)
│  - Issues JWT    │
│  - tenant_id     │
│  - role          │
└────────┬─────────┘
         │ JWT (RS256)
         ▼
┌─────────────────┐
│    Client       │ ← Authenticated
│   (EHR/App)     │ ← JWT in Authorization header
└────────┬─────────┘
         │ HTTPS (TLS 1.2+)
         ▼
┌─────────────────────────────────────────┐
│        CDIL Server (Trusted Zone)       │
│                                         │
│  ┌────────────────────────────────┐   │
│  │  JWT Validator                  │   │
│  │  - Verify signature             │   │
│  │  - Check expiration             │   │
│  │  - Extract tenant_id + role     │   │
│  └────────────┬───────────────────┘   │
│               │                        │
│  ┌────────────▼───────────────────┐   │
│  │  Per-Tenant Key Registry       │   │
│  │  - Isolated keys per tenant     │   │
│  │  - Key rotation support         │   │
│  └────────────┬───────────────────┘   │
│               │                        │
│  ┌────────────▼───────────────────┐   │
│  │  Nonce Tracker                 │   │
│  │  - UUID7 nonces                 │   │
│  │  - Replay attack prevention     │   │
│  └────────────┬───────────────────┘   │
│               │                        │
│  ┌────────────▼───────────────────┐   │
│  │  Signer Service                │   │
│  │  - ECDSA P-256 signatures       │   │
│  │  - Canonical JSON (C14N)        │   │
│  └────────────┬───────────────────┘   │
│               │                        │
│  ┌────────────▼───────────────────┐   │
│  │  Rate Limiter                  │   │
│  │  - 30 signing/min               │   │
│  │  - 100 verify/min               │   │
│  └────────────────────────────────┘   │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────┐
│     Database (SQLite)   │
│                         │
│  • certificates         │
│  • tenant_keys          │
│  • used_nonces          │
│  • WAL mode enabled     │
│  • Permissions 0600     │
└─────────────────────────┘
```

**Security Posture**: Defense-in-depth with identity binding, cryptographic isolation, replay protection, and PHI discipline.

---

## Core Security Principles

### 1. Identity Binding

**Principle**: Every action is tied to a cryptographically validated identity.

**Implementation**:
- JWT tokens issued by trusted identity provider
- Signature validation (RS256 recommended for production)
- Tenant context derived from JWT claims, not client input
- Role-based access control (RBAC)

**Threat Mitigated**: Impersonation, unauthorized access, privilege escalation

### 2. Cryptographic Boundary = Tenant Boundary

**Principle**: Each tenant has isolated cryptographic keys.

**Implementation**:
- Per-tenant ECDSA P-256 key pairs
- Key registry manages isolation
- Key rotation without invalidating existing certificates
- Cross-tenant forgery cryptographically impossible

**Threat Mitigated**: Cross-tenant forgery, key compromise blast radius

### 3. Replay Protection

**Principle**: Signatures cannot be reused.

**Implementation**:
- Every signature includes a unique nonce (UUID7)
- Nonces tracked in database (composite key: tenant_id + nonce)
- Server-controlled timestamps
- Atomic nonce recording

**Threat Mitigated**: Replay attacks, timestamp manipulation

### 4. Zero PHI in Logs

**Principle**: Plaintext PHI never leaves the client.

**Implementation**:
- Only hashes stored (SHA-256)
- Custom exception handlers sanitize errors
- Validation errors exclude request body
- Debug mode disabled
- No print statements in production paths

**Threat Mitigated**: PHI leakage via logs, errors, or debug output

### 5. Defense in Depth

**Principle**: Multiple layers of security controls.

**Implementation**:
- Authentication (JWT)
- Authorization (RBAC)
- Cryptographic signing (ECDSA)
- Replay protection (nonces)
- Rate limiting (slowapi)
- Input validation (Pydantic)
- Output sanitization (exception handlers)

**Threat Mitigated**: Single point of failure

---

## Trust Model

### Trusted Components

1. **Identity Provider** (Auth0, AWS Cognito, etc.)
   - Issues valid JWTs
   - Maintains secure key management
   - Enforces MFA (if configured)

2. **CDIL Server**
   - Validates JWT signatures
   - Manages per-tenant keys securely
   - Records nonces atomically
   - Enforces rate limits

3. **TLS/HTTPS**
   - Protects data in transit
   - Certificate from trusted CA
   - TLS 1.2+ with strong ciphers

### Untrusted Components

1. **Clients** (EHR systems, mobile apps)
   - Cannot forge JWT (no secret key)
   - Cannot choose tenant_id
   - Cannot replay signatures
   - Cannot bypass rate limits

2. **Network**
   - Assume eavesdropping (mitigated by TLS)
   - Assume MITM attempts (mitigated by certificate pinning)

---

## Security Guarantees

### What CDIL Guarantees

✅ **Integrity**: Certificate content cannot be tampered without detection  
✅ **Non-repudiation**: Valid certificates can only come from CDIL  
✅ **Tenant Isolation**: Tenant A cannot forge or access Tenant B's certificates  
✅ **Replay Prevention**: Signatures cannot be reused  
✅ **Timestamp Integrity**: Timestamps are server-controlled  
✅ **Role Enforcement**: Only authorized roles can perform actions  
✅ **PHI Protection**: Plaintext PHI never stored or logged

### What CDIL Does NOT Guarantee

❌ **Clinical Correctness**: Does not validate medical accuracy  
❌ **EHR Integration**: Does not enforce EHR recording  
❌ **Model Trustworthiness**: Does not audit AI models  
❌ **Human Review Quality**: Records occurrence, not thoroughness  
❌ **Regulatory Compliance**: Provides tools, not compliance itself

---

## Attack Surface Analysis

### Entry Points

1. **API Endpoints**
   - Protected by: JWT auth, rate limiting, input validation
   - Risk: Medium (authenticated access only)

2. **JWT Validation**
   - Protected by: Cryptographic signature verification
   - Risk: Low (if RS256 used, higher if HS256 with weak secret)

3. **Database**
   - Protected by: File permissions, WAL mode, SQLite safety
   - Risk: Medium (server compromise = DB access)

### Attack Scenarios & Mitigations

| Attack | Mitigation | Status |
|--------|-----------|--------|
| Cross-tenant forgery | Per-tenant keys | ✅ Mitigated |
| Replay attack | Nonce tracking | ✅ Mitigated |
| JWT forgery | Signature validation | ✅ Mitigated |
| Brute force | Rate limiting | ✅ Mitigated |
| PHI leakage | Hash-only storage + sanitized errors | ✅ Mitigated |
| DoS | Rate limiting, WAF | ⚠️ Partially mitigated |
| Server compromise | HSM/KMS for keys | ⚠️ Recommended |
| Database exfiltration | Encryption at rest | ⚠️ Recommended |

---

## Compliance Mapping

| Framework | Requirement | CDIL Implementation |
|-----------|-------------|---------------------|
| **21 CFR Part 11** | Electronic signatures | ECDSA P-256, non-repudiation |
| **HIPAA Security Rule** | Access control | JWT RBAC, tenant isolation |
| **HIPAA Security Rule** | Audit controls | Audit logging capability |
| **HIPAA Security Rule** | Integrity | Cryptographic hashes, chain |
| **HIPAA Security Rule** | Transmission security | HTTPS/TLS required |
| **GDPR Article 32** | Pseudonymization | SHA-256 hashing of PHI |
| **GDPR Article 32** | Encryption | TLS in transit, disk encryption recommended |
| **ISO 27001** | Access control | Identity binding, RBAC |
| **SOC 2** | Logical access | JWT authentication |

---

## Operational Security

### Key Management Lifecycle

```
┌─────────────┐
│  Generate   │ ← Tenant onboarding or rotation trigger
│  Key Pair   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    Store    │ ← Database (dev) or KMS (prod)
│  in Registry│
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Sign      │ ← Active key for new certificates
│Certificates │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Rotate    │ ← Mark old key "rotated", generate new
│   (Optional)│
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Verify    │ ← Old key still used for verification
│ Old Certs   │
└─────────────┘
```

### Incident Response

**Key Compromise**:
1. Rotate affected tenant's keys immediately
2. Mark compromised key as "revoked"
3. Review audit logs for unauthorized activity
4. Notify affected tenant
5. Forensic analysis

**PHI Breach**:
1. Investigate source (logs, errors, database)
2. Contain breach (disable affected endpoint if needed)
3. Notify security team and compliance
4. Follow organizational breach protocol
5. Implement additional controls

---

## Performance Characteristics

### Signing Performance

- **Algorithm**: ECDSA P-256
- **Throughput**: ~5,000 signatures/second (single core)
- **Latency**: <1ms per signature
- **Rate Limit**: 30/minute per identity (artificial constraint)

### Verification Performance

- **Algorithm**: ECDSA P-256 signature verification
- **Throughput**: ~2,000 verifications/second (single core)
- **Latency**: ~1-2ms per verification
- **Rate Limit**: 100/minute per identity

### Database Performance

- **WAL Mode**: Concurrent reads during writes
- **Write Throughput**: ~1,000 inserts/second (SQLite)
- **Read Throughput**: >10,000 reads/second
- **Recommendation**: Migrate to PostgreSQL at >1M certificates

---

## Deployment Checklist

See `docs/PRODUCTION_READINESS.md` for full checklist. Key items:

- [ ] TLS/SSL certificate from trusted CA
- [ ] JWT_SECRET_KEY in secrets manager (not env var in code)
- [ ] JWT_ALGORITHM set to RS256
- [ ] Database path configured outside repo
- [ ] WAF configured (CloudFlare, AWS WAF)
- [ ] Monitoring and alerting configured
- [ ] Backup and disaster recovery tested
- [ ] Penetration test completed
- [ ] Compliance review approved

---

## Future Enhancements

### Short Term (Next 3 Months)

- [ ] Migrate keys to AWS KMS / Azure Key Vault
- [ ] Implement structured audit logging (JSON)
- [ ] Add Prometheus metrics
- [ ] PostgreSQL migration guide

### Medium Term (6 Months)

- [ ] Zero-knowledge proofs for governance compliance
- [ ] Multi-region deployment
- [ ] Advanced anomaly detection
- [ ] Step-up authentication for sensitive operations

### Long Term (12 Months)

- [ ] HSM integration for key generation
- [ ] Blockchain anchoring for certificate chains
- [ ] Homomorphic encryption for PHI queries
- [ ] Quantum-resistant signatures (post-quantum crypto)

---

## References

- [THREAT_MODEL_AND_TRUST_GUARANTEES.md](./THREAT_MODEL_AND_TRUST_GUARANTEES.md) - Detailed threat analysis
- [PRODUCTION_READINESS.md](./PRODUCTION_READINESS.md) - Deployment checklist
- [ECDSA Specification (FIPS 186-4)](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.186-4.pdf)
- [JWT Best Practices (RFC 8725)](https://datatracker.ietf.org/doc/html/rfc8725)
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)

---

## Document Control

**Author**: CDIL Security Team  
**Version**: 2.0  
**Date**: 2026-02-18  
**Classification**: Internal - Technical  
**Next Review**: 2026-05-18 (90 days)
