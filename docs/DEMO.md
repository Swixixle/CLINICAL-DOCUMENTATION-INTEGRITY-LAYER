# CDIL 60-Second Demo Script

This walkthrough shows the full integrity cycle: issue a certificate, download a defense bundle, verify offline, then tamper and watch it fail.

**Prerequisites:** Server running locally (see [Quickstart in README](../README.md#quickstart)) and a valid JWT token.

---

## Step 1 — Issue a Certificate (~10 seconds)

```bash
TOKEN="your-jwt-token"

curl -s -X POST http://localhost:8000/v1/clinical/documentation \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "note_text": "<placeholder note text — do not use real PHI in demos>",
    "model_version": "demo-model-v1",
    "patient_hash": "a3f9e2b1c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1"
  }'
```

**Expected response (abbreviated):**

```json
{
  "certificate_id": "01JXXXXXXXXXXXXX",
  "status": "issued",
  "note_hash": "sha256:...",
  "signature": { "algorithm": "ECDSA_SHA_256", "key_id": "...", "signature": "..." }
}
```

Save the `certificate_id` for the next steps.

---

## Step 2 — Download the Defense Bundle (~5 seconds)

```bash
CERT_ID="01JXXXXXXXXXXXXX"   # from step 1

curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/v1/certificates/$CERT_ID/defense-bundle" \
  -o bundle.zip

ls -lh bundle.zip
# Should show a non-empty ZIP file
```

The bundle contains:
- `certificate.json` — full provenance record
- `canonical_message.json` — the exact JSON that was signed
- `public_key.pem` — EC P-256 public key
- `verification_report.json` — verification status at time of export
- `README.txt` — offline verification instructions

---

## Step 3 — Verify Offline — Expected: PASS (~10 seconds)

```bash
python tools/verify_bundle.py bundle.zip
```

**Expected output (green):**

```
======================================================================
              DEFENSE BUNDLE VERIFICATION
======================================================================

[INFO] Bundle: bundle.zip
[INFO] Mode: OFFLINE (no network required)

...

======================================================================
                     VERIFICATION SUMMARY
======================================================================

======================================================================
         PASS - CERTIFICATE VALID AND UNMODIFIED
======================================================================

✓ All verification checks passed
✓ Certificate is cryptographically authentic
✓ Document has not been altered since certification
✓ Suitable for legal proceedings and expert testimony
```

Exit code: `0`

---

## Step 4 — Tamper with the Bundle and Re-verify — Expected: FAIL (~15 seconds)

```bash
# 1. Unzip the bundle
mkdir /tmp/tamper_test && cd /tmp/tamper_test
unzip /path/to/bundle.zip

# 2. Modify the canonical message (simulates document alteration)
python3 -c "
import json
with open('canonical_message.json') as f:
    msg = json.load(f)
# Alter the note_hash field (simulates changing the note content)
msg['note_hash'] = 'tampered_hash_value_0000000000000000000000000000000000000000000000'
with open('canonical_message.json', 'w') as f:
    json.dump(msg, f)
print('Tampered canonical_message.json')
"

# 3. Repack the ZIP
zip -r /tmp/tampered_bundle.zip .

# 4. Re-verify the tampered bundle
python tools/verify_bundle.py /tmp/tampered_bundle.zip
```

**Expected output (red):**

```
======================================================================
                     VERIFICATION SUMMARY
======================================================================

======================================================================
              FAIL - TAMPERING DETECTED
======================================================================

✗ One or more verification checks failed
✗ Document may be tampered, corrupted, or invalid
✗ DO NOT rely on this certificate for legal proceedings
```

Exit code: `1`

---

## Step 5 — Simulate Alteration via API (~5 seconds)

The API also has a built-in tamper demo for presentations:

```bash
curl -s -X POST http://localhost:8000/v1/defense/simulate-alteration \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"certificate_id\": \"$CERT_ID\",
    \"modified_note_text\": \"<placeholder altered content>\"
  }"
```

**Expected response:**

```json
{
  "tamper_detected": true,
  "reason": "NOTE_HASH_MISMATCH",
  "original_hash": "<original hash>",
  "modified_hash": "<hash of altered text>",
  "verification_failed": true,
  "summary": "Tampering detected! The note content has been altered since certification."
}
```

---

## Summary

| Step | Action | Result |
|---|---|---|
| 1 | Issue certificate | `certificate_id` returned, ECDSA P-256 signature created |
| 2 | Download defense bundle | ZIP with certificate, canonical message, public key |
| 3 | Verify offline (unmodified) | Exit 0 — PASS |
| 4 | Tamper + re-verify | Exit 1 — FAIL |
| 5 | API simulate-alteration | `tamper_detected: true`, `verification_failed: true` |

**Key talking point:** Steps 3 and 4 require **no internet, no API, no trust in CDIL**. Any party with the bundle and `python tools/verify_bundle.py` can independently verify integrity.

---

See also: [`docs/API.md`](API.md) for full endpoint reference.
