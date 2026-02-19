# CDIL Tools

This directory contains utility scripts and tools for the Clinical Documentation Integrity Layer (CDIL).

## Smoke Tests

Smoke tests verify that the CDIL gateway can start successfully and respond to basic health checks. These tests should pass before any PR is merged.

### Local Smoke Test

Tests the gateway running directly with uvicorn (non-Docker mode).

```bash
./tools/smoke-test-local.sh
```

**What it does:**
1. Starts uvicorn server with the gateway app
2. Waits for server to be ready
3. Tests `/healthz` endpoint
4. Tests `/v1/health/status` endpoint
5. Tests root `/` endpoint
6. Cleans up test database and server process

**Requirements:**
- Python 3.12+
- All dependencies installed: `pip install -r requirements.txt`

### Docker Smoke Test

Tests the gateway running in a Docker container (production-like mode).

```bash
./tools/smoke-test-docker.sh
```

**What it does:**
1. Builds the Docker image from Dockerfile
2. Starts a container with test configuration
3. Waits for container to be healthy
4. Tests `/healthz` endpoint
5. Tests `/v1/health/status` endpoint
6. Tests root `/` endpoint
7. Checks Docker healthcheck status
8. Cleans up container

**Requirements:**
- Docker installed and running
- No other service using port 8000

## When to Run Smoke Tests

- **Before every PR**: Ensure basic functionality works
- **After dependency changes**: Verify nothing broke
- **After Docker changes**: Confirm container builds and runs
- **After import refactoring**: Check Python module paths work

## CI Integration

Smoke tests run automatically in GitHub Actions via `.github/workflows/smoke-test.yml`:
- On every push to main
- On every pull request
- Can be triggered manually via workflow_dispatch

## Troubleshooting

### Port 8000 already in use

```bash
# Find process using port 8000
lsof -ti:8000

# Kill the process (replace PID with actual process ID)
kill <PID>
```

### Docker build fails

```bash
# Check Docker is running
docker info

# Clean up old images
docker image prune -a
```

### Import errors

Make sure PYTHONPATH is set correctly:
```bash
export PYTHONPATH=/path/to/CLINICAL-DOCUMENTATION-INTEGRITY-LAYER
```

## Tenant Vault Initialization

The `init-tenant-vault.py` tool generates tenant-scoped RSA-4096 keypairs for signing and verification with encrypted private keys. **Now with explicit KDF parameters for institutional audit compliance.**

### Usage

```bash
# Generate a keypair for a tenant
TENANT_VAULT_PASSPHRASE="your-strong-passphrase-here" \
  python tools/init-tenant-vault.py --tenant acme-clinic

# Custom output directory
TENANT_VAULT_PASSPHRASE="your-strong-passphrase-here" \
  python tools/init-tenant-vault.py --tenant acme-clinic --out-dir /secure/path

# Force overwrite existing vault
TENANT_VAULT_PASSPHRASE="your-strong-passphrase-here" \
  python tools/init-tenant-vault.py --tenant acme-clinic --force
```

### Options

- `--tenant` (required): Tenant identifier (e.g., "acme-clinic")
- `--out-dir`: Base output directory (default: "tenant_vault")
- `--force`: Overwrite existing tenant vault directory
- `--env`: Passphrase environment variable name (default: "TENANT_VAULT_PASSPHRASE")

### What it Does

1. **Generates RSA-4096 keypair**: Strong cryptographic keys suitable for long-term use
2. **Encrypts private key**: Uses **explicit PBKDF2HMAC-SHA256 + AES-256-CBC** with 600,000 iterations (OWASP 2023 compliant)
3. **Documents KDF parameters**: Creates detailed cryptographic parameter log for institutional audits
4. **Creates tenant directory**: Output files are organized by tenant slug (normalized from tenant name)
5. **Sets secure permissions**: Private key gets 0600 permissions (owner read/write only)
6. **Generates readiness report**: Includes public key fingerprints, KDF parameters, and operational guidance

### Output Files

For a tenant named "acme-clinic", the tool creates:

```
tenant_vault/
└── acme-clinic/
    ├── tenant_private_key.pem    # Encrypted private key (0600 permissions)
    ├── tenant_public_key.pem     # Public key (0644 permissions)
    ├── readiness_report.txt      # System readiness report with key fingerprints
    └── kdf_parameters.txt        # Explicit KDF parameters for audit
```

### Audit-Optimal Features (NEW)

The tool now provides **explicit cryptographic parameters** for institutional audits:

- **Key Derivation Function**: PBKDF2HMAC with SHA-256
- **Iterations**: 600,000 (meets OWASP 2023 recommendations)
- **Encryption**: AES-256-CBC (FIPS 140-2 approved)
- **Salt**: 16 bytes cryptographically random (unique per key)
- **Documentation**: All parameters logged in `kdf_parameters.txt`

