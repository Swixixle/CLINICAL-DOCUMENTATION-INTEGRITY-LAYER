# Technical Explainer: Clinical Decision Integrity Certificates

## A 6-Page Technical Deep Dive for Healthcare IT Teams

---

## 1. Problem Statement: AI Decisions Lack Tamper-Evident Proof of Governance Execution

### The Scenario

A hospital deploys an AI system for sepsis prediction. The AI flags a patient for potential sepsis at 14:32 on March 15, 2026. The clinician sees the alert, reviews the data, and initiates the sepsis bundle protocol.

Six months later, a legal team asks:

> "Prove that this AI alert followed approved clinical protocols at the time it executed."

### What Traditional Systems Provide

**Database logs:**
```json
{
  "timestamp": "2026-03-15T14:32:10Z",
  "model": "sepsis-predictor-v2",
  "alert": "HIGH_RISK",
  "patient_id": "12345"
}
```

**Problems:**
* ❌ Logs can be modified after the fact (backdating, deletion)
* ❌ No proof that policy was checked **before** the alert fired
* ❌ No way to verify log integrity offline
* ❌ Trust depends on database administrator controls

### What Clinical Decision Certificates Provide

**Cryptographically signed certificate:**
```json
{
  "certificate_id": "01JC3X7...",
  "timestamp": "2026-03-15T14:32:10Z",
  "model_fingerprint": "sepsis-predictor-v2::sha256:abc123",
  "policy_decision": "approved",
  "policy_version_hash": "sha256:xyz789",
  "final_hash": "sha256:def456",
  "signature": "MEUCIQDx..."
}
```

**Advantages:**
* ✅ Tamper-evident: Changing any field breaks the hash chain
* ✅ Offline verifiable: No need to trust the database
* ✅ Proves pre-execution policy enforcement
* ✅ Cryptographically signed with private key

**Result:** If an auditor has the certificate and the public key, they can independently verify it was not tampered with.

---

## 2. Threat Model in Healthcare

### Threats We Defend Against

| Threat | Traditional Logging | Clinical Decision Certificates |
|--------|---------------------|--------------------------------|
| **Database Tampering** | Admin can modify logs | ✅ Hash chain breaks if tampered |
| **Backdated Records** | Timestamp can be changed | ✅ Timestamp in signed hash chain |
| **Log Deletion** | Logs can be deleted | ✅ Certificates can be stored externally |
| **Fabricated Decisions** | Difficult to detect forgery | ✅ Cannot forge signature without private key |
| **Silent Policy Changes** | Policy version not always captured | ✅ Policy version hash in every certificate |
| **Insider Manipulation** | Depends on access controls | ✅ Separation of duties enforced in policy approval |

### Threats We Do NOT Defend Against

* **Compromised Signing Key:** If attacker steals private key, they can forge certificates
* **AI Model Performance:** Certificates prove governance, not clinical outcomes
* **Clinical Judgment Errors:** Certificates don't validate medical decisions
* **Infrastructure Availability:** If Sentinel is down, no certificates are issued

### Security Posture

**Core principle:** If an attacker compromises the database but **not** the signing key, they cannot forge valid certificates.

**Why this matters:** In litigation or regulatory review, the certificate provides mathematically verifiable proof that survives database compromise.

---

## 3. Architecture: How Certificates Are Built

### Components

