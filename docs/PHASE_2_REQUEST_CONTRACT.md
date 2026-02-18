# Phase 2 Request Contract

## Overview

This document defines the canonical request contract for Phase 2 of ELI Sentinel. These specifications are **locked** and form part of the protocol's governance model.

## Core Principle

In Phase 2, governance-critical fields are **explicit request parameters**, not derived from authentication context or deployment configuration. This design choice enables:

1. **Environment-specific policy evaluation** without infrastructure coupling
2. **Client-specific governance rules** independent of auth tokens
3. **Complete auditability** with all governance factors in the accountability packet

## Required Fields

### `environment`

**Type:** `Literal["prod", "staging", "dev"]`  
**Required:** Yes  
**Feeds HALO:** Yes (Block 1 - Genesis)

The environment field identifies the deployment environment for policy evaluation.

**Validation:**
- Must be exactly one of: `"prod"`, `"staging"`, `"dev"`
- Enforced via Pydantic `Literal` type constraint
- Invalid values rejected at request validation (400 Bad Request)

**Usage in governance:**
- Environment-specific policy rules (e.g., network access restrictions in prod)
- Temperature constraints by environment
- Model allowlists by environment

**Phase evolution:**
- Phase 2: Explicit request field (current)
- Future phases: May move to auth context with protocol version bump
- Any change requires protocol version increment and backward compatibility

**Example:**
```json
{
  "environment": "prod",
  ...
}
```

### `client_id`

**Type:** `str`  
**Required:** Yes  
**Feeds HALO:** Yes (Block 1 - Genesis)

The client identifier specifies the calling application or service.

**Validation:**
- Non-empty string
- No format restrictions in Phase 2 (intentionally flexible)

**Usage in governance:**
- Client-specific policy rules
- Rate limiting and quota tracking
- Accountability attribution

**Phase evolution:**
- Phase 2: Explicit request field, not trusted for authentication
- Future phases: May derive from validated auth token (mTLS, JWT)
- Identity/auth integration is explicitly out of scope for Phase 2

**Example:**
```json
{
  "client_id": "billing-service-v2",
  ...
}
```

## Security Posture

### Not Used for Authentication

In Phase 2, neither `environment` nor `client_id` are used for:
- Authentication
- Authorization  
- Identity verification
- Access control

These fields are **governance metadata only**. Authentication is out of scope.

### Tamper Evidence

Both fields feed into the HALO chain (Block 1 - Genesis):
- Any modification after packet creation breaks HALO verification
- Recomputed `final_hash` will not match stored commitment
- This enables detection of post-hoc tampering ("court-ready" proof)

## Policy Decision Flow

```
1. Request arrives with environment="prod" and client_id="billing-service"
2. Policy engine evaluates rules:
   - Check environment-specific constraints
   - Check client-specific constraints
   - Check feature-tag constraints
3. Decision: approved or denied (with reasons)
4. HALO chain captures environment + client_id in Block 1
5. Signature commits to final_hash
6. Packet persisted with tamper-evident proof
```

## Backward Compatibility

### Phase 2 → Phase 3 Migration

If future phases move these fields to auth context:

1. **Protocol version bump required** (e.g., `v1` → `v2`)
2. **Old packets remain valid** (they declare `protocol_metadata.halo_version = "v1"`)
3. **Verifiers handle both versions** based on packet metadata
4. **No retroactive changes** to Phase 2 contract

## Test Coverage

### Validation Tests

- `test_environment_values_are_consistent()` - Verifies environment stored exactly as provided
- Type validation at Pydantic layer rejects invalid environment values

### Tampering Detection

- `test_verify_detects_packet_field_tampering()` - Proves that tampering with ANY packet field (including `client_id` or `environment`) breaks verification
- Test mutates `policy_receipt.policy_change_ref` but principle applies to all HALO inputs

### Integration Tests

- All Phase 2.1 hardening tests use `environment` and `client_id`
- Policy engine tests verify environment-specific rule evaluation

## Code References

### Request Model

File: `gateway/app/models/requests.py`

```python
class AICallRequest(BaseModel):
    """Request body for /v1/ai/call endpoint.
    
    Phase 2 Request Contract Fields:
    - environment and client_id are REQUIRED canonical fields
    - They are part of the governance model and feed into HALO chain
    - environment must be one of: prod, staging, dev
    - client_id identifies the calling application/service
    
    These fields are not derived from auth tokens or deployment config
    in Phase 2. They are explicit request parameters that:
    1. Enable environment-specific policy evaluation
    2. Support client-specific governance rules
    3. Feed into the accountability packet for auditability
    """
    environment: Literal["prod", "staging", "dev"] = Field(..., description="Environment: prod, staging, or dev (REQUIRED)")
    client_id: str = Field(..., description="Client identifier (REQUIRED)")
    ...
```

### HALO Chain Builder

File: `gateway/app/services/halo.py`

```python
def build_halo_chain(
    transaction_id: str,
    gateway_timestamp_utc: str,
    environment: str,  # Used in Block 1 (Genesis)
    client_id: str,    # Used in Block 1 (Genesis)
    ...
) -> Dict[str, Any]:
    """
    Block 1 (Genesis) includes:
    - transaction_id
    - gateway_timestamp_utc
    - environment  ← Phase 2 canonical field
    - client_id    ← Phase 2 canonical field
    """
```

## Design Rationale

### Why Explicit Fields?

**Alternative considered:** Derive from deployment environment variables or auth context.

**Rejected because:**
1. Breaks offline verification (would need infrastructure context)
2. Creates implicit dependencies on deployment topology
3. Makes packets non-portable across environments
4. Complicates testing (can't simulate prod from dev)

**Chosen approach:**
- Explicit is better than implicit
- Self-contained packets are verifiable anywhere
- Clear separation between governance metadata and authentication

### Why Not Authenticated in Phase 2?

Authentication integration is a **separate concern** that requires:
- Token validation infrastructure
- Key management for token signing
- Revocation mechanisms
- Session management

Phase 2 focus is **governance and accountability**. Authentication will be layered in a future phase without changing the underlying packet structure.

## Enforcement

### Request Validation

Pydantic enforces the contract at ingestion:

```python
# This request is ACCEPTED
{"environment": "prod", "client_id": "app-1", ...}

# This request is REJECTED (400 Bad Request)
{"environment": "production", "client_id": "app-1", ...}
# Error: environment must be one of: prod, staging, dev

# This request is REJECTED (422 Unprocessable Entity)
{"client_id": "app-1", ...}
# Error: field 'environment' required
```

### Verification Enforcement

The `/v1/transactions/{id}/verify` endpoint:

1. Recomputes HALO chain from packet fields (including `environment` and `client_id`)
2. Compares recomputed `final_hash` to stored `final_hash`
3. Returns `valid: false` with error code `final_hash_mismatch` if tampering detected

## Stability Guarantee

This contract is **locked for Phase 2**:

- ✅ `environment` is a required `Literal["prod", "staging", "dev"]` field
- ✅ `client_id` is a required `str` field
- ✅ Both feed into HALO Block 1 (Genesis)
- ✅ Both are explicit request parameters (not derived)
- ✅ Neither is used for authentication in Phase 2

Any change to these guarantees requires:
- Protocol version bump
- Migration documentation
- Backward compatibility plan
- Team consensus

---

**Document Version:** 1.0  
**Last Updated:** 2026-02-18  
**Protocol Version:** Phase 2  
**Status:** Locked ✅
