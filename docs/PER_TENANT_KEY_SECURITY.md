# Per-Tenant Key Isolation - Security Guarantee

## Overview

CDIL enforces **strict per-tenant cryptographic key isolation** to prevent cross-tenant forgery and ensure certificates cannot be tampered with across organizational boundaries.

## Critical Security Contract

### ✅ What CDIL Guarantees

1. **Per-Tenant Keys Required**
   - Every certificate MUST be signed with a tenant-specific key
   - No shared keys across tenants
   - No global fallback keys

2. **Cross-Tenant Forgery Prevention**
   - Tenant A cannot create certificates for Tenant B
   - Each tenant's key material is cryptographically isolated
   - Key IDs are scoped to tenant context

3. **Key Lookup Enforcement**
   - Certificate verification ALWAYS validates tenant_id matches key ownership
   - Missing keys result in verification failure (no fallback)
   - Key registry enforces tenant-scoped lookups

### ❌ What CDIL Does NOT Allow

1. **No Global Dev Key Fallback**
   - Legacy dev key fallback has been **permanently removed** (as of v2.1.0)
   - Any `tenant_id=None` path raises `ValueError`
   - All signing operations require explicit tenant_id

2. **No Cross-Tenant Key Sharing**
   - Keys are never shared between tenants
   - Even if two tenants trust each other, they use separate keys
   - Key rotation is per-tenant

3. **No Anonymous Certificates**
   - Every certificate MUST have a `tenant_id`
   - Certificates without tenant context are rejected at signing
   - JWT claims MUST include `tenant_id`

## Code-Level Enforcement

### Signing (gateway/app/services/signer.py)

```python
def sign_generic_message(message_obj: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    """
    Sign an arbitrary message object using per-tenant keys.
    
    Args:
        tenant_id: Tenant ID for per-tenant signing (REQUIRED - no legacy fallback)
    
    Raises:
        ValueError: If tenant_id is None or empty (no legacy fallback allowed)
    """
    if not tenant_id:
        raise ValueError(
            "tenant_id is required for signing operations. "
            "Legacy fallback to dev key has been removed for security. "
            "All certificates must use per-tenant keys."
        )
    
    # Get tenant's active key (generates if needed)
    registry = get_key_registry()
    key_data = registry.get_active_key(tenant_id)
    # ... signing logic ...
```

### Verification (gateway/app/routes/clinical.py)

```python
# Look up key from tenant key registry
registry = get_key_registry()
key_data = registry.get_key_by_id(tenant_id, key_id)

if not key_data:
    # No fallback - per-tenant keys are required for security
    # Cross-tenant key usage would be a critical security vulnerability
    failures.append(fail("signature", "key_not_found"))
    jwk = None
else:
    jwk = key_data.get("public_jwk")
```

### Authentication (gateway/app/security/auth.py)

```python
if not tenant_id:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": "missing_claim",
            "message": "Token missing 'tenant_id' claim"
        }
    )
```

## Threat Model

### Threat: Cross-Tenant Certificate Forgery

**Attack Scenario:**
1. Attacker compromises Tenant A's credentials
2. Attacker attempts to issue certificate with `tenant_id=hospital-beta`
3. CDIL signs with Tenant A's key
4. Tenant B verifies and accepts forged certificate

**CDIL Mitigation:**
- `tenant_id` is **derived from JWT claims**, not request body
- JWT signature verification enforces identity
- Signing uses key scoped to authenticated tenant
- Verification checks key ownership matches certificate `tenant_id`

**Result:** Attack fails at JWT verification (Step 2) OR at certificate verification (Step 4).

### Threat: Global Key Fallback Exploitation

**Attack Scenario:**
1. Attacker discovers legacy dev key in git history
2. Attacker crafts certificate with `key_id=dev-key-01`
3. CDIL falls back to global dev key for verification
4. Forged certificate validates

**CDIL Mitigation (v2.1.0+):**
- **Global dev key fallback removed entirely**
- Missing key results in `key_not_found` failure
- No path exists where `tenant_id=None` is accepted
- Dev keys only used in test environments (ENV=TEST)

**Result:** Attack fails at verification (Step 3) - no fallback path exists.

### Threat: Key Registry Bypass

**Attack Scenario:**
1. Attacker bypasses key registry lookup
2. Attacker provides their own public key for verification
3. Certificate validates with attacker's key

**CDIL Mitigation:**
- Key registry is **only source of truth** for public keys
- No API endpoint accepts public key in request
- Verification code does not allow key injection
- Key lookup is scoped to tenant context

**Result:** No attack surface - key registry cannot be bypassed.

## Verification Evidence

### Test Coverage

See `gateway/tests/test_phase5_cleanup.py`:

```python
def test_sign_without_tenant_id_raises_error():
    """Test that signing without tenant_id raises ValueError."""
    message = {"certificate_id": "test", "timestamp": "..."}
    
    with pytest.raises(ValueError, match="tenant_id is required"):
        sign_generic_message(message, tenant_id=None)


def test_sign_with_empty_tenant_id_raises_error():
    """Test that signing with empty tenant_id raises ValueError."""
    message = {"certificate_id": "test", "timestamp": "..."}
    
    with pytest.raises(ValueError, match="tenant_id is required"):
        sign_generic_message(message, tenant_id="")
```

