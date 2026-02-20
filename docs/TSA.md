# CDIL Trusted Time (TSA) Design

> **Status: Roadmap — not yet implemented.** This document describes the intended design for RFC 3161 Trusted Timestamp Authority (TSA) integration. The env vars and verification steps below describe the planned behavior.

---

## Why Trusted Timestamps Matter

CDIL currently sets `issued_at_utc` using the server's own clock. This provides a reasonable time anchor for most use cases, but it has one limitation: the server clock is controlled by the operator. If an adversary controls the server, they could potentially issue a certificate with a backdated timestamp.

A **Trusted Timestamp Authority (TSA)** solves this by having an independent, trusted third party cryptographically attest to the time at which a digest was presented to them. This is defined by **RFC 3161** (Internet X.509 Public Key Infrastructure Time-Stamp Protocol).

**Important:** Only the SHA-256 digest of the certificate's canonical message is sent to the TSA — **no PHI, no note content, no patient data**.

---

## Mock vs. Real TSA

### Mock Mode (`TSA_MODE=mock`)

- A local stub generates a fake TSA token containing a timestamp from the server clock
- Used for **development, testing, and demos** where RFC 3161 round-trips are impractical
- **Does not provide a legally significant time anchor**
- The mock response is structurally identical to a real response for testing purposes
- Explicitly labeled `"tsa_mode": "mock"` in the certificate

### Real Mode (`TSA_MODE=real`)

- CDIL sends a `TimeStampRequest` (RFC 3161) containing the SHA-256 digest of the canonical message to the configured TSA endpoint
- The TSA returns a signed `TimeStampToken` (RFC 3161)
- The token is stored in the certificate and included in the defense bundle
- **Provides a legally significant, independently verifiable time anchor**
- The token can be validated against the TSA's public certificate chain (optional, see below)

---

## Planned Environment Variables

| Variable | Values | Default | Description |
|---|---|---|---|
| `TSA_ENABLED` | `true` / `false` | `false` | Enable TSA stamping at certificate issuance |
| `TSA_MODE` | `mock` / `real` | `mock` | Use local mock stub or real RFC 3161 endpoint |
| `TSA_REQUIRED` | `true` / `false` | `false` | If `true`, certificate issuance fails when TSA is unavailable |
| `TSA_URL` | URL string | (none) | RFC 3161 TSA endpoint URL (required when `TSA_MODE=real`) |
| `TSA_TIMEOUT_MS` | integer | `5000` | Request timeout in milliseconds |

**Example `.env` snippet (planned):**

```dotenv
TSA_ENABLED=true
TSA_MODE=real
TSA_REQUIRED=false
TSA_URL=https://freetsa.org/tsr
TSA_TIMEOUT_MS=5000
```

---

## What RFC 3161 Provides

When `TSA_MODE=real`, the TSA timestamp provides:

1. **Independent time attestation** — a trusted third party attests that the digest was presented at a specific time, independent of the CDIL server clock
2. **Cryptographic binding** — the TSA signs the digest; the token cannot be reused for a different digest
3. **Non-repudiation of time** — the issuing organization cannot later claim a different issuance time

RFC 3161 does **not** provide:
- Proof of what the document contains (only the digest is sent)
- Validation of the signing key's trust chain (that is a separate PKI concern)
- HIPAA compliance by itself

---

## What Is Verified Offline (Imprint Match)

When TSA is enabled, the offline verifier (`tools/verify_bundle.py`) will perform an additional check:

**TSA imprint match (check 5/5, when enabled):**

1. Extract the `TimeStampToken` from the defense bundle
2. Parse the `MessageImprint` field from the token
3. Recompute the SHA-256 digest of `canonical_message.json` (same as Check 1)
4. Compare: `token.MessageImprint.digest == SHA256(canonical_message_bytes)`
5. PASS if they match; FAIL if they do not

This check confirms that the TSA token was issued for *this specific canonical message* and not swapped from another certificate.

**What is NOT checked by default (optional):**

- TSA certificate chain validation against a trusted root (requires the TSA's root CA certificate to be present)
- TSA token signature validity (requires the TSA's signing certificate)

Full TSA PKI chain validation is planned as a follow-on feature. For most use cases, the imprint match is sufficient to detect token substitution.

---

## Where TSA Data Is Stored

When implemented, TSA data will appear in the certificate and defense bundle as follows:

**In `certificate.json`:**

```json
{
  "tsa": {
    "mode": "real",
    "enabled": true,
    "timestamp_token_b64": "<base64-encoded DER TimeStampToken>",
    "digest_algorithm": "SHA-256",
    "serial_number": "<TSA token serial>",
    "tsa_url": "https://freetsa.org/tsr",
    "stamped_at_utc": "2024-01-15T10:00:00Z"
  }
}
```

**In `canonical_message.json`** (the signed message will include):

```json
{
  "tsa_imprint_sha256": "<hex digest that was sent to TSA>"
}
```

**In `verification_report.json`:**

```json
{
  "tsa_check": {
    "enabled": true,
    "mode": "real",
    "imprint_match": true,
    "verified_at": "2024-01-15T10:01:00Z"
  }
}
```

---

## Design Choices

- **Only the digest is sent to the TSA** — zero PHI exposure
- **TSA failure is non-fatal by default** (`TSA_REQUIRED=false`) — certificate issuance succeeds even if TSA is unreachable, and the certificate is marked as lacking a TSA timestamp
- **Mock mode is explicit** — the certificate clearly labels `"tsa_mode": "mock"` so it cannot be confused with a real timestamp
- **Imprint match is sufficient for most use cases** — full PKI chain validation is optional and planned for later

---

See also:
- [`docs/SECURITY_SCOPE.md`](SECURITY_SCOPE.md) — full truth table
- [`tools/verify_bundle.py`](../tools/verify_bundle.py) — current offline verifier (TSA check to be added)
- [`README.md`](../README.md#trusted-time-tsa) — TSA section in main README
