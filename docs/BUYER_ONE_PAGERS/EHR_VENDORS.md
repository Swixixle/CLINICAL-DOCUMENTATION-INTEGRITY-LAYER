# CDIL for EHR Vendors: Liability Firewall & Gatekeeper Mode

## The Problem

**EHRs are liable if unverified AI notes cause harm or billing fraud.**

- AI-generated note contains error → EHR committed it → Hospital sues EHR vendor
- Billing fraud from AI hallucination → CMS fines hospital → Hospital blames EHR
- Regulatory audit: "How do you ensure AI notes are reviewed?" → EHR has no answer
- Multi-vendor AI ecosystem → EHR can't track which model generated what

**Without CDIL**: You're the liability backstop for every AI vendor integrated with your EHR. High risk, limited upside.

---

## The Solution: Gatekeeper Mode

CDIL provides a **pre-commit verification gate** that ensures only verified, governed AI notes reach the medical record.

### What You Get

1. **Liability Firewall**
   - EHR checks certificate before committing note
   - Only verified notes with human review pass gate
   - Commit token proves EHR enforced verification
   - Audit trail: "We only accepted verified notes"

2. **Competitive Differentiation**
   - "Our EHR has built-in AI governance"
   - Enable multi-vendor AI without increased risk
   - Faster AI partnerships (vendors trust your gate)

3. **Regulatory Compliance**
   - Prove to CMS: "We enforce verification"
   - Evidence for Joint Commission audits
   - Documentation for legal defense

---

## Gatekeeper API Integration

### Pre-Commit Verification

```bash
# EHR workflow when clinician finalizes AI note:

# 1. Check if note has certificate
if note.has_certificate:
    certificate_id = note.certificate_id
else:
    # Reject: AI note without certificate
    return error("AI note must have integrity certificate")

# 2. Verify certificate via gatekeeper
POST /v1/gatekeeper/verify-and-authorize
Headers: Authorization: Bearer <ehr-gateway-jwt>
Body: {
    "certificate_id": certificate_id,
    "ehr_commit_id": generate_commit_id()  # Your internal ID
}

Response: {
    "authorized": true,  # or false
    "verification_passed": true,
    "verification_failures": [],  # If any
    "commit_token": "eyJhbGc...",  # Short-lived JWT
    "verified_at": "2026-02-18T10:30:00Z"
}

# 3. If authorized, commit note
if response.authorized:
    # Store commit token for audit trail
    db.store_commit_audit(
        commit_id=ehr_commit_id,
        certificate_id=certificate_id,
        commit_token=response.commit_token
    )
    
    # Commit note to EHR
    ehr.commit_note(note)
else:
    # Reject: Failed verification
    return error("Note failed integrity verification", 
                 failures=response.verification_failures)
```

### Commit Token Lifecycle

**Token Validity**: 5 minutes (prevents replay)
**Token Binding**: certificate_id + ehr_commit_id + tenant_id
**Token Proof**: "EHR committed only verified notes"

```bash
# Later: Auditor asks "Did you verify before committing?"
# You show commit token as proof

POST /v1/gatekeeper/verify-commit-token
Body: {"commit_token": "saved-token"}

Response: {
    "valid": true,
    "certificate_id": "...",
    "issued_at": "2026-02-18T10:30:00Z",
    "expires_at": "2026-02-18T10:35:00Z"
}
```

---

## Business Value

### Risk Reduction

**Scenario**: AI note contains harmful error, committed to EHR

**Without CDIL (Your Liability)**:
- Hospital: "Your EHR accepted an unverified AI note"
- Plaintiff's attorney: "EHR vendor enabled the harm"
- Your defense: "We trusted the AI vendor" (weak)

