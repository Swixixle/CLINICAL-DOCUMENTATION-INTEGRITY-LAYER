# CDIL Integrity Artifact Specification

## Version: 1.0
## Status: Draft
## Last Updated: 2026-02-18

This document defines the canonical formats for all integrity artifacts produced by the Clinical Documentation Integrity Layer (CDIL).

---

## Table of Contents

1. [Canonical Message Format](#canonical-message-format)
2. [Certificate Schema](#certificate-schema)
3. [Evidence Bundle Schema](#evidence-bundle-schema)
4. [Verification Process](#verification-process)
5. [Cryptographic Algorithms](#cryptographic-algorithms)
6. [Versioning and Compatibility](#versioning-and-compatibility)

---

## Canonical Message Format

The **canonical message** is the exact byte sequence that gets cryptographically signed. It must be deterministic and reproducible.

### Canonicalization Algorithm: `json_c14n_v1`

1. **Sort keys** recursively (all nested objects)
2. **No whitespace** between tokens
3. **UTF-8 encoding** for all strings
4. **IEEE 754 double precision** for numbers
5. **No trailing commas** in arrays or objects

### Example: Certificate Canonical Message

```json
{
  "certificate_id":"cert-019453c2-8f5a-7b2e-a123-456789abcdef",
  "chain_hash":"abc123def456...",
  "governance_policy_hash":"sha256:policy789...",
  "governance_policy_version":"CDOC-Policy-v1",
  "human_attested_at_utc":"2026-02-18T10:30:00Z",
  "human_reviewed":true,
  "human_reviewer_id_hash":"sha256:reviewer456...",
  "issued_at_utc":"2026-02-18T10:30:00Z",
  "key_id":"tenant-key-001",
  "model_name":"GPT-4-Turbo",
  "model_version":"gpt-4-turbo-2024-11",
  "nonce":"019453c2-8f5a-7b2e-a123-456789abcdef",
  "note_hash":"sha256:789012345678...",
  "prompt_version":"clinical-v1.2",
  "server_timestamp":"2026-02-18T10:30:00Z",
  "tenant_id":"hospital-alpha"
}
```

**Byte Representation**: After canonicalization, convert to UTF-8 bytes, then hash with SHA-256.

> **`patient_hash`** is stored in `certificate.json` but is **not** included in the canonical message and is therefore not directly signed.
>
> **`previous_hash`** is in `integrity_chain` but is **not** directly in the canonical message. It is indirectly protected via `chain_hash`: `previous_hash` is an input to `chain_hash`, and `chain_hash` IS signed.

### Fields in Canonical Message

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `certificate_id` | string | Yes | UUIDv7 certificate identifier |
| `chain_hash` | string | Yes | Hash linking to previous certificate (indirectly protects `previous_hash`) |
| `governance_policy_hash` | string | Yes | `sha256:<hex>` of governance policy version string |
| `governance_policy_version` | string | Yes | Policy version label |
| `human_attested_at_utc` | string \| null | Yes | ISO 8601 UTC timestamp of human attestation (null if not reviewed) |
| `human_reviewed` | boolean | Yes | Whether a human reviewer attested to this note |
| `human_reviewer_id_hash` | string \| null | Yes | `sha256:<hex>` of reviewer identifier (null if not reviewed) |
| `issued_at_utc` | string | Yes | ISO 8601 UTC issuance timestamp |
| `key_id` | string | Yes | Signing key identifier (added by signer) |
| `model_name` | string | Yes | AI model name |
| `model_version` | string | Yes | AI model version |
| `nonce` | string | Yes | UUIDv7 for replay protection (added by signer) |
| `note_hash` | string | Yes | `sha256:<hex>` of clinical note |
| `prompt_version` | string \| null | Yes | Prompt template version label |
| `server_timestamp` | string | Yes | Server-controlled timestamp (added by signer) |
| `tenant_id` | string | Yes | Tenant identifier (from JWT) |

**Security Constraints**:
- ❌ **NEVER** include plaintext PHI (note_text, patient_reference, reviewer_id)
- ✅ **ALWAYS** use hashes for PHI fields
- ✅ **ALWAYS** include nonce for replay protection
- ✅ **ALWAYS** use server_timestamp (never client-supplied)

### Indirectly Protected Fields

These fields are **not** in the canonical message but are protected through a signed value:

| Field | Protection Mechanism |
|-------|---------------------|
| `previous_hash` | Not in the canonical message, but is an input to `chain_hash`. Because `chain_hash` IS signed, any alteration of `previous_hash` breaks the signature. |

### Fields NOT Signed

| Field | Reason |
|-------|--------|
| `patient_hash` | Stored in `certificate.json` as a chain-of-custody reference, but not included in `canonical_message`. A post-issuance modification of `patient_hash` would not invalidate the signature. |
| Plaintext note content | Never stored or transmitted; only `note_hash` is kept. |
| Raw patient / reviewer identifiers | Never stored; only the caller-supplied hash is kept. |

---

## Certificate Schema

Full certificate structure including metadata, hashes, signatures, and integrity chains.

### Complete Certificate JSON

```json
{
  "certificate_id": "cert-019453c2-8f5a-7b2e-a123-456789abcdef",
  "tenant_id": "hospital-alpha",
  "timestamp": "2026-02-18T10:30:00Z",
  
  "finalized_at": "2026-02-18T10:30:00Z",
  "ehr_referenced_at": "2026-02-18T10:31:00Z",
  "ehr_commit_id": "ehr-commit-xyz789",
  
  "model_version": "gpt-4-turbo-2024-11",
  "model_id": "model-019453c0-0000-7000-8000-000000000001",
  "prompt_version": "clinical-v1.2",
  "governance_policy_version": "CDOC-Policy-v1",
  
  "policy_hash": "sha256:abc123def456...",
  "governance_summary": "Requires human review for diagnoses and medications. AI assists with documentation.",
  
  "note_hash": "sha256:789012345678...",
  "patient_hash": "sha256:patient123...",
  "reviewer_hash": "sha256:reviewer456...",
  
  "encounter_id": "ENC-2026-02-18-001",
  "human_reviewed": true,
  
  "attribution": {
    "ai_generated_pct": 60,
    "human_edited_pct": 40,
    "source_mix": {
      "ai": 60,
      "dictation": 20,
      "prior_note": 20
    }
  },
  
  "integrity_chain": {
    "previous_hash": "sha256:prev-cert-hash...",
    "chain_hash": "sha256:this-cert-chain-hash..."
  },
  
  "signature": {
    "key_id": "tenant-key-001",
    "algorithm": "ECDSA_SHA_256",
    "signature": "MEUCIQDabcd1234...base64...",
    "canonical_message": {
      "certificate_id": "cert-019453c2-8f5a-7b2e-a123-456789abcdef",
      "chain_hash": "sha256:this-cert-chain-hash...",
      "governance_policy_hash": "sha256:policy789...",
      "governance_policy_version": "CDOC-Policy-v1",
      "human_attested_at_utc": "2026-02-18T10:29:50Z",
      "human_reviewed": true,
      "human_reviewer_id_hash": "sha256:reviewer456...",
      "issued_at_utc": "2026-02-18T10:30:00Z",
      "key_id": "tenant-key-001",
      "model_name": "GPT-4-Turbo",
      "model_version": "gpt-4-turbo-2024-11",
      "nonce": "019453c2-8f5a-7b2e-a123-456789abcdef",
      "note_hash": "sha256:789012345678...",
      "prompt_version": "clinical-v1.2",
      "server_timestamp": "2026-02-18T10:30:00Z",
      "tenant_id": "hospital-alpha"
    }
  }
}
```

### Certificate Fields Reference

#### Core Identity
- `certificate_id`: UUIDv7 unique identifier
- `tenant_id`: Organization/hospital identifier (from JWT authentication)
- `timestamp`: Certificate issuance time (ISO 8601 UTC)

#### Timing Integrity
- `finalized_at`: When note was finalized and certificate issued
- `ehr_referenced_at`: (Optional) When EHR system referenced the note
- `ehr_commit_id`: (Optional) Opaque EHR reference (no PHI)

**Verification Rule**: `finalized_at` MUST be ≤ `ehr_referenced_at` (no backdating)

#### Governance Metadata
- `model_version`: AI model version (e.g., "gpt-4-turbo-2024-11")
- `model_id`: (Optional) Reference to registered model in vendor registry
- `prompt_version`: Prompt template version
- `governance_policy_version`: Policy identifier
- `policy_hash`: SHA-256 of policy document
- `governance_summary`: Human-readable policy description

#### Content Hashes (No PHI)
- `note_hash`: SHA-256 of clinical note plaintext (format: `sha256:<hex>`)
- `patient_hash`: (Optional) SHA-256 of patient reference
- `reviewer_hash`: (Optional) SHA-256 of reviewer identifier

#### Clinical Context
- `encounter_id`: (Optional) Encounter/visit identifier (assumed non-PHI)
- `human_reviewed`: Boolean indicating if clinician reviewed

#### Attribution (Phase 2)
- `attribution.ai_generated_pct`: Percentage AI-generated (0-100)
- `attribution.human_edited_pct`: Percentage human-edited (0-100)
- `attribution.source_mix`: Breakdown by source type (governance metadata only, no raw text)

#### Integrity Chain
- `integrity_chain.previous_hash`: Hash of previous certificate (null for first cert)
- `integrity_chain.chain_hash`: Hash of current certificate including linkage

**Chain Hash Computation**:
```
chain_hash = SHA256(
  certificate_id ||
  tenant_id ||
  timestamp ||
  note_hash ||
  model_version ||
  governance_policy_version ||
  previous_hash
)
```

#### Signature
- `signature.key_id`: Signing key identifier
- `signature.algorithm`: "ECDSA_SHA_256"
- `signature.signature`: Base64-encoded DER signature
- `signature.canonical_message`: Exact message that was signed

---

## Evidence Bundle Schema

Complete exportable package for legal/compliance use.

### Evidence Bundle JSON Structure

```json
{
  "bundle_version": "1.0",
  "generated_at": "2026-02-18T10:35:00Z",
  
  "certificate": {
    /* Full certificate object (see above) */
  },
  
  "metadata": {
    "certificate_id": "cert-019453c2-8f5a-7b2e-a123-456789abcdef",
    "tenant_id": "hospital-alpha",
    "issued_at": "2026-02-18T10:30:00Z",
    "key_id": "tenant-key-001",
    "algorithm": "ECDSA_SHA_256"
  },
  
  "hashes": {
    "note_hash": "sha256:789012345678...",
    "hash_algorithm": "SHA-256",
    "patient_hash": "sha256:patient123...",
    "reviewer_hash": "sha256:reviewer456..."
  },
  
  "model_info": {
    "model_id": "model-019453c0-0000-7000-8000-000000000001",
    "model_name": "GPT-4-Turbo",
    "model_version": "2024-11",
    "vendor_name": "OpenAI",
    "vendor_id": "vendor-001",
    "policy_hash": "sha256:abc123def456..."
  },
  
  "human_attestation": {
    "reviewed": true,
    "reviewer_hash": "sha256:reviewer456...",
    "review_timestamp": "2026-02-18T10:29:50Z"
  },
  
  "attribution": {
    "ai_generated_pct": 60,
    "human_edited_pct": 40,
    "source_mix": {
      "ai": 60,
      "dictation": 20,
      "prior_note": 20
    }
  },
  
  "verification": {
    "instructions": {
      "cli": "python verify_certificate_cli.py certificate.json",
      "api": "POST /v1/certificates/{id}/verify",
      "manual": "See README_VERIFICATION.txt"
    },
    "public_key": {
      "key_id": "tenant-key-001",
      "reference_url": "GET /v1/keys/tenant-key-001",
      "jwk": {
        /* Optional: Embed JWK for offline verification */
        "kty": "EC",
        "crv": "P-256",
        "x": "base64url...",
        "y": "base64url..."
      }
    }
  },
  
  "bundle_signature": {
    "signed_at": "2026-02-18T10:35:00Z",
    "bundle_hash": "sha256:bundle-content-hash...",
    "signature": "MEUCIQDbundle...base64..."
  }
}
```

### Evidence Bundle Contents (ZIP)

When exported as ZIP archive:

```
evidence_bundle_cert-019453c2.zip
├── certificate.json          # Full certificate
├── certificate.pdf           # Human-readable PDF
├── evidence_bundle.json      # Complete bundle (this schema)
├── verification_report.json  # Current verification result
└── README_VERIFICATION.txt   # Verification instructions
```

---

## Verification Process

### Online API Verification

**Endpoint**: `POST /v1/certificates/{certificate_id}/verify`

**Headers**:
```
Authorization: Bearer <JWT>
```

**Response**:
```json
{
  "valid": true,
  "status": "PASS",
  "summary": "Certificate passed all integrity checks",
  "checks": {
    "signature_valid": true,
    "chain_integrity": true,
    "timing_valid": true,
    "tenant_authorized": true,
    "policy_found": true
  },
  "timestamp": "2026-02-18T10:40:00Z"
}
```

### Offline CLI Verification

**Command**:
```bash
python verify_certificate_cli.py certificate.json
```

**Steps**:
1. Load certificate from JSON file
2. Extract `signature.canonical_message` and `signature.signature`
3. Load public key (from file or fetch from API)
4. Recompute canonical bytes: `json_c14n_v1(canonical_message)`
5. Verify ECDSA signature: `verify(public_key, canonical_bytes, signature)`
6. Check chain hash: Recompute and compare to `integrity_chain.chain_hash`
7. Check timing: Verify `finalized_at <= ehr_referenced_at` (if present)

**Exit Codes**:
- `0`: PASS (all checks passed)
- `1`: FAIL (one or more checks failed)

### Manual Verification (Advanced)

For auditors who want to manually verify without tools:

1. **Extract canonical message**:
   - Get `signature.canonical_message` from certificate
   
2. **Canonicalize**:
   - Sort all keys recursively
   - Remove whitespace
   - Encode as UTF-8 bytes
   
3. **Hash**:
   - `message_hash = SHA256(canonical_bytes)`
   
4. **Verify signature**:
   - Decode `signature.signature` from Base64
   - Use public key (P-256 curve) to verify signature over message_hash
   
5. **Verify chain linkage**:
   - Recompute chain_hash from certificate fields
   - Compare to stored `integrity_chain.chain_hash`
   - If mismatch, certificate has been tampered with

---

## Cryptographic Algorithms

### Digital Signature

- **Algorithm**: ECDSA (Elliptic Curve Digital Signature Algorithm)
- **Curve**: P-256 (secp256r1 / prime256v1)
- **Hash Function**: SHA-256
- **Encoding**: DER format, Base64-encoded

**Rationale**:
- NIST-approved (FIPS 186-4)
- Widely supported in healthcare PKI
- Smaller keys than RSA (256-bit vs 2048-bit)
- Fast verification on mobile devices

### Hashing

- **Algorithm**: SHA-256
- **Format**: `sha256:<64-char-hex>`

**Example**:
```
Input: "Patient presents with headache. Vital signs stable."
Output: "sha256:a1b2c3d4e5f6..."
```

### Key Format

**Private Key**: PEM-encoded PKCS#8

```
-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg...
-----END PRIVATE KEY-----
```

**Public Key**: JWK (JSON Web Key)

```json
{
  "kty": "EC",
  "crv": "P-256",
  "x": "base64url-encoded-x-coordinate",
  "y": "base64url-encoded-y-coordinate"
}
```

### Nonce Generation

- **Format**: UUIDv7 (time-ordered, globally unique)
- **Purpose**: Replay protection
- **Storage**: Recorded in `used_nonces` table per tenant
- **Validation**: Each nonce can only be used once per tenant

---

## Versioning and Compatibility

### Bundle Version

- **Current Version**: `1.0`
- **Version Field**: `bundle_version` in evidence bundle JSON

### Backward Compatibility Rules

1. **Additive Changes**: New fields can be added without version bump
2. **Field Removal**: Requires major version bump (e.g., 1.0 → 2.0)
3. **Field Rename**: Requires major version bump
4. **Algorithm Change**: Requires new `algorithm` value (e.g., "ECDSA_SHA_256" → "ECDSA_SHA_512")

### Certificate Format Evolution

| Version | Changes | Migration |
|---------|---------|-----------|
| 1.0 | Initial format | N/A |
| 1.1 (Phase 2) | Add `model_id`, `attribution` | Optional fields, backward compatible |
| 1.2 (Phase 4) | Add `commit_token` reference | Optional field, backward compatible |

### Verification Compatibility

- Old certificates MUST verify with new verifiers
- New certificates MAY fail with old verifiers if they check for required fields
- Verifiers SHOULD ignore unknown fields (forward compatibility)

---

## Security Considerations

### PHI Protection

❌ **NEVER include in canonical message or certificate**:
- Plaintext clinical note content
- Patient names, MRNs, dates of birth
- Reviewer names or credentials
- Encounter timestamps (if precise to second)

✅ **ALWAYS use hashes for**:
- `note_text` → `note_hash`
- `patient_reference` → `patient_hash`
- `human_reviewer_id` → `reviewer_hash`

### Replay Protection

- Every canonical message includes a `nonce` (UUIDv7)
- Server records nonces in `used_nonces` table
- Duplicate nonce causes signature rejection (replay attack detected)

### Chain Integrity

- Each certificate links to previous via `previous_hash`
- Inserting a certificate into the chain requires recomputing all subsequent chain hashes
- Impossible without tenant's private signing key

### Timing Integrity

- Server sets `finalized_at` (never client-supplied)
- Verification fails if `finalized_at > ehr_referenced_at` (backdating attempt)

### Cross-Tenant Isolation

- Tenant ID embedded in canonical message (signed)
- Verifier MUST check that request tenant matches certificate tenant
- Cross-tenant access returns 404 (no existence disclosure)

---

## Appendix: Example Implementations

### Python: Canonical Message Generation

```python
import json
import hashlib

def json_c14n_v1(obj):
    """Canonicalize JSON object to deterministic bytes."""
    canonical_str = json.dumps(obj, sort_keys=True, separators=(',', ':'))
    return canonical_str.encode('utf-8')

def sign_canonical_message(message_dict, private_key):
    """Sign a canonical message."""
    canonical_bytes = json_c14n_v1(message_dict)
    signature = private_key.sign(canonical_bytes, ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(signature).decode('utf-8')
```

### JavaScript: Evidence Bundle Verification

```javascript
async function verifyEvidenceBundle(bundle) {
  const { certificate, metadata, verification } = bundle;
  
  // 1. Extract canonical message and signature
  const canonicalMessage = certificate.signature.canonical_message;
  const signature = certificate.signature.signature;
  
  // 2. Fetch public key
  const publicKey = await fetchPublicKey(metadata.key_id);
  
  // 3. Canonicalize and verify
  const canonicalBytes = JSON.stringify(canonicalMessage, Object.keys(canonicalMessage).sort());
  const isValid = await crypto.subtle.verify(
    { name: "ECDSA", hash: "SHA-256" },
    publicKey,
    base64Decode(signature),
    new TextEncoder().encode(canonicalBytes)
  );
  
  return isValid;
}
```

---

## Questions or Feedback?

For clarifications on this specification:
- Open an issue in the CDIL repository
- Contact the CDIL architecture team
- Reference this document in integration discussions

**Specification Status**: Draft (Phase 0)
**Next Review**: After Phase 1 implementation
