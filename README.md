# Clinical Documentation Integrity Layer (CDIL)

> CDIL is a middleware service that issues cryptographically signed integrity certificates for AI-generated clinical documentation at the moment of finalization.
CDIL issues cryptographically signed integrity certificates for AI-generated clinical notes at finalization.

---

## Certificate Issuance Policy

A certificate is issued for **every finalized AI-generated clinical note**.

**Core principles:**

* Certificates are generated before the note is committed to the EHR.
* Certificates are immutable once issued.
* Certificates do not store plaintext PHI.
* Certificates are independently verifiable.

**Draft policy:**

* Draft notes are **not** certified.
* Only finalized notes receive certificates.
* Finalization triggers immediate certificate issuance.

---

## Risk Without CDIL

Hospitals deploying AI documentation risk being unable to demonstrate:

* Which model generated a note
* Which governance policies executed
* That the note was not modified post-generation
* That safety filters executed
* That human review occurred (if required)

**Exposure categories:**

* **Audit risk**: Cannot reconstruct model provenance during clinical audits
* **Litigation risk**: No tamper-evident record of AI-generated content
* **Regulatory risk**: Inability to prove compliance with AI governance requirements
* **Operational risk**: No verifiable chain of custody for clinical documentation
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

## Architecture

```
Clinician
    ↓
AI Documentation System
    ↓
CDIL
    ↓
EHR
```

**Flow:**

1. AI generates clinical note.
2. Governance metadata captured (model, policy version, parameters).
3. Final note content hashed.
4. Certificate generated and cryptographically signed.
5. CDIL returns certificate to AI Documentation System.
6. Note + certificate stored in EHR by AI Documentation System.

**Key properties:**
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

* Pre-finalization governance enforcement
* Tamper-evident hash chain
* Offline-verifiable signatures
* No PHI in certificate

---

## Certificate Structure Example

```json
{
  "certificate_id": "01936f8a-1234-7abc-9def-0123456789ab",
  "model_version": "gpt-4-2024-11-20",
  "prompt_version": "clinical-summary-v3",
  "governance_policy_version": "policy-2024-Q4-v2.1",
  "note_hash": "8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4",
  "patient_hash": "3fc9b689459d738f8c88a3a48aa9e33542016b7a4052e001aaa536fca74813cb",
  "encounter_id": "ENC-2024-001234",
  "timestamp": "2024-11-20T14:32:01Z",
  "human_reviewed": true,
  "signature": "MEUCIQDx8...",
  "chain_hash": "7d865e959b2466918c9863afca942d0fb89d7c9ac0c99bafc3749504ded97730"
}
```

**Field definitions:**

* `certificate_id`: Unique certificate identifier (UUIDv7)
* `model_version`: AI model identifier used to generate note
* `prompt_version`: Versioned prompt template identifier
* `governance_policy_version`: Active governance policy at finalization
* `note_hash`: SHA-256 hash of finalized note content
* `patient_hash`: SHA-256 hash of patient identifier (not plaintext)
* `encounter_id`: Clinical encounter reference (application-assigned identifier, not direct PHI)
* `timestamp`: Certificate issuance timestamp (ISO 8601 UTC)
* `human_reviewed`: Boolean flag indicating human review status
* `signature`: Cryptographic signature (ECDSA-SHA256)
* `chain_hash`: Hash chain linking to previous certificate

---

## Verification

Certificates can be verified via:

### API Verification

```
POST /v1/certificates/{certificate_id}/verify
```

Returns structured validation result including:

* Hash chain integrity
* Signature authenticity
* Policy version validity
* Timestamp verification

### Offline Verification

Certificates are self-contained and verifiable without CDIL database access.

**Offline verification validates:**

* Certificate schema compliance
* Hash chain recomputation
* Signature verification against public key
* Tamper detection

**Failure handling:**

* Tampering results in explicit failure responses
* Structured error codes identify specific validation failures
* No ambiguous "verification warning" states

---

## Security Properties

* **Tamper detection**: Hash chaining detects any post-issuance modification
* **Cryptographic signature enforcement**: All certificates digitally signed using ECDSA-SHA256
* **No plaintext PHI storage**: Patient identifiers hashed; no clinical content in certificate
* **Environment isolation**: Separate keys and policies per environment (prod/staging/dev)
* **Structured error codes**: Explicit failure types for debugging and audit
* **Governance metadata capture**: Model version, policy version, and parameters immutably recorded

