

---

# ELI Sentinel

## Cryptographically Verifiable AI Governance Infrastructure

---

## Overview

**ELI Sentinel** is a protocol-backed AI governance gateway.

It intercepts AI model calls, enforces policy **before execution**, and emits a **tamper-evident, cryptographically signed accountability packet** that can be verified **offline** without trusting Sentinel’s infrastructure.

This is not a logging tool.
This is not an observability platform.
This is a **black-box recorder for AI decisions**.

If a court, regulator, auditor, or insurer asks:

> “Prove that this AI call followed approved governance at the time it executed.”

ELI Sentinel produces a mathematically verifiable answer.

---

# Core Outcome

For every AI transaction:

1. Evaluate governance policy **pre-execution**
2. Allow or deny execution
3. Construct a deterministic **HALO chain**
4. Sign a canonical message with a cryptographic key
5. Persist a self-contained accountability packet
6. Enable independent offline verification

---

# System Capabilities

## 1. Pre-Execution Policy Enforcement

Policies are evaluated **before** the model is contacted.

Checks may include:

* Model allowlist
* Feature-specific constraints (e.g., billing requires temperature=0.0)
* Token ceilings
* Tool permissions
* Network access controls
* Environment rules (dev/staging/prod)

Denied calls never reach the provider.

---

## 2. HALO Chain (Hash-Linked Accountability Ledger)

Each transaction produces a deterministic five-block hash chain:

1. Genesis
2. Intent
3. Inputs (hashes only)
4. Policy + Model Snapshot
5. Output (or Denial)

Each block hashes the previous block’s hash plus canonicalized payload.

Any modification breaks verification.

---

## 3. Cryptographic Signing (Trust Anchor)

Each transaction signs a canonical message:

```json
{
  "transaction_id": "...",
  "gateway_timestamp_utc": "...",
  "final_hash": "...",
  "policy_version_hash": "...",
  "client_key_fingerprint": "..."
}
```

Signature algorithm:

* ECDSA_SHA_256 (preferred)
* or RSA-PSS-SHA256

Signing is pluggable:

* Local dev keys
* KMS (AWS/GCP/Azure)
* HSM integration (future)

Optional:

* RFC 3161 trusted timestamp

---

## 4. Accountability Packet

Each transaction emits a full packet containing:

* Identifiers and timestamps
* Intent + feature_tag
* Model fingerprint
* Parameter snapshot
* Prompt hash / RAG hash
* Policy receipt
* Execution summary
* HALO chain
* Verification bundle
* Data handling attestation
* Enforcement mode

The packet is self-contained and exportable as:

* JSON
* PDF (with embedded JSON)

---

## 5. Offline Verifier

A portable CLI tool verifies:

* Schema validity
* HALO chain integrity
* Signature authenticity
* Optional TSA timestamp
* Policy provenance

Verification does not require contacting Sentinel.

---

## 6. Policy Governance (SOX-Grade Minimal Model)

Policy changes follow:

* Proposer
* Approver
* proposer ≠ approver (prod enforced)
* Immutable policy versions
* Append-only change log
* Single mutable active pointer per environment

This supports:

* SOX 404
* SOC 2
* ISO 27001
* Litigation defensibility

---

## 7. Legal Hold

Allows freezing scoped transactions for:

* Litigation
* Regulatory review
* Discovery requests

Generates signed Legal Hold Certificate.

---

# Integration Modes

ELI Sentinel supports multiple integration patterns:

### API Gateway (Enforced Mode)

Sentinel calls provider directly.

### SDK Wrapper (Two-Phase)

* Preflight policy approval
* Client executes provider call
* Finalize with output hash

### Sidecar Proxy

Zero code change deployment.

### Orchestration Plugin

Langchain / LlamaIndex callback integration.

Each packet records `enforcement_mode`.

---

# Architectural Principles

These are non-negotiable:

* Deterministic canonicalization (`json_c14n_v1`)
* SHA-256 hashing
* Signature required in production
* Policy evaluated pre-execution
* Raw prompt/output storage disabled by default
* Packet must be self-contained
* Separation-of-duties enforced in code

If canonicalization drifts, verification collapses.

Protocol integrity is the product.

---

# What We Are NOT Building

* Hallucination scoring
* AI evaluation dashboards
* Observability analytics
* Blockchain anchoring
* Prompt storage by default
* Autonomous policy generation

ELI Sentinel governs structure, not semantics.

---

# Repository Structure (Planned)

```
eli-sentinel/
  gateway/
    app/
      services/
        c14n.py
        hashing.py
        halo.py
        signer.py
        policy_engine.py
        packet_builder.py
      routes/
      models/
  tools/
    eli_verify.py
  docs/
    openapi.yaml
    canonicalization.md
    verification.md
```

---

# Build Order (Strict)

1. json_c14n_v1 + test vectors
2. Hash utilities
3. HALO chain compute + verify
4. Signer interface + verification tests
5. Packet schema
6. Offline verifier CLI
7. Policy governance endpoints
8. `/v1/ai/call` end-to-end
9. JSON + PDF exports
10. Legal hold
11. Usage reporting

Protocol primitives before API sugar.

---

# Threat Model

ELI Sentinel defends against:

* Database tampering
* Backdated records
* Insider policy manipulation
* Log deletion
* Fabricated receipts
* Silent policy changes

If an attacker compromises the database but not the signing key,
they cannot forge valid packets.

---

# Quality Bar

This system must:

* Produce identical packets for identical inputs
* Verify offline without contacting Sentinel
* Prove policy executed before output
* Survive operator distrust
* Be explainable to an auditor in under 10 minutes

If asked:

> “Can this record be forged?”

The correct answer must be:

> “Only if you break SHA-256 or compromise the signing key.”

---

# Project Status

This repository is in active development.

Initial focus:

* Deterministic canonicalization
* HALO chain
* Signing + verification
* Offline verifier

UI and dashboards are explicitly out of scope.

---

## License

TBD

---

Once this is committed, Copilot will understand:

* This is a Python FastAPI protocol project
* Determinism is critical
* Cryptographic integrity is core
* Governance precedes execution



* The **`.github/copilot-instructions.md`** to lock Copilot into protocol-first mode
* Or the **first 3 foundational files (c14n.py, hashing.py, halo.py)** ready to paste next