This makes the system defensible for FDA 21 CFR Part 11 and other regulatory audits where "implicit security" (e.g., `BestAvailableEncryption`) is harder to document.

### Security Notes

- **Passphrase**: Must be at least 16 characters (24+ recommended)
- **Storage**: Store the passphrase in a secrets manager, NOT in git or committed .env files
- **Private Key**: Treat as a regulated asset with access logging and least privilege
- **Key Rotation**: Rotate keys per tenant based on policy; retain old public keys for legacy signature validation
- **Git Protection**: The `tenant_vault/` directory is in .gitignore to prevent accidental key commits

### Requirements

- Python 3.12+
- `cryptography` library (included in requirements.txt)

---

## Ledger Integrity Verification

The `verify-ledger-integrity.sh` script cryptographically verifies the integrity of the audit event ledger. This is a **critical compliance tool for FDA 21 CFR Part 11** audit requirements.

### What it Verifies

1. **Hash Integrity**: Each audit event's hash matches its recomputed value
2. **Chain Linkage**: The hash chain is intact (prev_event_hash consistency)
3. **Tamper Detection**: No events have been modified or deleted

### Usage

```bash
# Verify entire ledger
./tools/verify-ledger-integrity.sh

# Verify specific database
./tools/verify-ledger-integrity.sh --db /path/to/production.db

# Verify single tenant only
./tools/verify-ledger-integrity.sh --tenant tenant_12345

# Verbose output (shows each event)
./tools/verify-ledger-integrity.sh --verbose

# JSON output (for automation)
./tools/verify-ledger-integrity.sh --json
```

### Options

- `--db PATH`: Path to SQLite database (default: `gateway/app/data/part11.db`)
- `--tenant ID`: Verify only specific tenant (default: all tenants)
- `--verbose`: Show detailed event-by-event verification
- `--json`: Output results as JSON for automation/integration

### Exit Codes

- **0**: Ledger integrity verified (no tampering detected)
- **1**: Ledger integrity FAILED (tampering detected)
- **2**: Database not found or inaccessible
- **3**: Invalid arguments

### Example Output

#### ✅ Valid Ledger
```
═══════════════════════════════════════════════════════════════
   ✓ LEDGER INTEGRITY VERIFIED
═══════════════════════════════════════════════════════════════

Total Events:     1,247
Verified Events:  1,247
Tenants:          3
Integrity Status: INTACT

No tampering detected. All audit events are cryptographically valid.

This ledger is defensible for regulatory audit.
```

#### ❌ Tampered Ledger
```
═══════════════════════════════════════════════════════════════
   ✗ LEDGER INTEGRITY VIOLATION DETECTED
═══════════════════════════════════════════════════════════════

Total Events:     1,247
Verified Events:  1,246
Tenants:          3
Errors Found:     1

⚠ WARNING: The audit ledger has been compromised.

Errors:
  1. Event: a630f753-bb8d-43...
     Error: Hash mismatch - event has been tampered with
     Time: 2026-02-19T10:55:50.485466Z

RECOMMENDED ACTIONS:
  1. Immediately secure the database and investigate unauthorized access
  2. Review system access logs for the timeframes of compromised events
  3. Notify your compliance officer and security team
  4. Restore from the last verified backup if available
  5. Document this incident per your breach response procedures
```

### When to Run

- **Before board presentations**: Prove audit trail integrity
- **During regulatory audits**: Demonstrate tamper-evidence
- **After security incidents**: Verify ledger hasn't been compromised
- **Scheduled checks**: Regular integrity validation (e.g., daily)
- **Before system handoff**: Verify integrity before transferring custody

### Automation Example

```bash
#!/bin/bash
# Daily integrity check with alerting

if ! ./tools/verify-ledger-integrity.sh --json > /tmp/integrity.json; then
  # Ledger compromised - send alert
  cat /tmp/integrity.json | mail -s "CRITICAL: Audit Ledger Tampered" security@example.com
  exit 1
fi

echo "Ledger integrity verified"
```

### CI Integration

The verification script can be added to your CI/CD pipeline:

```yaml
- name: Verify Audit Ledger Integrity
  run: |
    ./tools/verify-ledger-integrity.sh --db test.db
```

### Regulatory Compliance

This tool supports:
- **FDA 21 CFR Part 11**: Secure, tamper-evident audit trails
- **HIPAA**: Audit and accountability requirements
- **ISO 27001**: Event logging and monitoring
- **SOC 2**: System operation integrity

### Technical Details

The script uses cryptographic hash chaining:
- Each event includes `SHA-256(prev_hash || timestamp || object_type || object_id || action || payload)`
- Events are linked in a tamper-evident chain
- Any modification breaks the chain and is immediately detected

### Requirements

- Python 3.7+
- SQLite3
- Bash shell

---

## Other Tools

(Add documentation for other tools as they are added to this directory)
