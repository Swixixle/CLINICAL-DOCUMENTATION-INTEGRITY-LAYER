#!/bin/bash
# Smoke test for local (non-Docker) deployment
# Tests that the gateway starts correctly and responds to health checks

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== CDIL Gateway Smoke Test (Local Mode) ==="
echo "Project root: $PROJECT_ROOT"
echo ""

# Set environment variables
export PYTHONPATH="$PROJECT_ROOT"
export ENV=TEST
export DISABLE_RATE_LIMITS=1
export CDIL_DB_PATH=/tmp/smoke_test_cdil.db

# Clean up any existing test database
rm -f "$CDIL_DB_PATH"

# Start uvicorn in the background
echo "Starting uvicorn server..."
cd "$PROJECT_ROOT"
uvicorn gateway.app.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --timeout-keep-alive 5 \
    --timeout-graceful-shutdown 3 \
    > /tmp/smoke_test_uvicorn.log 2>&1 &
UVICORN_PID=$!

echo "Server PID: $UVICORN_PID"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Cleaning up..."
    if [ -n "$UVICORN_PID" ]; then
        kill "$UVICORN_PID" 2>/dev/null || true
        wait "$UVICORN_PID" 2>/dev/null || true
    fi
    rm -f "$CDIL_DB_PATH"
    rm -f /tmp/smoke_test_uvicorn.log
}

trap cleanup EXIT

# Wait for server to be ready
echo "Waiting for server to start..."
MAX_ATTEMPTS=30
ATTEMPT=0
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if curl -f -s http://127.0.0.1:8000/healthz > /dev/null 2>&1; then
        echo "Server is ready!"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    sleep 1
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "ERROR: Server failed to start within 30 seconds"
    echo "Server log:"
    cat /tmp/smoke_test_uvicorn.log
    exit 1
fi

# Test endpoints
echo ""
echo "Testing /healthz endpoint..."
RESPONSE=$(curl -f -s http://127.0.0.1:8000/healthz)
echo "Response: $RESPONSE"
if ! echo "$RESPONSE" | grep -q '"ok".*true'; then
    echo "ERROR: /healthz endpoint did not return expected response"
    exit 1
fi
echo "✓ /healthz endpoint OK"

echo ""
echo "Testing /v1/health/status endpoint..."
RESPONSE=$(curl -f -s http://127.0.0.1:8000/v1/health/status)
echo "Response: $RESPONSE"
if ! echo "$RESPONSE" | grep -q '"status".*"healthy"'; then
    echo "ERROR: /v1/health/status endpoint did not return expected response"
    exit 1
fi
echo "✓ /v1/health/status endpoint OK"

echo ""
echo "Testing root endpoint..."
RESPONSE=$(curl -f -s http://127.0.0.1:8000/)
echo "Response: $RESPONSE"
if ! echo "$RESPONSE" | grep -q '"service"'; then
    echo "ERROR: Root endpoint did not return expected response"
    exit 1
fi
echo "✓ Root endpoint OK"

echo ""
echo "=== All smoke tests passed! ==="
exit 0
