# Regulatory Defensibility Mapping

## How Clinical Decision Integrity Certificates Support Regulatory Compliance

---

## Executive Summary

Clinical Decision Integrity Certificates provide **tamper-evident proof** that AI governance executed before clinical recommendations. This artifact simplifies audit evidence for multiple regulatory frameworks without claiming certification or compliance.

**Target:** Healthcare IT directors, compliance officers, clinical informatics teams deploying AI in respiratory care and critical care workflows.

---

## 1. EU AI Act (High-Risk Medical AI Systems)

### Regulatory Requirement

The EU AI Act classifies medical AI systems as "high-risk" (Article 6, Annex III), requiring:

* **Article 9 - Risk Management Systems:** Continuous risk identification and mitigation
* **Article 10 - Data Governance:** Data quality, relevance, and representativeness
* **Article 11 - Technical Documentation:** Detailed description of system capabilities and limitations
* **Article 13 - Transparency:** Human oversight and interpretability
* **Article 14 - Human Oversight:** Ability for humans to intervene or override

### How Clinical Decision Certificates Help

| Requirement | Certificate Provides |
|-------------|---------------------|
| Technical Documentation | Immutable record of model version, parameters, and decision timestamp |
| Risk Management | Policy enforcement proof (was the model approved? were constraints followed?) |
| Human Oversight | Override flag and human decision attribution in certificate |
| Transparency | Complete HALO chain showing policy evaluation before execution |
| Audit Trail | Cryptographically signed, tamper-evident decision record |

### Audit Evidence Scenario

**Auditor asks:** "Prove this AI recommendation followed approved risk controls on March 15, 2026."

**Certificate provides:**
* Transaction ID: `01JC3X7...`
* Timestamp: `2026-03-15T14:32:10Z`
* Policy version hash: `sha256:abc123...`
* Policy decision: `approved`
* Model fingerprint: `sepsis-predictor-v2.1`
* Human override: `false`
* Signature: Valid (verified offline)

**Result:** Auditor can independently verify the decision chain without trusting Sentinel's infrastructure.

---

## 2. FDA Software as a Medical Device (SaMD)

### Regulatory Requirement

FDA guidance on SaMD (21 CFR Part 820, Digital Health Software Precertification) requires:

* **Algorithm Version Control:** Track which algorithm version made the decision
* **Performance Monitoring:** Detect algorithm drift or degradation
* **Change Management:** Document when algorithms are updated
* **Validation Evidence:** Demonstrate algorithm performed as intended

### How Clinical Decision Certificates Help

| FDA Expectation | Certificate Provides |
|-----------------|---------------------|
| Algorithm Traceability | Model fingerprint (name + version hash) in every certificate |
| Change Documentation | Policy version hash captures approved algorithm versions |
| Decision Attribution | Timestamp and transaction ID link certificate to clinical event |
| Validation Support | Certificates can be aggregated to demonstrate consistent policy enforcement |
| Post-Market Surveillance | Query certificates to identify which decisions used specific model versions |

### Audit Evidence Scenario

**FDA inspector asks:** "Show me all ventilator weaning recommendations made by algorithm v2.3 in Q1 2026."

**Certificate query provides:**
* Filter: `model_fingerprint = "vent-weaning-v2.3"` AND `timestamp >= 2026-01-01`
* Result: List of certificate IDs with timestamps, policy versions, and signatures
* Each certificate is independently verifiable

**Result:** Complete audit trail without exposing patient data (only decision hashes stored).

---

## 3. SOC 2 (Service Organization Control)

### Regulatory Requirement

SOC 2 Trust Services Criteria require:

* **CC6.1 - Logical Access Controls:** System restricts access to authorized users
* **CC6.8 - Change Management:** System tracks and approves changes
* **CC7.2 - System Monitoring:** System monitors for anomalies
* **CC8.1 - Change Control:** System enforces separation of duties

### How Clinical Decision Certificates Help