---

## Non-Goals

CDIL is **not**:

* An EHR system
* An AI model or inference engine
* A logging dashboard or observability platform
* A compliance certification authority
* A blockchain or distributed ledger

CDIL provides certificate issuance and verification infrastructure. It does not replace clinical systems, regulatory compliance processes, or AI model governance.

---

## Intended Users

* **Hospitals** deploying AI documentation tools
* **Digital health vendors** integrating LLM-based clinical summarization
* **Clinical informatics teams** implementing AI governance
* **Compliance and risk officers** managing AI deployment oversight

---

## Implementation

**Technology stack:**

* Python 3.11+
* FastAPI web framework
* Deterministic canonicalization (json_c14n_v1)
* SHA-256 hashing
* ECDSA cryptographic signatures

**Key endpoints:**

* `POST /v1/clinical/finalize` - Finalize note and issue certificate
* `GET /v1/certificates/{certificate_id}` - Retrieve certificate
* `POST /v1/certificates/{certificate_id}/verify` - Verify certificate integrity

**Repository structure:**

```
gateway/
  app/
    services/
      c14n.py              # Deterministic canonicalization
      hashing.py           # SHA-256 utilities
      halo.py              # Hash chain construction
      signer.py            # Signature generation/verification
      policy_engine.py     # Governance policy evaluation
      packet_builder.py    # Certificate builder
    routes/
      ai.py                # AI request processing
      transactions.py      # Certificate retrieval/verification
    models/
      requests.py          # Request schemas
tools/
  eli_verify.py            # Offline verification CLI
```
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

# ELI Sentinel – Clinical AI Documentation Integrity Layer

## Cryptographically Verifiable Governance for AI-Generated Clinical Notes

---

## Overview

**ELI Sentinel** is a clinical documentation integrity middleware designed specifically for AI-generated clinical notes.

It sits between AI documentation systems and Electronic Health Records (EHRs), generating **tamper-evident integrity certificates** that prove governance execution and note integrity during audit, litigation, or regulatory review.

### The Problem We Solve

> **If this didn't exist, hospitals deploying AI documentation risk being unable to prove governance execution and note integrity during audit, litigation, or regulatory review.**

When AI systems generate clinical documentation, healthcare organizations need to demonstrate:
- Which AI model and version was used
- What governance policies were applied
- Whether human review occurred
- That the documentation hasn't been tampered with

ELI Sentinel provides a cryptographically verifiable answer to these questions.

---

## Architecture

```
┌─────────────────┐
│  AI Summarizer  │ (OpenAI, Anthropic, etc.)
│   (External)    │
└────────┬────────┘
         │
         │ Generated Note
         ▼
┌─────────────────────────────────────────┐
│         ELI Sentinel Middleware         │
│                                         │
│  • Hash clinical note (no PHI stored)  │
│  • Execute governance checks           │
│  • Generate HALO chain                 │
│  • Sign with cryptographic key         │
│  • Create integrity certificate        │
└────────┬──────────────┬─────────────────┘
         │              │
         │              │ Certificate
         │              ▼
         │     ┌────────────────────┐
         │     │ Certificate Store  │
         │     │  (Verifiable)      │
         │     └────────────────────┘
         │
         │ Note + Certificate ID
         ▼
┌─────────────────┐
│       EHR       │
│    (Destination) │
└─────────────────┘
```

**Key Flow:**
1. AI vendor generates clinical note
2. ELI Sentinel receives note and metadata
3. System hashes note (never stores raw PHI)
4. Governance checks executed (PHI filter, hallucination scan, bias filter)
5. HALO chain built (tamper-evident)
6. Certificate cryptographically signed
7. Certificate returned with verification URL
8. Note + certificate ID stored in EHR

---

## Core Features

### 1. **Clinical Documentation Integrity Certificates**

For every AI-generated clinical note, ELI Sentinel produces a certificate containing:

- **Certificate ID**: Unique identifier
- **Model Version**: Which AI model was used
- **Prompt Version**: Template version identifier
- **Governance Policy Version**: Which policies were enforced
- **Note Hash**: SHA-256 hash of clinical note (no plaintext storage)
- **Patient Hash**: SHA-256 hash of patient ID (no PHI)
- **Encounter ID**: Visit/encounter reference
- **Timestamp**: ISO 8601 UTC timestamp
- **Human Review Flag**: Whether a clinician reviewed the note
- **Governance Checks**: List of checks executed (PHI filter, hallucination scan, etc.)
- **Cryptographic Signature**: Tamper-evident proof
- **HALO Chain**: Deterministic hash chain for integrity

