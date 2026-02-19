# Clinical Documentation Integrity Layer (CDIL) - Dockerfile
# 
# Production-ready Docker image for CDIL Gateway API
# Includes security hardening and minimal attack surface

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY gateway/ ./gateway/
COPY tools/ ./tools/

# Create data directory for SQLite database
RUN mkdir -p /app/data && chmod 750 /app/data

# Create non-root user for security
RUN useradd -m -u 1000 cdil && \
    chown -R cdil:cdil /app

# Switch to non-root user
USER cdil

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    CDIL_DB_PATH=/app/data/cdil.db

# Health check (using stdlib only, no external dependencies)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/v1/health/status', timeout=5).read()"

# Run the application
CMD ["uvicorn", "gateway.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
