# GitHub Copilot Instructions for CDIL

This file contains critical rules and guidelines for GitHub Copilot when working on this repository. **Always follow these instructions.**

## Repository Context

This is the **Clinical Documentation Integrity Layer (CDIL)** - a system for creating cryptographically signed integrity certificates for AI-generated clinical documentation. This project is subject to healthcare compliance requirements and must maintain strict security and privacy standards.

## Critical Rules

### 1. PHI Protection
- **NEVER** log, store, or output Protected Health Information (PHI) in:
  - Application logs
  - Error messages
  - Debug output
  - Test artifacts
  - Git commits
  - PR descriptions
- All patient identifiers must be hashed before storage
- Use generic error messages that don't leak request data

### 2. Import Consistency
- **ALWAYS** use `from gateway.app.*` for internal imports
- **NEVER** use `from app.*` (this causes Docker runtime failures)
- Verify PYTHONPATH is set correctly in all run configurations

### 3. Part 11 Compliance & Audit Trail
- The audit ledger is **append-only** - never delete or modify existing audit events
- All audit events must be hash-chained (each event references previous event hash)
- Signatures must be cryptographically verifiable
- **NEVER** claim "Part 11 compliant" unless verification passes
- Run `verify_ledger` command before claiming compliance

### 4. Testing & Quality

#### Required Before PR
- Run smoke tests: `./tools/smoke-test-local.sh` and `./tools/smoke-test-docker.sh`
- Run existing tests: `pytest`
- Verify health endpoints work: `/healthz` and `/v1/health/status`
- Check Docker build succeeds: `docker build -t cdil-gateway:test .`

#### Test Environment
- Set `ENV=TEST` to disable rate limiting in tests
- Set `DISABLE_RATE_LIMITS=1` as alternative
- Set `PYTHONPATH` to project root for local testing

### 5. Security Guidelines
- No hardcoded secrets (use environment variables)
- All API endpoints require JWT authentication (except health checks)
- Rate limiting must be enabled in production
- Database files must have secure permissions (0600)
- Enable WAL mode for SQLite in production

### 6. Code Changes
- Make **minimal, surgical changes** - don't refactor unrelated code
- Don't fix unrelated bugs or tests unless they block your task
- Follow existing code style and patterns
- Don't add comments unless they match existing style
- Update documentation only if directly related to changes

### 7. Package Layout
```
gateway/
├── app/              # Main application code
│   ├── main.py      # FastAPI app entry point
│   ├── routes/      # API endpoints
│   ├── services/    # Business logic
│   ├── db/          # Database operations
│   ├── models/      # Pydantic models
│   └── security/    # Auth/crypto
└── tests/           # Test suite
```

### 8. Health Endpoints
Two health endpoints must always work:
- `/healthz` - Simple boolean check
- `/v1/health/status` - Detailed status with service info

These are used by Docker healthchecks, load balancers, and monitoring.

### 9. Docker Requirements
- Multi-stage build for security
- Run as non-root user (cdil:cdil)
- Set PYTHONPATH=/app
- Healthcheck must succeed within 40 seconds
- Use uvicorn with 4 workers (configurable via UVICORN_WORKERS)

### 10. Database Operations
- Use connection context managers (`with get_connection() as conn`)
- Enable foreign keys: `PRAGMA foreign_keys = ON`
- Use WAL mode in production: `PRAGMA journal_mode = WAL`
- Hash patient references before storing
- Never store raw PHI

### 11. Error Handling
- Catch exceptions at API boundaries
- Return sanitized errors to clients
- Log full errors server-side with PHI redaction
- Use generic 500 errors for unexpected failures

### 12. Dependency Management
- Check GitHub Advisory Database before adding new dependencies
- Keep dependencies minimal
- Pin versions in requirements.txt
- Update only when necessary for security or features

## Common Pitfalls to Avoid

1. ❌ Using `from app.*` imports → ✅ Use `from gateway.app.*`
2. ❌ Hardcoding secrets → ✅ Use environment variables
3. ❌ Logging PHI → ✅ Hash or redact sensitive data
4. ❌ Modifying audit events → ✅ Append-only operations
5. ❌ Skipping smoke tests → ✅ Run before every PR
6. ❌ Removing existing tests → ✅ Keep all tests unless broken by your changes

## Quick Commands

```bash
# Run tests locally
PYTHONPATH=$PWD ENV=TEST DISABLE_RATE_LIMITS=1 pytest

# Run smoke tests
./tools/smoke-test-local.sh
./tools/smoke-test-docker.sh

# Start local server
PYTHONPATH=$PWD ENV=TEST uvicorn gateway.app.main:app --reload

# Build Docker image
docker build -t cdil-gateway:dev .

# Run Docker container
docker run -e JWT_SECRET_KEY=test -p 8000:8000 cdil-gateway:dev
```

## When Making Changes

1. Understand the existing code structure
2. Make minimal changes to fix the issue
3. Run relevant tests (not full suite initially)
4. Run smoke tests to verify basic functionality
5. Review security implications
6. Check for PHI leakage
7. Verify Part 11 compliance if touching audit/signature code
8. Update this file if you add new critical rules

---

**Remember**: This is healthcare software. When in doubt, prioritize security and compliance over convenience.