### 2. **Tamper-Evident Architecture**

Built on cryptographic primitives:

- **HALO Chain**: Hash-Linked Accountability Ledger
  - Each transaction produces a deterministic five-block hash chain
  - Any modification breaks verification
  - Each block hashes the previous block plus canonicalized payload

- **Cryptographic Signing**:
  - ECDSA_SHA_256 or RSA-PSS-SHA256
  - Signs canonical message with certificate details
  - Verification possible offline without server access

### 3. **No PHI Storage**

ELI Sentinel is designed for privacy compliance:

- ✅ Stores hashes only (SHA-256)
- ✅ Never stores raw clinical notes
- ✅ Never stores raw patient identifiers
- ✅ All verification via cryptographic proof

### 4. **Offline Verification**

Certificates can be verified without contacting ELI Sentinel:

```bash
python verify_clinical_certificate.py certificate.json
```

The verification script validates:
- HALO chain integrity
- Cryptographic signature authenticity
- Policy version consistency
- Timestamp validity

### 5. **PDF Certificates**

Generate official PDF certificates for compliance officers:

```bash
python certificate_pdf.py certificate.json output.pdf
```

Certificates include:
- All metadata (no PHI)
- Governance checks executed
- Cryptographic proof
- Verification instructions
- Professional formatting for audit trails

---

## API Endpoints

### Clinical Documentation Certificate Generation

**POST /v1/clinical/documentation**

## Closing Statement

> CDIL provides durable, verifiable origin attestation for AI-generated clinical documentation.
Generate an integrity certificate for an AI-generated clinical note.

**Request:**
```json
{
  "clinician_id": "DR-12345",
  "patient_id": "PATIENT-67890",
  "encounter_id": "ENC-2026-02-18-001",
  "ai_vendor": "openai",
  "model_version": "gpt-4-turbo",
  "prompt_version": "clinical-v1.2",
  "governance_policy_version": "CDOC-Policy-v1",
  "note_text": "Clinical note text here...",
  "human_reviewed": true,
  "human_editor_id": "DR-12345",
  "note_type": "progress_note",
  "environment": "prod"
}
```

**Response:**
```json
{
  "certificate_id": "01933e7a-8b2c-7d4e-9f1a-2b3c4d5e6f7a",
  "verification_url": "/v1/transactions/01933e7a-8b2c-7d4e-9f1a-2b3c4d5e6f7a/verify",
  "hash_prefix": "a3f5c2d1",
  "certificate": {
    "certificate_id": "01933e7a-8b2c-7d4e-9f1a-2b3c4d5e6f7a",
    "encounter_id": "ENC-2026-02-18-001",
    "model_version": "gpt-4-turbo",
    "prompt_version": "clinical-v1.2",
    "governance_policy_version": "CDOC-Policy-v1",
    "note_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "patient_hash": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    "timestamp": "2026-02-18T04:29:47.233Z",
    "human_reviewed": true,
    "signature": "...",
    "final_hash": "...",
    "governance_checks": [
      "phi_filter_executed",
      "hallucination_scan_executed",
      "bias_filter_executed"
    ]
  }
}
```

---

## What We Are NOT Doing

ELI Sentinel has a focused scope:

- ❌ Not replacing EHR systems
- ❌ Not building AI summarizers
- ❌ Not training AI models
- ❌ Not selling enterprise infrastructure
- ❌ Not claiming regulatory certification

We are:

> **Building the integrity envelope around AI-generated clinical documentation.**

---

## Installation

```bash
# Clone the repository
git clone https://github.com/Swixixle/ELI-SENTINEL.git
cd ELI-SENTINEL

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn gateway.app.main:app --reload
```

---

## Getting Started

### Quick Start

1. **Start the server:**
   ```bash
   uvicorn gateway.app.main:app --reload
   ```

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
2. **Run the demo:**
   ```bash
   python tools/demo_clinical_flow.py
   ```

3. **Review artifacts:**
   - Check `/tmp/clinical_demo/` for generated certificates

---

**ELI Sentinel – Making AI clinical documentation auditably defensible.**