| SOC 2 Criterion | Certificate Provides |
|-----------------|---------------------|
| CC6.8 - Change Management | Policy version hash captures approved policy changes |
| CC8.1 - Separation of Duties | Policy approval workflow (proposer ≠ approver) enforced in code |
| CC7.2 - Monitoring | Every AI decision creates immutable certificate |
| Audit Logging | Complete HALO chain with cryptographic signature |
| Data Integrity | Tamper-evident hash chain prevents post-hoc modification |

### Audit Evidence Scenario

**Auditor asks:** "How do you ensure AI policy changes are approved before deployment?"

**Certificate shows:**
* Policy change ref: `policy-change-017`
* Policy proposer: `admin-user-1`
* Policy approver: `admin-user-2` (different user, enforced)
* Active policy version: `sha256:xyz789...`
* All subsequent certificates reference this policy version

**Result:** Demonstrates separation of duties and change control.

---

## 4. HIPAA (Health Insurance Portability and Accountability Act)

### Regulatory Requirement

HIPAA Security Rule (45 CFR §164.308, §164.312) requires:

* **§164.308(a)(1)(ii)(D) - Information System Activity Review:** Review records of system activity
* **§164.308(a)(5)(ii)(C) - Access Audit Controls:** Audit trail of access events
* **§164.312(b) - Audit Controls:** Record and examine activity
* **§164.312(c)(1) - Integrity Controls:** Protect data from improper alteration or destruction

### How Clinical Decision Certificates Help

| HIPAA Requirement | Certificate Provides |
|-------------------|---------------------|
| System Activity Review | Every AI decision logged with tamper-evident certificate |
| Audit Trail | HALO chain captures decision inputs, policy check, and output |
| Integrity Controls | Cryptographic signature prevents unauthorized modification |
| PHI Protection | Patient data is **hashed**, never stored in plain text |
| Access Controls | Policy enforcement proves only approved models/parameters were used |

### Privacy Protection

**Critical distinction:** Clinical Decision Certificates do **not** store PHI.

* Input data: `sha256:abcdef...` (hash only)
* Output data: Decision summary, not full patient record
* Certificate contains: Metadata about the decision, not patient identifiers

This means certificates can be:
* Shared with auditors without PHI exposure
* Stored in separate audit systems
* Retained for compliance timelines without PHI retention limits

### Audit Evidence Scenario

**HIPAA auditor asks:** "Show me audit logs for AI decisions in February 2026, without exposing PHI."

**Certificate provides:**
* Queryable metadata: timestamps, model versions, policy decisions
* No PHI: Only hashes of input data
* Verification: Each certificate independently verifiable

**Result:** Complete audit trail with PHI protection built in.

---

## 5. ISO 27001 (Information Security Management)

### Regulatory Requirement

ISO 27001 controls relevant to AI governance:

* **A.12.4.1 - Event Logging:** Log security-relevant events
* **A.12.4.3 - Administrator Logs:** Protect administrator activity logs
* **A.18.1.3 - Protection of Records:** Protect records from loss, destruction, falsification

### How Clinical Decision Certificates Help

| ISO 27001 Control | Certificate Provides |
|-------------------|---------------------|
| Event Logging | Every AI decision creates immutable event record |
| Log Protection | Cryptographic signature prevents log tampering |
| Record Protection | Certificates can be exported and stored in multiple locations |
| Integrity Verification | Offline verifier proves certificate authenticity |

---

## Comparison: Traditional Logging vs. Clinical Decision Certificates

| Capability | Traditional Logs | Clinical Decision Certificates |
|------------|-----------------|--------------------------------|
| Tamper-evident | ❌ Logs can be modified | ✅ Hash chain + signature prevents tampering |
| Offline verification | ❌ Must trust log infrastructure | ✅ Independent verification without trusting Sentinel |
| Policy enforcement proof | ❌ Logs show what happened, not that policy was enforced | ✅ Certificate proves policy evaluated **before** execution |
| Regulatory alignment | ⚠️ Logs are evidence, but not guaranteed tamper-proof | ✅ Cryptographic proof survives legal scrutiny |
| PHI protection | ⚠️ Logs may contain PHI | ✅ Only hashes stored, no PHI exposure |

