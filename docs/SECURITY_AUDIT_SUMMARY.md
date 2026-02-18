# CDIL Security Audit Summary

## Executive Summary

This document provides direct answers to the security audit questions and summarizes critical findings from the adversarial audit of CDIL's signing service.

---

## 1. Repo Reality Check

### Runtime Stack
- **Framework:** FastAPI 0.109.0+
- **Database:** SQLite (local file)
- **Cryptography:** Python `cryptography` library
- **Signing:** ECDSA with SHA-256 (P-256 curve)
- **Queue:** None
- **Redis:** None
- **KMS:** None (dev keys on filesystem)

### Deployment
- **Shape:** Single server (MVP/development)
- **Not k8s, not ECS** - simple single-process FastAPI app

---

## 2. Tenant Model

### What is a "tenant"?
A **hospital organization, healthcare facility, or customer account** using CDIL for integrity certification.

Examples: `"hospital-alpha"`, `"clinic-beta"`, `"health-system-gamma"`

### Tenant identifier field name
**`tenant_id`** (string field)

Used everywhere:
- Request body: `request.tenant_id`
- Database: `certificates.tenant_id`
- Headers: `X-Tenant-Id` (for GET/verify endpoints)

---

## 3. Signing Flow Specifics

### Where does the signing key live today?
**Filesystem:** `gateway/app/dev_keys/dev_private.pem`

**Key type:** ECDSA P-256 private key (PEM format)

**Public key:** `gateway/app/dev_keys/dev_public.jwk.json` (JWK format)

### Current intent: Per-tenant key or global key?
**Current implementation:** ⚠️ **GLOBAL KEY**

**Single key (`dev-key-01`) signs ALL tenant certificates.**

**Intended design (per security best practices):** Per-tenant keys

**Status:** Critical security gap identified - see remediation plan below.

---

## 4. Data Flow Constraints

### Confirm: Zero-PHI server-side?
**Partially true** with important nuance:

**What the server receives:**
- ✅ `note_text` **IS** sent to server (not just hash)
- ✅ `patient_reference` **IS** sent to server (not just hash)
- ✅ `human_reviewer_id` **IS** sent to server (not just hash)

**What the server does:**
1. Receives plaintext PHI fields
2. Validates `note_text` for obvious PHI patterns (SSN, phone, email) - **rejects if detected**
3. **Immediately hashes** all PHI fields using SHA-256
4. **Only stores hashes** (`note_hash`, `patient_hash`, `reviewer_hash`)
5. **Never persists plaintext** in database

**So technically:** Server **receives** PHI momentarily, but **never stores** it. Hash computation happens server-side, not client-side.

### Exceptions?
**None documented.**

No debug mode, no support tooling exceptions, no special cases where plaintext PHI is logged or persisted.

**Gap:** No automated tests or middleware to **prove** PHI never appears in logs. This is a required security control.

---

## 5. Artifacts

### `gateway/app/services/signer.py`

**See:** Attached in this repository at `gateway/app/services/signer.py`

**Key functions:**
- `sign_generic_message(message_obj)` - Signs arbitrary message with global dev key
- `verify_signature(bundle, jwk)` - Verifies signature using JWK public key
- `_load_private_key()` - Loads `dev_private.pem` from filesystem

### Models/schemas for certificates

**See:** `gateway/app/models/clinical.py`

**Key models:**
- `ClinicalDocumentationRequest` - Issuance request schema
- `DocumentationIntegrityCertificate` - Certificate response schema
- `IntegrityChain` - Chain linkage schema
- `SignatureBundle` - Signature metadata schema

### API route that calls the signer

**See:** `gateway/app/routes/clinical.py`

**Key endpoint:** `POST /v1/clinical/documentation` (lines 136-277)

**Flow:**
1. Receive request with `tenant_id` and `note_text`
2. Validate PHI patterns
3. Hash PHI fields
4. Get tenant chain head
5. Compute chain hash
6. Build canonical message
7. **Call `sign_generic_message(canonical_message)`** (line 236)
8. Store certificate
9. Return response

---

## 6. Adversarial Audit Results

### Pass/Fail Verdict

❌ **FAIL** - The cryptographic boundary does **NOT** equal the tenant boundary.

### Critical Vulnerability: Cross-Tenant Certificate Forgery

**Issue:** Any user who can call the issuance API can forge certificates for ANY tenant.

**Root causes:**
1. ✅ `tenant_id` accepted from request body, not derived from authentication
2. ✅ Single global signing key (`dev-key-01`) used for ALL tenants
3. ✅ No tenant→key mapping in signer
4. ✅ Signer does not enforce authorization or tenant context

**Exploit path:**

```python
# Attacker has API access (or no auth required in MVP)
# Attacker forges certificate for victim tenant:

POST /v1/clinical/documentation
Content-Type: application/json

{
  "tenant_id": "victim-hospital",  # ← Forged tenant ID
  "model_version": "gpt-4",
  "prompt_version": "v1",
  "governance_policy_version": "v1",
  "note_text": "Malicious note content",
  "human_reviewed": false
}

# Server accepts tenant_id from body
# Server calls sign_generic_message() with forged tenant_id in message
# Signer uses global dev-key-01 (no tenant check)
# Result: Valid certificate for victim-hospital, cryptographically signed by CDIL
# Victim cannot distinguish this from legitimate certificates
```

**Impact:**
- Cross-tenant certificate forgery
- No cryptographic attribution to actual issuer
- Reputation damage if discovered
- Regulatory/legal liability

---

## 7. Minimal Hardening Patch

### Three-Part Fix

#### Fix 1: Add tenant_id parameter to signer

**File:** `gateway/app/services/signer.py`

