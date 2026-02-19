# Running CDIL Gateway Without Docker

This guide explains how to run the Clinical Documentation Integrity Layer (CDIL) Gateway directly on your system without using Docker.

## Prerequisites

- Python 3.11 or 3.12
- pip (Python package manager)
- SQLite3 (usually included with Python)

## Quick Start

### 1. Install Dependencies

```bash
# Navigate to project directory
cd CLINICAL-DOCUMENTATION-INTEGRITY-LAYER

# Create a virtual environment (recommended)
python3 -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Set Environment Variables

Create a `.env` file in the project root (for development only):

```bash
# .env file (DO NOT USE IN PRODUCTION)
JWT_SECRET_KEY=dev-secret-key-change-in-production
JWT_ALGORITHM=HS256
CDIL_DB_PATH=./data/eli_sentinel.db
LOG_LEVEL=INFO
LOG_FORMAT=json
RATE_LIMIT_ENABLED=true
PYTHONPATH=.
```

Or export them directly:

```bash
export JWT_SECRET_KEY="dev-secret-key-change-in-production"
export CDIL_DB_PATH="./data/eli_sentinel.db"
export PYTHONPATH="$(pwd)"
```

### 3. Create Data Directory

```bash
mkdir -p data
```

### 4. Run the Application

Using uvicorn directly:

```bash
uvicorn gateway.app.main:app --host 0.0.0.0 --port 8000
```

With hot-reload for development:

```bash
uvicorn gateway.app.main:app --host 0.0.0.0 --port 8000 --reload
```

With multiple workers for production:

```bash
uvicorn gateway.app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 5. Verify the Application

Check health endpoint:

```bash
curl http://localhost:8000/v1/health/status
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2026-02-19T09:00:00Z",
  "version": "1.0.0"
}
```

## Development Mode

For active development with auto-reload:

```bash
# Set development environment
export ENV=development
export LOG_LEVEL=DEBUG
export DISABLE_RATE_LIMITS=1

# Run with reload
uvicorn gateway.app.main:app --reload --host 0.0.0.0 --port 8000
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=gateway --cov-report=html

# Run specific test file
pytest gateway/tests/test_api.py

# Run with verbose output
pytest -v
```

## Linting and Formatting

```bash
# Install dev dependencies
pip install black ruff

# Check code formatting
black --check gateway

# Format code
black gateway

# Run linter
ruff check gateway

# Auto-fix linting issues
ruff check --fix gateway
```

## Production Considerations

### ⚠️ Security

When running in production without Docker:

1. **Never use the development JWT secret** - Generate a secure random key:
   ```bash
   openssl rand -base64 32
   ```

2. **Use a secrets manager** - Store secrets in AWS Secrets Manager, HashiCorp Vault, or similar

3. **Run as non-root user** - Create a dedicated service account:
   ```bash
   sudo useradd -r -s /bin/false cdil
   sudo chown -R cdil:cdil /path/to/app
   ```

4. **Enable rate limiting** - Always set `RATE_LIMIT_ENABLED=true` in production

5. **Use a reverse proxy** - Put nginx or similar in front of uvicorn:
   ```nginx
   server {
       listen 443 ssl;
       server_name api.example.com;
       
       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

### Process Management

Use a process manager like systemd for production:

Create `/etc/systemd/system/cdil-gateway.service`:

```ini
[Unit]
Description=CDIL Gateway API
After=network.target

[Service]
Type=simple
User=cdil
Group=cdil
WorkingDirectory=/opt/cdil
Environment="PATH=/opt/cdil/venv/bin"
Environment="PYTHONPATH=/opt/cdil"
Environment="CDIL_DB_PATH=/var/lib/cdil/eli_sentinel.db"
Environment="LOG_LEVEL=INFO"
Environment="RATE_LIMIT_ENABLED=true"
ExecStart=/opt/cdil/venv/bin/uvicorn gateway.app.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cdil-gateway
sudo systemctl start cdil-gateway
sudo systemctl status cdil-gateway
```

### Database Management

Backup the SQLite database regularly:

```bash
# Create backup
sqlite3 data/eli_sentinel.db ".backup 'data/eli_sentinel_backup.db'"

# Or copy the file
cp data/eli_sentinel.db data/eli_sentinel_backup_$(date +%Y%m%d).db
```

### Monitoring

View logs:

```bash
# If using systemd
sudo journalctl -u cdil-gateway -f

# Or check application logs
tail -f logs/cdil.log
```

Monitor the health endpoint:

```bash
# Simple health check script
while true; do
  curl -s http://localhost:8000/v1/health/status | jq .
  sleep 30
done
```

## Troubleshooting

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000
# Or on Linux
sudo netstat -tlnp | grep 8000

# Kill the process
kill -9 <PID>
```

### Import Errors

Ensure PYTHONPATH is set correctly:

```bash
export PYTHONPATH="$(pwd)"
# Or add to .env file
```

### Database Locked

If you see "database is locked" errors:

```bash
# Check for zombie connections
lsof data/eli_sentinel.db

# Ensure only one instance is running
ps aux | grep uvicorn
```

### Permission Denied

```bash
# Fix file permissions
chmod -R u+rw data/
chown -R $(whoami) data/
```

## Performance Tuning

### Workers

For production, set workers based on CPU cores:

```bash
# Calculate optimal workers (2 * cores + 1)
export UVICORN_WORKERS=$(python3 -c "import os; print(2 * os.cpu_count() + 1)")
uvicorn gateway.app.main:app --workers $UVICORN_WORKERS
```

### Database

For better SQLite performance:

```python
# gateway/app/database.py should include:
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-64000;  # 64MB cache
```

## See Also

- [Deployment Guide](../DEPLOYMENT_GUIDE.md) - Full deployment documentation
- [README](../README.md) - Project overview and Docker setup
- [Testing Guide](../gateway/tests/README.md) - Testing documentation
