# Clinical Documentation Integrity Layer (CDIL)

CDIL issues cryptographically signed integrity certificates for AI-generated clinical notes at finalization.

---

## Certificate Issuance Policy

CDIL certificates are issued according to these requirements:

* **Certificate issued only for finalized notes** – Certificates are created when clinical documentation is complete and ready for commitment to the EHR
* **Issued before commit to EHR** – The certificate must be generated prior to storing the note in the Electronic Health Record
* **Immutable** – Once issued, certificates cannot be modified
* **No plaintext PHI** – Patient and clinical data are hashed; no plaintext Protected Health Information is stored in certificates
* **Verifiable offline** – Certificates can be verified independently without accessing CDIL infrastructure

---

## Architecture

```
┌─────────────┐
│   Clinician │
│  + AI Tool  │
└──────┬──────┘
       │ 1. Generate note
       │ 2. Human review
       │ 3. Finalize
       ▼
┌─────────────────────────────────────┐
│  Clinical Documentation             │
│  Integrity Layer (CDIL)             │
│                                     │
│  ┌───────────────────────────────┐ │
│  │ 1. Hash note content          │ │
│  │ 2. Hash patient reference     │ │
│  │ 3. Extend tenant chain        │ │
│  │ 4. Sign certificate           │ │
│  │ 5. Store certificate          │ │
│  │ 6. Return certificate ID      │ │
│  └───────────────────────────────┘ │
└──────────────┬──────────────────────┘
               │ Certificate issued
               ▼
        ┌─────────────┐
        │     EHR     │
        │  + Cert ID  │
        └─────────────┘
```

**6-Step Flow:**

1. **Note Generation** – AI system generates clinical documentation
2. **Human Review** – Clinician reviews and approves the note
3. **Finalization** – System calls CDIL to issue certificate
4. **Hash Computation** – CDIL hashes note content and patient identifiers
5. **Chain Extension** – Certificate is linked to tenant's integrity chain
6. **Signature** – Certificate is cryptographically signed and stored

---

## Integrity Chain

The **Integrity Chain** is a tamper-evident hash chain scoped to each tenant.

Each certificate references the hash of the previous certificate in the tenant's chain:

```
Cert 1 → hash₁
Cert 2 → hash₂ (includes hash₁)
Cert 3 → hash₃ (includes hash₂)
...
```

Any modification to a certificate breaks the chain, making tampering immediately detectable.

**Properties:**

* Sequential ordering of certificates within a tenant
* Cryptographic linkage between certificates
* Tamper-evident: changing any certificate invalidates all subsequent certificates
* Append-only: certificates cannot be inserted retroactively

---

## Multi-Tenant Architecture

CDIL provides complete tenant isolation:

### Tenant-Scoped Integrity Chain

* Each tenant maintains an independent integrity chain
* Certificates from different tenants never cross-reference
* Chain state is tracked per tenant_id
* No linkage between tenant chains

### Tenant-Scoped Signing Keys

* Each tenant has dedicated signing keys
* Keys are isolated in storage
* Optional: Customer Managed Keys (CMK) / Bring Your Own Key (BYOK) for enterprise deployments (future)

### Isolation Guarantees

* No cross-tenant data access
* No cross-tenant chain linkage
* No shared cryptographic material
* Tenant deletion cleanly removes all tenant data

---

## Certificate Example

```json
{
  "certificate_id": "01JCXM4K8N9P2R5T7V9W0X2Y4Z",
  "tenant_id": "hospital-west-wing",
  "timestamp": "2026-02-18T10:15:30Z",
  "model_version": "gpt-4-clinical-v2",
  "prompt_version": "soap-note-v1.2",
  "governance_policy_version": "clinical-v3.1",
  "note_hash": "a3f5d8e2b1c4...",
  "patient_hash": "7e9f2a1b8c3d...",
  "encounter_id": "enc-2026-02-18-001",
  "human_reviewed": true,
  "integrity_chain": {
    "previous_hash": "e8f3a9d1c2b4...",
    "chain_hash": "c5d2e9f1a8b3..."
  },
  "signature": {
    "key_id": "cdil-tenant-key-hospital-west-wing-2026",
    "algorithm": "ECDSA_SHA_256",
    "signature": "MEUCIQDx3fK..."
  }
}
```

**Note:** All PHI fields (note content, patient identifiers) are stored as cryptographic hashes only.

---

## Verification

### API Verification

```bash
curl -X POST https://cdil.example.com/v1/certificates/{certificate_id}/verify
```

Response:

```json
{
  "certificate_id": "01JCXM4K8N9P2R5T7V9W0X2Y4Z",
  "valid": true,
  "failures": []
}
```

### Offline Verification

Certificates can be verified without accessing CDIL infrastructure:

1. Recompute integrity chain from certificate fields
2. Verify cryptographic signature using public key
3. Check chain linkage (optional: verify against previous certificate)

Offline verification requires:

* The certificate (JSON)
* The tenant's public signing key (JWK)
* (Optional) Previous certificate for chain verification

---

## Security Properties

* **Tamper-evident** – Any modification to a certificate breaks cryptographic verification
* **Non-repudiation** – Signed certificates prove origin and cannot be forged without access to signing keys
* **Immutable** – Certificates cannot be edited after issuance
* **Offline verifiable** – Verification does not require trust in CDIL infrastructure
* **PHI protection** – No plaintext Protected Health Information in certificates
* **Tenant isolation** – Complete cryptographic and data separation between tenants
* **Audit trail** – Integrity chain provides chronological ordering of all certificates

---

## Non-Goals

CDIL does **not** provide:

* **Content validation** – CDIL does not assess clinical accuracy or quality of notes
* **EHR integration** – CDIL issues certificates; EHR systems must store and reference them
* **Access control** – CDIL does not enforce who can read notes (EHR responsibility)
* **Hallucination detection** – CDIL does not evaluate AI model output quality
* **Prompt storage** – Prompts are hashed, not stored in plaintext
* **Blockchain anchoring** – CDIL uses hash chains, not distributed ledgers

---

## Intended Users

* **Healthcare organizations** using AI-assisted clinical documentation
* **EHR vendors** integrating AI-generated content
* **AI medical scribe vendors** requiring documentation integrity
* **Compliance teams** needing audit trails for AI-generated clinical content
* **Legal/risk teams** requiring non-repudiable records of AI usage in clinical settings

---

## Summary

CDIL provides **durable, verifiable origin attestation** for AI-generated clinical documentation. By issuing cryptographically signed integrity certificates at note finalization, CDIL enables healthcare organizations to prove the provenance, integrity, and governance compliance of AI-generated content without storing Protected Health Information in plaintext.

Every certificate is:

* **Cryptographically signed** – proving origin and preventing forgery
* **Hash-chained** – detecting tampering across the certificate sequence
* **Tenant-isolated** – ensuring complete separation between organizations
* **Offline verifiable** – enabling independent audit without infrastructure access
* **PHI-safe** – storing only cryptographic hashes of sensitive data

CDIL transforms AI clinical documentation from "opaque output" to "verifiable, governed, auditable artifacts."
