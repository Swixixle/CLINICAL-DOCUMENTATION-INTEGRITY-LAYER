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

## Other Tools

(Add documentation for other tools as they are added to this directory)
