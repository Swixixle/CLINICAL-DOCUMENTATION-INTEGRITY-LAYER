# Clinical Documentation Integrity Layer (CDIL)

> CDIL is a middleware service that issues cryptographically signed integrity certificates for AI-generated clinical documentation at the moment of finalization.

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

---

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

---

## Closing Statement

> CDIL provides durable, verifiable origin attestation for AI-generated clinical documentation.