**Change:**
```python
def sign_generic_message(message_obj: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    """Sign message using tenant-specific key."""
    
    # Validate tenant_id in message matches auth context
    if message_obj.get("tenant_id") != tenant_id:
        raise ValueError(
            f"Message tenant_id '{message_obj.get('tenant_id')}' "
            f"does not match authenticated tenant '{tenant_id}'"
        )
    
    # Load tenant-specific key (or fail)
    key_id, private_key = _load_tenant_key(tenant_id)
    
    # ... rest of signing logic ...
```

#### Fix 2: Enforce tenant_id from auth

**File:** `gateway/app/routes/clinical.py`

**Change:**
```python
@router.post("/v1/clinical/documentation")
async def issue_certificate(
    request: ClinicalDocumentationRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id")  # Required
):
    # Enforce tenant_id matches auth
    if request.tenant_id != x_tenant_id:
        raise HTTPException(403, detail="Tenant mismatch")
    
    # ... rest of logic ...
    
    # Pass authenticated tenant_id to signer
    signature_bundle = sign_generic_message(
        canonical_message,
        tenant_id=x_tenant_id  # ← From auth, not request body
    )
```

#### Fix 3: Implement per-tenant key mapping

**File:** `gateway/app/services/storage.py` (new function)

**Add:**
```python
def get_tenant_key_id(tenant_id: str) -> str | None:
    """Get the active signing key ID for a tenant."""
    from gateway.app.db.migrate import get_connection
    
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT key_id FROM tenant_keys
            WHERE tenant_id = ? AND status = 'active'
            ORDER BY created_at_utc DESC
            LIMIT 1
        """, (tenant_id,))
        row = cursor.fetchone()
        return row['key_id'] if row else None
    finally:
        conn.close()
```

**Database migration:**
```sql
-- Add tenant_keys table
CREATE TABLE IF NOT EXISTS tenant_keys (
    tenant_id TEXT NOT NULL,
    key_id TEXT NOT NULL,
    status TEXT NOT NULL,  -- 'active', 'rotated', 'compromised'
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY (tenant_id, key_id)
);

CREATE INDEX IF NOT EXISTS idx_tenant_keys_status 
ON tenant_keys(tenant_id, status);
```

---

## 8. Security Test Requirements

### Critical Tests (Must Add)

#### Test 1: Cross-tenant signing prevention
```python
def test_cannot_sign_as_other_tenant():
    """Verify T2 cannot sign certificates as T1."""
    # Issue cert for tenant-A
    response_a = client.post(
        "/v1/clinical/documentation",
        headers={"X-Tenant-Id": "tenant-A"},
        json={...}
    )
    assert response_a.status_code == 201
    
    # Attempt to issue cert for tenant-B with tenant-A auth
    response_b = client.post(
        "/v1/clinical/documentation",
        headers={"X-Tenant-Id": "tenant-A"},  # A's auth
        json={"tenant_id": "tenant-B", ...}  # Forged B's ID
    )
    assert response_b.status_code == 403  # Should fail
    assert "tenant_mismatch" in response_b.json()["detail"]
```

#### Test 2: Cross-tenant read isolation
```python
def test_cannot_read_other_tenant_cert():
    """Verify T2 cannot retrieve T1's certificates."""
    # Issue cert for tenant-A
    cert_id = issue_cert_for_tenant("tenant-A")
    
    # Attempt to retrieve with tenant-B auth
    response = client.get(
        f"/v1/certificates/{cert_id}",
        headers={"X-Tenant-Id": "tenant-B"}
    )
    assert response.status_code == 404  # Not 403, hide existence
    assert "not found" in response.json()["detail"]
```

#### Test 3: PHI never in logs
```python
def test_phi_not_in_logs(caplog):
    """Verify note_text and patient_reference never appear in logs."""
    sensitive_data = {
        "tenant_id": "test-hospital",
        "note_text": "Patient John Doe has diabetes",
        "patient_reference": "MRN-12345",
        ...
    }
    
    response = client.post("/v1/clinical/documentation", json=sensitive_data)
    assert response.status_code == 201
    
    # Check logs
    log_text = caplog.text
    assert "John Doe" not in log_text
    assert "MRN-12345" not in log_text
    assert sensitive_data["note_text"] not in log_text
```

---

## 9. Remediation Timeline

### Phase 1: Immediate (Pre-Production Blocker)
- [ ] Implement tenant_id enforcement from auth header
- [ ] Add tenant→key mapping table
- [ ] Update signer to validate tenant context
- [ ] Add cross-tenant signing prevention tests

**Estimated effort:** 2-3 days

### Phase 2: Short-term (Production Requirements)
- [ ] Implement per-tenant key generation
- [ ] Add logging middleware with PHI allowlist
- [ ] Add audit logging (certificate issuance/verification)
- [ ] Add rate limiting per tenant

**Estimated effort:** 1-2 weeks

### Phase 3: Medium-term (Operational Maturity)
- [ ] Integrate KMS (AWS/GCP/Azure)
- [ ] Implement key rotation workflow
- [ ] Add monitoring and alerting
- [ ] Add break-glass access controls

**Estimated effort:** 2-4 weeks

---

## 10. Conclusion

**Current state:** MVP with functional cryptographic signatures, but **critical tenant isolation gap**.

**Immediate action:** Implement tenant_id enforcement from authentication before any production use.

**Security posture:** 
- ✅ Strong cryptographic primitives (ECDSA P-256)
- ✅ PHI never persisted in plaintext
- ✅ Integrity chain prevents tampering
- ❌ **No tenant isolation** at cryptographic layer
- ❌ No authentication/authorization
- ❌ No audit logging

**Recommendation:** Do not deploy to production until Phase 1 remediation complete.

---

**Audit Date:** 2026-02-18
**Auditor:** CDIL Security Review
**Status:** Critical findings - remediation required
