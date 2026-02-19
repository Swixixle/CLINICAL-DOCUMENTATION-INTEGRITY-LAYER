#!/bin/bash
# Smoke test for Docker deployment
# Tests that the gateway Docker image builds and runs correctly

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== CDIL Gateway Smoke Test (Docker Mode) ==="
echo "Project root: $PROJECT_ROOT"
echo ""

IMAGE_NAME="cdil-gateway:smoke-test"
CONTAINER_NAME="cdil-smoke-test"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Cleaning up..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
    # Note: Keeping the image for potential debugging
}

trap cleanup EXIT

# Build Docker image
echo "Building Docker image..."
cd "$PROJECT_ROOT"
docker build -t "$IMAGE_NAME" .

echo ""
echo "Docker image built successfully!"
echo ""

# Start container
echo "Starting Docker container..."
docker run -d \
    --name "$CONTAINER_NAME" \
    -e JWT_SECRET_KEY=test-secret-key-for-smoke-test \
    -e CDIL_DB_PATH=/data/smoke_test.db \
    -e ENV=TEST \
    -e DISABLE_RATE_LIMITS=1 \
    -p 8000:8000 \
    "$IMAGE_NAME"

# NOTE: The JWT_SECRET_KEY above is for testing only.
# NEVER use this value in production. Generate a secure secret with:
# openssl rand -base64 32

echo "Container started with name: $CONTAINER_NAME"

# Wait for container to be ready
echo "Waiting for container to be ready..."
MAX_ATTEMPTS=30
ATTEMPT=0
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if curl -f -s http://127.0.0.1:8000/healthz > /dev/null 2>&1; then
        echo "Container is ready!"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    sleep 1
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "ERROR: Container failed to become healthy within 30 seconds"
    echo "Container logs:"
    docker logs "$CONTAINER_NAME"
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
echo "Checking Docker healthcheck status..."
HEALTH_STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "no-healthcheck")
echo "Health status: $HEALTH_STATUS"
if [ "$HEALTH_STATUS" = "healthy" ] || [ "$HEALTH_STATUS" = "no-healthcheck" ]; then
    echo "✓ Docker health status OK"
else
    echo "⚠ Docker health status: $HEALTH_STATUS (this may be normal if healthcheck hasn't run yet)"
fi

echo ""
echo "=== All Docker smoke tests passed! ==="
exit 0
