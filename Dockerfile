# Clinical Documentation Integrity Layer (CDIL) - Dockerfile
# 
# Production-ready Docker image for CDIL Gateway API
# Multi-stage build for minimal image size and security

# Stage 1: Builder
FROM python:3.12-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash cdil && \
    mkdir -p /data /app && \
    chown -R cdil:cdil /data /app

# Copy Python dependencies from builder
COPY --from=builder --chown=cdil:cdil /root/.local /home/cdil/.local

# Copy application code
COPY --chown=cdil:cdil gateway/ gateway/
COPY --chown=cdil:cdil tools/ tools/
COPY --chown=cdil:cdil requirements.txt .

# Set Python path to include local packages
ENV PATH=/home/cdil/.local/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    CDIL_DB_PATH=/data/eli_sentinel.db \
    LOG_LEVEL=INFO \
    LOG_FORMAT=json \
    RATE_LIMIT_ENABLED=true \
    UVICORN_WORKERS=4

# Switch to non-root user
USER cdil

# Expose port
EXPOSE 8000

# Health check (using stdlib only, no external dependencies)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/v1/health/status', timeout=5).read()"

# Run application with uvicorn
# Number of workers can be configured via UVICORN_WORKERS env var
CMD ["sh", "-c", "uvicorn gateway.app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-4}"]