```
┌─────────────────────────────────────────────────────┐
│                Clinical AI System                    │
│          (Sepsis Predictor, Vent Advisor, etc.)     │
└──────────────────┬──────────────────────────────────┘
                   │ API Call
                   ▼
┌─────────────────────────────────────────────────────┐
│              ELI Sentinel Gateway                    │
│  ┌──────────────────────────────────────────────┐  │
│  │  1. Policy Engine                             │  │
│  │     - Check model allowlist                   │  │
│  │     - Validate parameters                     │  │
│  │     - Approve or Deny                         │  │
│  └──────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────┐  │
│  │  2. HALO Chain Builder                        │  │
│  │     - Build 5-block hash chain                │  │
│  │     - Each block hashes previous + payload    │  │
│  └──────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────┐  │
│  │  3. Cryptographic Signer                      │  │
│  │     - Sign final hash with private key        │  │
│  │     - ECDSA or RSA-PSS                        │  │
│  └──────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────┐  │
│  │  4. Certificate Builder                       │  │
│  │     - Assemble complete packet                │  │
│  │     - Include verification bundle             │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────┬───────────────────────────────────┘
                  │ Certificate
                  ▼
┌─────────────────────────────────────────────────────┐
│     Storage (Database, EHR, Audit System)           │
└─────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│         Offline Verifier (eli_verify.py)            │
│  - Recompute HALO chain                             │
│  - Verify signature                                 │
│  - No network required                              │
└─────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

**1. Pre-execution policy enforcement**
* Policy is checked **before** AI executes
* If denied, AI call never happens
* This is recorded in the certificate

**2. Deterministic canonicalization**
* Same inputs always produce same certificate
* JSON fields are sorted and formatted consistently
* Critical for reproducible verification

**3. Hash chaining (HALO)**
* Each block hashes the previous block's hash
* Like blockchain, but simpler and centralized
* Any modification breaks the chain

**4. Offline verification**
* Verifier only needs: certificate + public key
* No need to contact Sentinel
* Enables independent audit

---

## 4. HALO Chain: The Tamper-Evident Core

### What is HALO?

**HALO = Hash-Linked Accountability Ledger Ordered**

A deterministic, five-block hash chain that captures every step of the AI decision.

### Block Structure

```
Block 1: Genesis
{
  "block": 1,
  "label": "genesis",
  "prev_hash": null,
  "payload": {
    "transaction_id": "01JC3X7...",
    "timestamp": "2026-03-15T14:32:10Z",
    "environment": "prod",
    "client_id": "sepsis-monitor-v3"
  },
  "hash": "sha256:abc..."
}

Block 2: Intent
{
  "block": 2,
  "label": "intent",
  "prev_hash": "sha256:abc...",
  "payload": {
    "intent_manifest": "clinical-alert-sepsis",
    "feature_tag": "sepsis-prediction",
    "user_ref": "clinician-001"
  },
  "hash": "sha256:def..."
}

Block 3: Inputs
{
  "block": 3,
  "label": "inputs",
  "prev_hash": "sha256:def...",
  "payload": {
    "prompt_hash": "sha256:patient-vitals-hash...",
    "rag_hash": null,
    "multimodal_hash": null
  },
  "hash": "sha256:ghi..."
}

Block 4: Policy + Model
{
  "block": 4,
  "label": "policy_and_model",
  "prev_hash": "sha256:ghi...",
  "payload": {
    "policy_version_hash": "sha256:policy-xyz...",
    "policy_decision": "approved",
    "model_fingerprint": "sepsis-predictor-v2::sha256:model-abc...",
    "param_snapshot": {"threshold": 0.85}
  },
  "hash": "sha256:jkl..."
}

Block 5: Output
{
  "block": 5,
  "label": "output",
  "prev_hash": "sha256:jkl...",
  "payload": {
    "execution_status": "completed",
    "decision_summary": "HIGH_RISK_ALERT",
    "override": false
  },
  "hash": "sha256:mno..."
}