**With CDIL (Hospital's Liability)**:
- Hospital: "Your EHR..."
- Your defense: "We verified the certificate. Human review was marked 'true'. We have proof."
- Evidence: Commit token + certificate showing human_reviewed=true
- Outcome: Liability stays with hospital, not EHR

### Competitive Differentiation

**RFP Question**: "How does your EHR handle AI-generated documentation?"

**Competitor's Answer**:
- "We support AI integrations"
- "We have audit logs"
- "We trust our AI partners"

**Your Answer with CDIL**:
- "We have a built-in gatekeeper that verifies every AI note"
- "Only verified notes with proven human review reach the record"
- "We provide commit tokens for audit trail"
- "We enable safe multi-vendor AI ecosystems"

### Revenue Opportunities

**AI Partnership Revenue**:
- Charge AI vendors for gatekeeper API access: $10K-50K/year per vendor
- Charge hospitals for gatekeeper feature: $50K-200K/year per hospital
- **Value**: New revenue stream without building AI yourself

**Faster AI Adoption**:
- Hospitals adopt AI faster with gatekeeper safety net
- More AI integrations → More EHR utilization → Higher retention
- **Value**: Competitive moat via AI enablement

---

## Technical Integration

### Minimal Code Changes

**Your existing EHR commit path**:
```python
def commit_note(note):
    validate_note(note)
    db.insert(note)
    log_audit("note_committed")
```

**With CDIL gatekeeper**:
```python
def commit_note(note):
    validate_note(note)
    
    # Add gatekeeper check
    if note.is_ai_generated:
        if not note.certificate_id:
            raise Error("AI note requires certificate")
        
        gatekeeper_result = cdil.verify_and_authorize(
            certificate_id=note.certificate_id,
            ehr_commit_id=generate_commit_id()
        )
        
        if not gatekeeper_result.authorized:
            raise Error("Certificate verification failed")
        
        # Store commit token for audit
        db.store_commit_token(gatekeeper_result.commit_token)
    
    db.insert(note)
    log_audit("note_committed")
```

### Rollout Strategy

**Phase 1: Warn Mode (Month 1)**
- Check certificates, log results
- Don't block commits (yet)
- Build confidence in gatekeeper

**Phase 2: Block Mode (Month 2)**
- Enforce gatekeeper for new AI integrations
- Legacy integrations still pass
- Monitor failure rates

**Phase 3: Full Enforcement (Month 3)**
- All AI notes require verification
- Exception reporting to admins
- Audit trail complete

---

## Security & Compliance

### What Gatekeeper Checks

✅ **Certificate Exists** - AI note has integrity certificate  
✅ **Signature Valid** - Certificate cryptographically signed  
✅ **Timing Integrity** - Note finalized before EHR reference (no backdating)  
✅ **Chain Integrity** - Certificate linked to tenant's chain (no insertion)  
✅ **Model Authorized** - AI model in hospital's allowlist (Phase 3)

### What Gatekeeper Does NOT Check

❌ Clinical accuracy (not gatekeeper's job)  
❌ Medical necessity (clinician's judgment)  
❌ Coding correctness (billing team's role)

**Gatekeeper's Job**: Verify governance and integrity. Not clinical judgment.

### Audit Trail

**Auditor Question**: "How do you ensure AI notes are reviewed?"

**Your Evidence**:
1. Gatekeeper logs showing all verification checks
2. Commit tokens proving only verified notes were committed
3. Certificate query: "Show me all AI notes without human review" → zero results
4. Percentage of AI notes that passed/failed gatekeeper

---

## Multi-Vendor AI Ecosystem

### The Challenge

Hospital wants to use:
- Vendor A for ED notes
- Vendor B for surgery notes
- Vendor C for radiology reports

**Your Risk Without CDIL**: You're liable for all three vendors' mistakes.

**Your Protection With CDIL**: 
- Vendor A registers model in CDIL
- Vendor B registers model in CDIL
- Vendor C registers model in CDIL
- Hospital approves which models are allowed
- Your gatekeeper enforces: "Only approved models"

**Result**: You enable multi-vendor ecosystem without increased risk.

---

## ROI for EHR Vendors

### Risk Reduction (Insurance Value)

**Litigation Cost Avoidance**:
- Average settlement for EHR-related harm: $2-5M
- Probability without gatekeeper: 5-10% over 5 years
- Probability with gatekeeper: 1-2% over 5 years
- **Value**: $100K-250K annual risk reduction

### Revenue Opportunities

**Gatekeeper Feature Revenue**:
- Large health system (10,000 beds): $200K/year
- Mid-size hospital (500 beds): $50K/year
- AI vendor integration fee: $25K/year per vendor

**Volume Potential**:
- 100 hospitals × $50K avg = $5M annual revenue
- 20 AI vendors × $25K = $500K annual revenue
- **Total**: $5.5M new revenue stream

### Competitive Advantage

**Win Rate Impact**:
- RFP requirement: "Must support AI governance"
- You: "Built-in gatekeeper with audit trail"
- Competitor: "We support AI integrations" (generic)
- **Win Rate Lift**: 10-15% on AI-focused RFPs

---

## Implementation Timeline

### Week 1: API Integration
- Integrate gatekeeper API
- Test certificate verification
- Validate commit token workflow

### Week 2: Warn Mode
- Enable gatekeeper checks (log only)
- Monitor failure rates
- Tune verification thresholds

### Week 3: Pilot Deployment
- Deploy to 1-2 pilot hospitals
- Enable block mode for new AI integrations
- Collect feedback

### Week 4: General Availability
- Full rollout to customer base
- Sales enablement training
- Marketing launch: "AI governance built-in"

---

## Next Steps

1. **Technical Review** - Review [GENIE_ROADMAP.md](../GENIE_ROADMAP.md) and [INTEGRITY_ARTIFACT_SPEC.md](../INTEGRITY_ARTIFACT_SPEC.md)
2. **Sandbox Access** - Test gatekeeper API in dev environment
3. **Pilot Agreement** - 30-day pilot with 1-2 hospitals
4. **Partnership Discussion** - Revenue share model for gatekeeper feature

---

## Questions?

**"What if legitimate notes fail verification?"**  
Gatekeeper has manual override for admins. Emergency mode disables gate temporarily.

**"What about performance impact?"**  
API call adds <100ms to commit path. Async option available.

**"Do we have to change our data model?"**  
No. Just add certificate_id field to notes table and commit_token to audit log.

**"What if hospital doesn't use CDIL?"**  
Gatekeeper becomes optional feature. Charge premium for hospitals that want it.

**"How much does this cost us?"**  
Free to integrate. Revenue share on gatekeeper feature sales to hospitals.

---

**CDIL: Making EHRs the trusted gatekeeper for AI clinical documentation.**

*For technical integration guide, see [GENIE_ROADMAP.md](../GENIE_ROADMAP.md)*  
*For security architecture, see [THREAT_MODEL_AND_TRUST_GUARANTEES.md](../THREAT_MODEL_AND_TRUST_GUARANTEES.md)*