### Security Boundaries Test

See `gateway/tests/test_security_boundaries.py`:

```python
def test_cross_tenant_certificate_verification_fails():
    """
    Test that Tenant A cannot verify a certificate signed by Tenant B
    using Tenant B's key ID.
    """
    # Create certificate with tenant-alpha
    cert = issue_certificate(tenant_id="tenant-alpha", ...)
    
    # Try to verify with tenant-beta context
    response = client.post(
        f"/v1/certificates/{cert_id}/verify",
        headers=create_headers(tenant_id="tenant-beta")
    )
    
    # Should fail - key lookup is scoped to tenant-beta
    assert response.status_code == 200
    assert result["status"] == "FAIL"
    assert "key_not_found" in result["reason"]
```

## Audit Trail

All key operations are logged with tenant context:

```json
{
  "timestamp": "2026-02-19T00:00:00Z",
  "event": "key_generated",
  "tenant_id": "hospital-alpha",
  "key_id": "key_01...",
  "algorithm": "ECDSA_P256"
}
```

```json
{
  "timestamp": "2026-02-19T00:00:00Z",
  "event": "certificate_signed",
  "tenant_id": "hospital-alpha",
  "certificate_id": "cert_01...",
  "key_id": "key_01...",
  "user_id": "user_..."
}
```

## Key Rotation

### Rotation Triggers

1. **Routine:** Every 90 days
2. **Compromise:** Immediately upon suspected exposure
3. **Tenant Request:** On-demand via API

### Rotation Procedure

1. Generate new key pair for tenant
2. Mark new key as "active"
3. Mark old key as "inactive" (but retain for verification)
4. Update tenant's default key_id
5. Emit audit event

**Historical certificates remain verifiable** with old keys (marked "inactive" but not deleted).

### Rotation Testing

```bash
# Future API endpoint
POST /v1/keys/rotate
Authorization: Bearer <admin-jwt>
{
  "tenant_id": "hospital-alpha"
}

# Response
{
  "old_key_id": "key_01...",
  "new_key_id": "key_02...",
  "rotated_at": "2026-02-19T00:00:00Z"
}
```

## Compliance

### SOC 2 Requirements

**CC6.1 - Logical Access Controls:**
- ✅ Per-tenant keys enforce logical separation
- ✅ No shared credentials across tenants
- ✅ Key material encrypted at rest

**CC6.6 - Logical and Physical Access:**
- ✅ Keys scoped to tenant context
- ✅ No global keys or fallbacks

**CC6.7 - Restriction of Access:**
- ✅ Key registry enforces access control
- ✅ JWT claims define tenant scope

### HIPAA Requirements

**164.312(a)(2)(i) - Unique User Identification:**
- ✅ Each tenant has unique cryptographic identity
- ✅ Certificates cannot be forged across tenants

**164.312(e)(2)(i) - Integrity Controls:**
- ✅ Signatures prevent tampering
- ✅ Per-tenant keys ensure non-repudiation

## FAQ

### Q: Can two tenants share a key if they're part of the same hospital system?

**A:** No. Even if two tenants are related, they must use separate keys. This ensures:
- Blast radius is limited if one tenant is compromised
- Certificates are scoped to the issuing tenant
- Audit trails are unambiguous

### Q: What happens if a tenant's key is compromised?

**A:** 
1. Immediately rotate the tenant's key
2. Mark compromised key as "revoked"
3. Review audit logs for unauthorized certificate issuance
4. Notify affected parties
5. Re-issue certificates if needed

### Q: Can I use the dev key in production for testing?

**A:** Absolutely not. The dev key is:
- Committed to git history (COMPROMISED)
- Shared across all dev environments
- Not intended for production use

Production MUST use per-tenant keys generated at runtime.

### Q: How do I verify a certificate was signed by a specific tenant?

**A:**
1. Check the certificate's `tenant_id` field
2. Look up the certificate's `signature.key_id`
3. Verify key_id belongs to tenant (via key registry)
4. Verify signature using tenant's public key

### Q: Can CDIL issue certificates without a tenant_id?

**A:** No. As of v2.1.0, all signing operations require a valid `tenant_id`. Any attempt to sign without one raises `ValueError`.

---

## Version History

**v2.1.0 (2026-02-19):**
- Removed global dev key fallback from `clinical.py`
- Added explicit tenant_id validation in `signer.py`
- All tests updated to enforce per-tenant keys

**v2.0.0 (2026-02-18):**
- Initial per-tenant key implementation
- Key registry with tenant-scoped lookup
- Nonce-based replay protection

---

## Contact

**Security Questions:** security@example.com  
**Key Rotation Requests:** [Support Portal]  
**Incident Response:** [PagerDuty/OpsGenie]
