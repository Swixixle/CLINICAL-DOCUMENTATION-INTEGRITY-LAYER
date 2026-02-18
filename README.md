
---

# ELI Sentinel — Clinical AI Documentation Integrity Layer

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

2. **Run the demo:**
   ```bash
   python tools/demo_clinical_flow.py
   ```

3. **Review artifacts:**
   - Check `/tmp/clinical_demo/` for generated certificates

---

**ELI Sentinel — Making AI clinical documentation auditably defensible.**
