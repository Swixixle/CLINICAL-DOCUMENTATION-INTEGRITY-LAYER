# Clinical Decision Certificate Generator Demo

## Overview

This is a web-based demo for generating sample Clinical Decision Integrity Certificates. It simulates the certificate generation process that happens in the ELI Sentinel Gateway when AI-assisted clinical decisions are made.

## Purpose

This demo helps:
* Healthcare IT teams visualize what certificates look like
* Compliance officers understand the audit trail format
* Clinical teams see how decisions are documented
* Auditors understand the verification process

## How to Use

### Option 1: Open Directly in Browser

1. Open `certificate-generator.html` in any modern web browser
2. Adjust the parameters (decision type, model, policy version, etc.)
3. Click "Generate Certificate"
4. Download the JSON certificate
5. In production, this JSON can be verified with `python tools/eli_verify.py certificate.json`

### Option 2: Serve with Python

```bash
# From the demo directory
python -m http.server 8000

# Open in browser
# http://localhost:8000/certificate-generator.html
```

### Option 3: Integrate into FastAPI Gateway (Future)

The demo can be served as a static route from the ELI Sentinel Gateway:

```python
# In gateway/app/main.py
from fastapi.staticfiles import StaticFiles

app.mount("/demo", StaticFiles(directory="demo"), name="demo")
```

Then access at: `http://localhost:8000/demo/certificate-generator.html`

## Demo Features

### Input Parameters

* **Clinical Decision Type**: Sepsis alert, vent weaning, ABG interpretation, documentation summary
* **AI Model Name**: Configurable model identifier
* **Policy Version**: Clinical protocol version
* **Environment**: Production, staging, or development
* **Decision Summary**: Free-text description of AI recommendation
* **Human Override**: Checkbox to indicate clinician override
* **Clinician ID**: Optional identifier for the reviewing clinician

### Generated Certificate

The demo generates a sample certificate with:

* **Certificate ID**: Unique UUIDv7 identifier
* **Timestamp**: ISO 8601 UTC timestamp
* **Clinical Context**: Decision type and feature tag
* **Model Information**: Model name, fingerprint, parameters
* **Policy Receipt**: Policy version, decision, applied rules
* **Decision Summary**: AI output and override status
* **HALO Chain**: 5-block hash chain (simplified for demo)
* **Signature**: Simulated ECDSA signature
* **Verification Instructions**: How to verify offline

### Actions

* **Download JSON**: Save certificate as JSON file
* **Download PDF**: Placeholder for PDF export (not implemented in demo)

## Limitations

This is a **demo only**. Key differences from production:

| Feature | Demo | Production |
|---------|------|------------|
| Hash Function | Simple JavaScript hash (NOT secure) | SHA-256 cryptographic hash |
| Signature | Random string | Real ECDSA or RSA-PSS signature |
| Verification | Not verifiable | Verifiable with `eli_verify.py` |
| HALO Chain | Simplified 5-block structure | Full deterministic chain |
| Patient Data | Simulated hash | Real hash of patient data (PHI protected) |
| Policy Engine | Not connected | Real policy enforcement |

**Warning**: Do not use demo certificates for real clinical workflows or compliance audits. They are for illustration only.

## Use Cases

### For Healthcare IT Demos

1. Show the certificate to compliance teams
2. Explain how tamper-evidence works
3. Demonstrate offline verification concept
4. Discuss integration patterns

### For Sales/Marketing

1. Include screenshot in pitch decks
2. Share link in emails to prospects
3. Use as conversation starter
4. Walk through certificate structure in demos

### For Development/Testing

1. Generate sample certificates for testing
2. Understand certificate schema
3. Design integration patterns
4. Plan verification workflows

## Screenshots

The demo includes:
* Clean, modern UI with medical document styling
* Two-column layout: input form on left, certificate preview on right
* Purple gradient theme matching ELI Sentinel branding
* Responsive design for mobile/tablet/desktop

## Customization

To customize the demo for your organization:

1. **Branding**: Update colors in CSS (search for `#667eea` and `#764ba2`)
2. **Decision Types**: Modify the `decisionType` dropdown options
3. **Default Values**: Change placeholder text and default values
4. **Instructions**: Update verification instructions with your endpoints

## Integration with Production

To integrate this demo with the real ELI Sentinel Gateway:

1. Replace simulated hash/signature functions with API calls:
   ```javascript
   // Instead of generateHash(input)
   const response = await fetch('/v1/ai/call', {
       method: 'POST',
       body: JSON.stringify(requestData)
   });
   const certificate = await response.json();
   ```

2. Add authentication (API keys, OAuth)
3. Connect to real policy engine
4. Enable real PDF export
5. Implement actual verification endpoint

## Next Steps

### For Demo Enhancement
- [ ] Add PDF export using jsPDF library
- [ ] Add QR code for verification URL
- [ ] Implement certificate comparison (tamper detection demo)
- [ ] Add "verify certificate" mode

### For Production Integration
- [ ] Create FastAPI static route
- [ ] Add authentication layer
- [ ] Connect to real certificate generation API
- [ ] Implement server-side PDF rendering
- [ ] Add certificate search/retrieval interface

## Questions?

For questions about the demo or production deployment, see:
* `docs/TECHNICAL_EXPLAINER.md` - Technical deep dive
* `docs/REGULATORY_MAPPING.md` - Compliance use cases
* `README.md` - Project overview

---

**Demo Version**: 1.0  
**Last Updated**: 2026-02-18  
**Purpose**: Educational demo for healthcare AI governance  
**Status**: Demo only (not for production use)