---

## Integration Workflow: From AI Decision to Audit Evidence

```
Step 1: Clinical AI Request
  Input: Sepsis prediction model called with patient vitals (hashed)
  
Step 2: Policy Enforcement (Pre-Execution)
  Check: Is model approved? Are parameters valid?
  Decision: Approved or Denied
  
Step 3: HALO Chain Construction
  Block 1 (Genesis): Transaction ID, timestamp, environment
  Block 2 (Intent): Decision type (sepsis-alert)
  Block 3 (Inputs): Input data hash
  Block 4 (Policy): Policy version, model fingerprint, decision
  Block 5 (Output): Decision summary (alert or no-alert)
  
Step 4: Cryptographic Signing
  Sign: Final hash of HALO chain
  Result: Tamper-evident certificate
  
Step 5: Certificate Export
  Format: JSON (machine) or PDF (human)
  Storage: Can be stored in EHR, compliance system, or separate audit database
  
Step 6: Audit Verification (Future)
  Auditor: Runs eli_verify.py on certificate
  Result: Valid or Invalid (with reason)
  No trust required: Verification is offline and independent
```

---

## What We Are NOT Claiming

**We are not claiming:**
* ❌ That using ELI Sentinel makes you compliant
* ❌ That certificates replace legal counsel or compliance programs
* ❌ That certificates eliminate all regulatory risk
* ❌ That we are certified by FDA, EU, or any regulatory body

**We ARE claiming:**
* ✅ Certificates provide tamper-evident proof of governance execution
* ✅ This proof simplifies audit evidence collection
* ✅ Offline verification removes trust dependencies
* ✅ Hash-based design protects PHI while maintaining auditability

---

## Target Audience

This mapping is for:

* **Healthcare IT Directors** deploying AI in clinical workflows
* **Compliance Officers** managing SOC 2, HIPAA, EU AI Act audits
* **Clinical Informatics Teams** integrating AI into respiratory care protocols
* **Legal Teams** preparing for AI-related litigation or regulatory review
* **Audit Firms** validating AI governance controls

---

## Questions for Your Compliance Team

1. **When regulators ask "prove this AI decision followed approved protocols," what artifact do you provide today?**

2. **If your audit logs were tampered with, could you still prove governance executed?**

3. **Can you verify your AI governance trail offline, without trusting your logging infrastructure?**

4. **How do you balance HIPAA PHI protection with the need for detailed AI decision audit trails?**

If these questions expose gaps, Clinical Decision Certificates may be relevant to your regulatory defensibility strategy.

---

## Next Steps

### For Healthcare IT Teams
1. Review technical explainer: `docs/TECHNICAL_EXPLAINER.md`
2. Test certificate generation with demo: `docs/DEMO_GUIDE.md`
3. Discuss integration patterns with your clinical AI vendors

### For Compliance Officers
1. Share this document with audit partners
2. Map certificates to your current audit requirements
3. Pilot certificate generation with one AI workflow

### For Clinical Teams
1. Identify one AI-assisted workflow (sepsis alerts, vent weaning, ABG interpretation)
2. Document current governance controls
3. Evaluate whether certificates strengthen defensibility

---

## Document Metadata

* **Version:** 1.0
* **Last Updated:** 2026-02-18
* **Focus:** Respiratory care and critical care AI workflows
* **Regulatory Scope:** EU AI Act, FDA SaMD, SOC 2, HIPAA, ISO 27001
* **Status:** Guidance document (not legal advice)

---

**Disclaimer:** This document provides general guidance on how Clinical Decision Certificates relate to regulatory frameworks. It is not legal advice, compliance certification, or regulatory approval. Consult with qualified legal and compliance professionals for your specific situation.
