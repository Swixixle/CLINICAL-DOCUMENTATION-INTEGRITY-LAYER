# CDIL Deployment Guide

## Table of Contents
1. [Quick Start](#quick-start)
2. [Environment Variables](#environment-variables)
3. [Secrets Management](#secrets-management)
4. [Database Configuration](#database-configuration)
5. [TLS/HTTPS Configuration](#tlshttps-configuration)
6. [Key Rotation Procedures](#key-rotation-procedures)
7. [Logging & Monitoring](#logging--monitoring)
8. [PHI Handling](#phi-handling)
9. [High Availability & Scaling](#high-availability--scaling)
10. [Production Checklist](#production-checklist)

---

## Quick Start

### Local Development with Docker

```bash
# Clone repository
git clone https://github.com/Swixixle/CLINICAL-DOCUMENTATION-INTEGRITY-LAYER.git
cd CLINICAL-DOCUMENTATION-INTEGRITY-LAYER

# Build and run with Docker Compose
docker-compose up -d

# Check health
curl http://localhost:8000/healthz
```

### Building Docker Image

```bash
# Build image
docker build -t cdil-gateway:v1.0.0 .

# Run container
docker run -d \
  -p 8000:8000 \
  -e JWT_SECRET_KEY="your-secret-key" \
  -e CDIL_DB_PATH="/data/eli_sentinel.db" \
  -v cdil-data:/data \
  --name cdil-gateway \
  cdil-gateway:v1.0.0
```

---

## Environment Variables

### Required Variables

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `JWT_SECRET_KEY` | Secret key for JWT signing | (from secrets manager) | Yes |
| `CDIL_DB_PATH` | Path to SQLite database | `/data/eli_sentinel.db` | Yes |

### Optional Variables

| Variable | Description | Default | Production Recommendation |
|----------|-------------|---------|--------------------------|
| `JWT_ALGORITHM` | JWT algorithm | `HS256` | `RS256` (asymmetric) |
| `LOG_LEVEL` | Logging level | `INFO` | `INFO` (never `DEBUG`) |
| `LOG_FORMAT` | Log output format | `json` | `json` |
| `RATE_LIMIT_ENABLED` | Enable rate limiting | `true` | `true` |

### Example .env File (Development Only)

```bash
# DO NOT USE IN PRODUCTION
JWT_SECRET_KEY=dev-secret-key-change-in-production
JWT_ALGORITHM=HS256
CDIL_DB_PATH=/data/eli_sentinel.db
LOG_LEVEL=INFO
LOG_FORMAT=json
RATE_LIMIT_ENABLED=true
```

---

## Secrets Management

### ⚠️ CRITICAL: Never Use Hardcoded Secrets in Production

The dev secret key in the repository is **COMPROMISED**. Production deployments **MUST** use:

### AWS Secrets Manager

```bash
# Store JWT secret
aws secretsmanager create-secret \
  --name cdil/jwt-secret \
  --secret-string "$(openssl rand -base64 32)"

# Retrieve at runtime
export JWT_SECRET_KEY=$(aws secretsmanager get-secret-value \
  --secret-id cdil/jwt-secret \
  --query SecretString \
  --output text)
```

### Azure Key Vault

```bash
# Store JWT secret
az keyvault secret set \
  --vault-name cdil-keyvault \
  --name jwt-secret \
  --value "$(openssl rand -base64 32)"

# Retrieve at runtime
export JWT_SECRET_KEY=$(az keyvault secret show \
  --vault-name cdil-keyvault \
  --name jwt-secret \
  --query value -o tsv)
```

### GCP Secret Manager

```bash
# Store JWT secret
echo -n "$(openssl rand -base64 32)" | \
  gcloud secrets create cdil-jwt-secret --data-file=-

# Retrieve at runtime
export JWT_SECRET_KEY=$(gcloud secrets versions access latest \
  --secret=cdil-jwt-secret)
```

### Docker Secrets (Docker Swarm)

```bash
# Create secret
echo "$(openssl rand -base64 32)" | docker secret create cdil_jwt_secret -

# Use in docker-compose.yml
services:
  cdil-gateway:
    secrets:
      - cdil_jwt_secret
    environment:
      - JWT_SECRET_KEY_FILE=/run/secrets/cdil_jwt_secret

secrets:
  cdil_jwt_secret:
    external: true
```

---

## Database Configuration

### SQLite (Development/Small Deployments)

```bash
# Persistent volume for database
docker volume create cdil-data

# Mount in container
docker run -v cdil-data:/data \
  -e CDIL_DB_PATH=/data/eli_sentinel.db \
  cdil-gateway:latest
```

**Database File Permissions:**
```bash
# Ensure correct permissions
chmod 600 /data/eli_sentinel.db
chown cdil:cdil /data/eli_sentinel.db
```

### PostgreSQL (Production/Scale)

For production deployments with multiple instances, migrate to PostgreSQL:

1. Export data from SQLite
2. Set `DATABASE_URL` to the PostgreSQL DSN (e.g. `postgresql+psycopg2://cdil:cdil@host:5432/cdil`)
3. Run schema migrations: `alembic -c alembic.ini upgrade head`

The Docker image includes Alembic and its migration scripts. Run migrations before starting the application.

---

## TLS/HTTPS Configuration

CDIL Gateway runs HTTP internally. TLS termination should be handled by:

### Option 1: Reverse Proxy (Recommended)

Use Nginx or similar as a reverse proxy:

```nginx
# /etc/nginx/sites-available/cdil
server {
    listen 443 ssl http2;
    server_name api.cdil.example.com;

    # TLS Configuration
    ssl_certificate /etc/ssl/certs/cdil.crt;
    ssl_certificate_key /etc/ssl/private/cdil.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers on;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    # Proxy to CDIL Gateway
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health check (exempt from authentication)
    location /healthz {
        proxy_pass http://localhost:8000/healthz;
        access_log off;
    }
}
```

### Option 2: Cloud Load Balancer

**AWS Application Load Balancer:**
- Attach ACM certificate
- Forward to ECS/EKS target group
- Enable health checks on `/healthz`

**GCP Load Balancer:**
- Use Google-managed SSL certificate
- Backend service pointing to GKE pods
- Health check on `/healthz`

**Azure Application Gateway:**
- Use Azure-managed certificate
- Backend pool with AKS pods
- Health probe on `/healthz`

---

## Key Rotation Procedures

### JWT Secret Rotation

CDIL uses per-tenant signing keys, but JWT secrets still need rotation:

**Zero-Downtime Rotation Strategy:**

1. Generate new secret
2. Update secrets manager
3. Deploy with dual-key verification (old + new)
4. After grace period, remove old key

**Rotation Frequency:** Every 90 days

### Tenant Signing Key Rotation

Each tenant has their own ECDSA P-256 key pair:

```bash
# Future feature - key rotation will be handled via API
POST /v1/keys/rotate
{
  "tenant_id": "hospital-alpha",
  "key_id": "current-key-id"
}
```

**Rotation Triggers:**
- Every 90 days (routine)
- Immediately upon suspected compromise
- On tenant request

**Rollback:** Old keys are retained for verification of historical certificates.

---

## Logging & Monitoring

### Structured Logging

CDIL outputs JSON logs for easy aggregation:

```json
{
  "timestamp": "2026-02-19T00:00:00Z",
  "level": "INFO",
  "message": "Certificate issued",
  "tenant_id": "hospital-alpha",
  "certificate_id": "cert_01...",
  "request_id": "req_...",
  "user_id": "user_..."
}
```

### PHI Redaction

**Logs NEVER contain:**
- `note_text`
- `patient_reference`
- `human_reviewer_id`
- Request/response bodies
- Error stack traces with sensitive data

**Only hashes and IDs are logged.**

### Log Aggregation

**Recommended Tools:**
- **DataDog**: For APM and log aggregation
- **Splunk**: For compliance-heavy environments
- **ELK Stack**: For self-hosted deployments
- **CloudWatch Logs**: For AWS deployments

**Retention:** Minimum 90 days for audit compliance.

### Metrics to Monitor

| Metric | Threshold | Action |
|--------|-----------|--------|
| Certificate issuance rate | Baseline +/- 50% | Alert on anomaly |
| Verification failure rate | > 5% | Investigate key issues |
| HTTP 5xx errors | > 1% | Check application health |
| Response time (p95) | > 2 seconds | Scale up or optimize |
| Database connections | > 80% of limit | Scale database |
| Rate limit hits | Sustained high | Review limits or block abuse |

### Alerting

**Critical Alerts (Immediate Response):**
- Application down (health check fails)
- Database unreachable
- Verification failures spike (possible key compromise)
- Repeated 401/403 (potential brute force attack)

**Warning Alerts (Next Business Day):**
- High error rate (1-5%)
- Elevated response times
- Disk space < 20%

---

## PHI Handling

### CDIL's PHI Posture

**What CDIL Does:**
- ✅ Hashes note content (SHA-256)
- ✅ Hashes patient references
- ✅ Hashes reviewer IDs
- ✅ Stores only hashes, never plaintext PHI

**What CDIL Does NOT Do:**
- ❌ Store note_text in database
- ❌ Log PHI in application logs
- ❌ Transmit PHI to third parties
- ❌ Cache PHI in memory longer than request duration

### HIPAA Compliance

**Business Associate Agreement (BAA):**
- CDIL acts as a Business Associate if processing ePHI
- BAA required between CDIL operator and covered entity
- Standard HIPAA safeguards apply

**Audit Logging:**
- All access to certificates logged with user/tenant ID
- No PHI in logs
- Logs retained for 90+ days

### Data At Rest

**Encryption:**
- Database file should be on encrypted volume (AWS EBS encryption, Azure Disk Encryption, etc.)
- Backups must be encrypted
- Key material (tenant signing keys) stored encrypted in database

**Permissions:**
```bash
# Database file permissions
chmod 600 /data/eli_sentinel.db

# Only cdil user can access
chown cdil:cdil /data/eli_sentinel.db
```

### Data In Transit

**All API communication MUST use HTTPS:**
- TLS 1.2 minimum (TLS 1.3 preferred)
- No self-signed certificates in production
- Certificate from trusted CA (Let's Encrypt, DigiCert, etc.)

---

## High Availability & Scaling

### Horizontal Scaling

CDIL Gateway is stateless (except for database):

```yaml
# Kubernetes example
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cdil-gateway
spec:
  replicas: 3  # Scale out
  selector:
    matchLabels:
      app: cdil-gateway
  template:
    metadata:
      labels:
        app: cdil-gateway
    spec:
      containers:
      - name: cdil
        image: cdil-gateway:v1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: JWT_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: cdil-secrets
              key: jwt-secret
        - name: CDIL_DB_PATH
          value: /data/eli_sentinel.db
        volumeMounts:
        - name: data
          mountPath: /data
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 2000m
            memory: 4Gi
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: cdil-data-pvc
```

### Database Scaling

**Phase 1 (SQLite):**
- Single instance
- Persistent volume
- Regular backups

**Phase 2 (Future - PostgreSQL):**
- Primary-replica setup
- Read replicas for queries
- Connection pooling

### Load Balancing

**Health Check Configuration:**
```yaml
health_check:
  path: /healthz
  interval: 30s
  timeout: 5s
  healthy_threshold: 2
  unhealthy_threshold: 3
```

**Sticky Sessions:** Not required (CDIL is stateless)

### Auto-Scaling

**Metrics to scale on:**
- CPU utilization > 70%
- Request queue depth > 100
- Response time p95 > 2s

**Example (AWS ECS):**
```json
{
  "targetTrackingScalingPolicies": [{
    "predefinedMetricType": "ECSServiceAverageCPUUtilization",
    "targetValue": 70,
    "scaleInCooldown": 300,
    "scaleOutCooldown": 60
  }]
}
```

---

## Production Checklist

Before deploying to production, verify:

### Security
- [ ] JWT secret from secrets manager (not hardcoded)
- [ ] TLS certificate from trusted CA (not self-signed)
- [ ] Database file encrypted at rest
- [ ] Non-root user running container
- [ ] Rate limiting enabled
- [ ] Security headers configured (HSTS, X-Content-Type-Options, etc.)

### Infrastructure
- [ ] Health checks configured on load balancer
- [ ] Auto-scaling policies defined
- [ ] Monitoring and alerting set up
- [ ] Log aggregation configured
- [ ] Persistent volume for database
- [ ] Backup strategy implemented and tested

### Compliance
- [ ] Business Associate Agreement (BAA) signed if handling ePHI
- [ ] Audit logging enabled and retained for 90+ days
- [ ] PHI redaction verified in logs
- [ ] Incident response plan documented
- [ ] Disaster recovery procedures tested

### Testing
- [ ] Load testing completed (target: 100 concurrent users)
- [ ] Penetration testing by third party
- [ ] Backup restore tested
- [ ] Failover tested
- [ ] Key rotation tested

### Documentation
- [ ] Runbooks created for common operations
- [ ] On-call procedures documented
- [ ] Escalation contacts defined
- [ ] Customer notification templates prepared

---

## Support & Troubleshooting

### Common Issues

**Issue:** Health check fails
- **Cause:** Application not started or crashed
- **Resolution:** Check container logs: `docker logs cdil-gateway`

**Issue:** JWT verification fails
- **Cause:** Secret key mismatch or expired token
- **Resolution:** Verify `JWT_SECRET_KEY` matches token issuer

**Issue:** Database locked
- **Cause:** Multiple instances with SQLite
- **Resolution:** Use persistent volume or migrate to PostgreSQL

**Issue:** High memory usage
- **Cause:** Too many uvicorn workers
- **Resolution:** Adjust workers based on CPU cores (2x cores recommended)

### Debug Mode

**NEVER enable debug mode in production:**
```bash
# Development only
export LOG_LEVEL=DEBUG
```

Debug mode exposes stack traces and implementation details.

---

## Next Steps

1. Review [PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) for full checklist
2. Review [THREAT_MODEL_AND_TRUST_GUARANTEES.md](docs/THREAT_MODEL_AND_TRUST_GUARANTEES.md) for security architecture
3. Contact security team for production deployment approval

---

## Contact

**Security Incidents:** security@example.com  
**On-Call:** [PagerDuty/OpsGenie link]  
**Escalation:** [CTO/CISO contact]