Final Hash: sha256:mno...
```

### How Tamper-Evidence Works

**Example tampering attempt:**

An attacker tries to backdate the certificate from 14:32 to 14:00.

1. Attacker modifies `Block 1` timestamp: `"timestamp": "2026-03-15T14:00:00Z"`
2. Block 1 hash changes: `sha256:abc...` → `sha256:xyz...`
3. Block 2 references old `prev_hash: sha256:abc...` (now invalid)
4. Block 2 hash changes
5. Block 3 hash changes
6. Block 4 hash changes
7. Block 5 hash changes
8. **Final hash changes**
9. **Signature verification fails** (signature was for old final hash)

**Result:** Verifier detects tampering immediately.

### Why HALO Instead of Blockchain?

| Feature | Blockchain | HALO Chain |
|---------|-----------|-----------|
| Decentralization | Yes | No (centralized in Sentinel) |
| Consensus | Required | Not required |
| Complexity | High | Low |
| Verification Speed | Slow | Fast |
| Use Case | Trustless networks | Trusted audit trail |

**HALO is simpler and faster because we're not building a decentralized ledger. We're building a tamper-evident audit trail for a single system.**

---

## 5. Verification Process: How Auditors Validate Certificates

### Step 1: Obtain Certificate and Public Key

**Certificate:** JSON or PDF export from Sentinel  
**Public Key:** Obtained from Sentinel's public key endpoint or stored in audit system

### Step 2: Run Offline Verifier

```bash
python eli_verify.py certificate.json --public-key sentinel-public-key.pem
```

### Step 3: Verification Steps

The verifier performs these checks:

**1. Schema Validation**
* Is the JSON structure valid?
* Are all required fields present?

**2. HALO Chain Recomputation**
* Recompute hash for Block 1 from payload
* Verify Block 2's `prev_hash` matches Block 1's hash
* Recompute hash for Block 2
* Continue through all 5 blocks
* Verify `final_hash` matches Block 5's hash

**3. Signature Verification**
* Extract signature from certificate
* Extract signed message (transaction ID, timestamp, final hash, policy version)
* Verify signature using public key

**4. Policy Provenance Check**
* Verify `policy_version_hash` is in approved policy history
* Check that policy was active at decision timestamp

### Step 4: Verification Result

**Success:**
```json
{
  "valid": true,
  "certificate_id": "01JC3X7...",
  "verified_at": "2026-09-15T10:00:00Z",
  "checks_passed": [
    "schema_valid",
    "halo_chain_valid",
    "signature_valid",
    "policy_provenance_valid"
  ]
}
```

**Failure:**
```json
{
  "valid": false,
  "certificate_id": "01JC3X7...",
  "error": "final_hash_mismatch",
  "details": "Block 1 timestamp appears modified"
}
```

### Why Offline Verification Matters

**Scenario:** Sentinel's database is compromised, or the company goes out of business.

**Traditional audit trail:** Unusable (can't trust the logs)  
**Clinical Decision Certificates:** Still verifiable (certificates stored externally, verification is offline)

**This is critical for long-term regulatory defensibility.**

---

## 6. Integration Pattern: Middleware Wrapper

### Recommended Deployment

```python
from eli_sentinel import SentinelClient

# Initialize client
client = SentinelClient(
    api_url="https://sentinel.hospital.com",
    api_key="your-api-key"
)

# Clinical AI decision
response = client.clinical_decision(
    decision_type="sepsis-alert",
    model="sepsis-predictor-v2",
    patient_data_hash="sha256:patient-vitals-001",
    environment="prod",
    client_id="icu-monitor-system"
)

# Response contains:
# - ai_recommendation: The AI output
# - certificate: The signed certificate
# - certificate_id: Unique ID for audit trail
```

### What Happens Inside Sentinel

```
Step 1: Policy Check
  - Is "sepsis-predictor-v2" approved?
  - Are parameters valid?
  - Is environment "prod" allowed?
  Result: approved or denied

Step 2: HALO Chain Construction
  - Build 5 blocks
  - Hash each block
  - Link blocks with prev_hash

Step 3: Sign Certificate
  - Create canonical message
  - Sign with private key (ECDSA)

Step 4: Return Response
  - AI recommendation (if approved)
  - Complete certificate
  - Verification instructions
```

### PHI Protection

**Critical:** Patient data is **hashed**, never stored in plain text.

```python
# Before sending to Sentinel:
import hashlib
patient_data = {
    "heart_rate": 120,
    "bp": "90/60",
    "temp": 38.5
}
patient_data_json = json.dumps(patient_data, sort_keys=True)
patient_data_hash = hashlib.sha256(patient_data_json.encode()).hexdigest()

# Send only the hash to Sentinel
response = client.clinical_decision(
    decision_type="sepsis-alert",
    patient_data_hash=f"sha256:{patient_data_hash}",
    ...
)
```

**Result:** Certificate proves governance was followed, without exposing PHI.

---

## Sample Certificate Artifact

```json
{
  "certificate_id": "01JC3X7ABCDEFGH",
  "timestamp": "2026-03-15T14:32:10Z",
  "environment": "prod",
  "client_id": "icu-sepsis-monitor",
  
  "clinical_context": {
    "decision_type": "sepsis-alert",
    "feature_tag": "sepsis-prediction",
    "user_ref": "clinician-smith"
  },
  
  "model_info": {
    "model_fingerprint": "sepsis-predictor-v2::sha256:model-abc123",
    "param_snapshot": {
      "threshold": 0.85,
      "sensitivity": "high"
    }
  },
  
  "policy_receipt": {
    "policy_version_hash": "sha256:policy-xyz789",
    "policy_decision": "approved",
    "rules_applied": [
      "model_allowlist_check",
      "parameter_validation",
      "environment_prod_rules"
    ]
  },
  
  "decision_summary": {
    "status": "completed",
    "output": "HIGH_RISK_ALERT",
    "override": false
  },
  
  "halo_chain": {
    "version": "v1",
    "blocks": [ /* 5 blocks */ ],
    "final_hash": "sha256:final-hash-mno456"
  },
  
  "signature": {
    "algorithm": "ECDSA_SHA_256",
    "value": "MEUCIQDx7..."
  },
  
  "verification": {
    "instructions": "Run: python eli_verify.py certificate.json",
    "public_key_url": "https://sentinel.hospital.com/v1/keys/public"
  }
}
```

---

## Frequently Asked Questions

### Q1: Does this replace our EHR audit logs?

**No.** ELI Sentinel is a complementary layer that proves governance execution. EHR logs still capture clinical actions.

### Q2: What if the signing key is compromised?

**Risk:** Attacker could forge certificates.  
**Mitigation:** Use Hardware Security Module (HSM) for key storage, rotate keys regularly, implement key access logging.

### Q3: Can we integrate this with our existing AI vendor?

**Yes.** ELI Sentinel acts as middleware between your clinical system and the AI vendor. No changes required to the AI model.

### Q4: How long do certificates need to be retained?

**Depends on your regulatory requirements.** HIPAA requires 6 years, malpractice retention varies by state. Certificates are small (typically <10 KB) and can be archived indefinitely.

### Q5: What happens if ELI Sentinel goes down?

**During outage:** No certificates are issued.  
**After outage:** Existing certificates remain valid and verifiable offline.  
**Mitigation:** Deploy Sentinel with high availability, export certificates to external storage.

---

## Next Steps for Healthcare IT Teams

1. **Pilot with one AI workflow** (e.g., sepsis alerts)
2. **Generate test certificates** using demo environment
3. **Validate offline verification** with your audit team
4. **Map to regulatory requirements** using `REGULATORY_MAPPING.md`
5. **Discuss integration** with clinical AI vendors

---

## Document Metadata

* **Version:** 1.0
* **Last Updated:** 2026-02-18
* **Target Audience:** Healthcare IT architects, clinical informatics teams
* **Technical Level:** Intermediate (assumes familiarity with APIs, cryptography basics)
* **Focus:** Respiratory care AI workflows (sepsis, ventilator weaning, ABG interpretation)

---

**Questions or feedback?** Open an issue on GitHub or contact the ELI Sentinel team.
