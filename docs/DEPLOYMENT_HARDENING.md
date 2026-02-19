# CDIL Deployment Hardening Guide

This document provides security hardening guidelines for deploying the Clinical Documentation Integrity Layer (CDIL) in production environments.

## Table of Contents

1. [TLS Termination](#tls-termination)
2. [Key Rotation](#key-rotation)
3. [Logging and Redaction](#logging-and-redaction)
4. [Database Backup and Restore](#database-backup-and-restore)
5. [Hospital Network Deployment](#hospital-network-deployment)
6. [Security Checklist](#security-checklist)

---

## TLS Termination

CDIL should **never** be exposed directly to the internet without TLS. Always use a reverse proxy or load balancer for TLS termination.

### Option 1: Nginx Reverse Proxy

Create `/etc/nginx/sites-available/cdil`:

```nginx
server {
    listen 443 ssl http2;
    server_name cdil.yourhospital.org;

    # TLS configuration
    ssl_certificate /etc/ssl/certs/cdil.crt;
    ssl_certificate_key /etc/ssl/private/cdil.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Proxy to CDIL
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=cdil:10m rate=10r/s;
    limit_req zone=cdil burst=20 nodelay;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name cdil.yourhospital.org;
    return 301 https://$server_name$request_uri;
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/cdil /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Option 2: Cloud Load Balancer

**AWS Application Load Balancer (ALB):**

1. Create ALB with HTTPS listener (port 443)
2. Attach ACM certificate
3. Configure target group pointing to CDIL instances (port 8000)
4. Enable access logs to S3
5. Set up WAF rules for additional protection

**Azure Application Gateway:**

1. Create Application Gateway with HTTPS listener
2. Upload TLS certificate
3. Configure backend pool with CDIL instances
4. Enable Web Application Firewall (WAF)
5. Configure health probes: `/v1/health/status`

**Google Cloud Load Balancer:**

1. Create HTTPS load balancer
2. Upload certificate or use Google-managed certificate
3. Configure backend service with CDIL instances
4. Enable Cloud Armor for DDoS protection
5. Set up health check: `/v1/health/status`

### Option 3: Traefik (Docker/Kubernetes)

Add to `docker-compose.yml`:

```yaml
services:
  traefik:
    image: traefik:v2.10
    command:
      - "--api.insecure=false"
      - "--providers.docker=true"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.email=admin@yourhospital.org"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock:ro"
      - "./letsencrypt:/letsencrypt"

  cdil-gateway:
    # ... existing config ...
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.cdil.rule=Host(`cdil.yourhospital.org`)"
      - "traefik.http.routers.cdil.entrypoints=websecure"
      - "traefik.http.routers.cdil.tls.certresolver=letsencrypt"
```

---

## Key Rotation

Per-tenant cryptographic keys should be rotated periodically (recommended: every 90 days).

### Key Rotation Process

1. **Generate new key pair:**

```bash
# Generate new RSA key pair
openssl genrsa -out new_tenant_key.pem 2048
openssl rsa -in new_tenant_key.pem -pubout -out new_tenant_public.pem

# Convert to JWK format (use provided script)
python tools/convert_to_jwk.py new_tenant_key.pem > new_tenant_key.jwk
```

2. **Add new key to database:**

```bash
# Use CDIL API to add new key
curl -X POST https://cdil.yourhospital.org/v1/keys \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d @new_tenant_key.jwk
```

3. **Switch to new key:**

New certificates will automatically use the new key. Old certificates remain verifiable with their original keys.

4. **Archive old key (do NOT delete):**

Old keys must be retained for verification of historical certificates. Mark as `rotated` status:

```sql
UPDATE tenant_keys 
SET status = 'rotated' 
WHERE key_id = 'old-key-id';
```

5. **Test verification:**

Verify that old certificates still validate:

```bash
curl -X POST https://cdil.yourhospital.org/v1/certificates/{old-cert-id}/verify
```

### Key Rotation Schedule

| Environment | Rotation Frequency |
|-------------|-------------------|
| Development | 180 days |
| Staging | 90 days |
| Production | 90 days |
| High-security | 30 days |

---

## Logging and Redaction

CDIL must never log PHI in plaintext. All logging must include redaction.

### Log Redaction Rules

1. **Never log:**
   - `note_text` (full text)
   - `patient_reference` (before hashing)
   - `reviewer_name` (before hashing)
   - Request bodies containing PHI

2. **Always log (safe):**
   - Hashes (SHA-256 prefixes only: first 8 chars)
   - Request IDs
   - Timestamps
   - HTTP status codes
   - Tenant IDs
   - Error codes (without PHI details)

### Structured Logging Configuration

Add to your application configuration:

```python
import logging
import re

class PHIRedactionFilter(logging.Filter):
    """Filter that redacts potential PHI from log messages."""
    
    PHI_PATTERNS = [
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
        r'\b\d{10}\b',  # Phone numbers
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Emails
    ]
    
    def filter(self, record):
        # Redact PHI patterns
        message = record.getMessage()
        for pattern in self.PHI_PATTERNS:
            message = re.sub(pattern, '[REDACTED]', message)
        record.msg = message
        return True

# Apply filter
logging.getLogger().addFilter(PHIRedactionFilter())
```

### Log Aggregation

**ELK Stack (Elasticsearch, Logstash, Kibana):**

```yaml
# logstash.conf
input {
  file {
    path => "/var/log/cdil/*.log"
    type => "cdil"
  }
}

filter {
  # Drop lines containing potential PHI
  if [message] =~ /note_text|patient_reference/ {
    drop { }
  }
}

output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "cdil-logs-%{+YYYY.MM.dd}"
  }
}
```

**Splunk:**

```ini
# props.conf
[cdil]
SEDCMD-redact-phi = s/(\d{3}-\d{2}-\d{4})/[REDACTED-SSN]/g
SEDCMD-redact-email = s/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}/[REDACTED-EMAIL]/g
```

---

## Database Backup and Restore

The SQLite database contains all certificates, keys, and audit trails. **Backup is critical.**

### Automated Backup Script

Create `/usr/local/bin/cdil-backup.sh`:

```bash
#!/bin/bash
set -e

# Configuration
CDIL_DB="/app/data/cdil.db"
BACKUP_DIR="/backups/cdil"
RETENTION_DAYS=90
DATE=$(date +%Y%m%d-%H%M%S)

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup database (hot backup)
sqlite3 $CDIL_DB ".backup '$BACKUP_DIR/cdil-$DATE.db'"

# Compress backup
gzip "$BACKUP_DIR/cdil-$DATE.db"

# Verify backup integrity
gunzip -c "$BACKUP_DIR/cdil-$DATE.db.gz" | sqlite3 :memory: "PRAGMA integrity_check;"

# Remove old backups
find $BACKUP_DIR -name "cdil-*.db.gz" -mtime +$RETENTION_DAYS -delete

# Log success
echo "$(date): Backup completed successfully: cdil-$DATE.db.gz" >> /var/log/cdil-backup.log
```

Make executable and add to cron:

```bash
chmod +x /usr/local/bin/cdil-backup.sh

# Run daily at 2 AM
echo "0 2 * * * /usr/local/bin/cdil-backup.sh" | crontab -
```

### Docker Backup

```bash
# Backup from running container
docker-compose exec cdil-gateway sqlite3 /app/data/cdil.db ".backup /tmp/backup.db"
docker cp cdil-gateway:/tmp/backup.db ./backups/cdil-$(date +%Y%m%d).db

# Restore backup
docker cp ./backups/cdil-20240101.db cdil-gateway:/tmp/restore.db
docker-compose exec cdil-gateway sqlite3 /app/data/cdil.db ".restore /tmp/restore.db"
```

### Offsite Backup

**AWS S3:**

```bash
# Upload to S3 with encryption
aws s3 cp $BACKUP_DIR/cdil-$DATE.db.gz \
  s3://hospital-cdil-backups/ \
  --sse AES256
```

**Azure Blob Storage:**

```bash
# Upload to Azure
az storage blob upload \
  --account-name hospitalcdil \
  --container-name backups \
  --name cdil-$DATE.db.gz \
  --file $BACKUP_DIR/cdil-$DATE.db.gz
```

### Restore Procedure

1. **Stop CDIL service:**

```bash
docker-compose down
```

2. **Restore database:**

```bash
# Extract backup
gunzip backups/cdil-20240101.db.gz

# Replace current database
cp backups/cdil-20240101.db data/cdil.db
```

3. **Verify database integrity:**

```bash
sqlite3 data/cdil.db "PRAGMA integrity_check;"
```

4. **Start service:**

```bash
docker-compose up -d
```

5. **Verify service health:**

```bash
curl https://cdil.yourhospital.org/v1/health/status
```

---

## Hospital Network Deployment

Deploying CDIL in a hospital network requires careful consideration of network security, compliance, and integration.

### Network Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Internet                              │
└────────────────────┬────────────────────────────────────┘
                     │
            ┌────────▼────────┐
            │   Firewall      │
            │   (External)    │
            └────────┬────────┘
                     │
            ┌────────▼────────┐
            │   WAF / IDS     │
            │   (Optional)    │
            └────────┬────────┘
                     │
       ┌─────────────▼──────────────┐
       │     DMZ Network            │
       │  ┌──────────────────────┐  │
       │  │   Reverse Proxy      │  │
       │  │   (Nginx/Traefik)    │  │
       │  └──────────┬───────────┘  │
       └─────────────┼───────────────┘
                     │
            ┌────────▼────────┐
            │   Firewall      │
            │   (Internal)    │
            └────────┬────────┘
                     │
       ┌─────────────▼──────────────┐
       │  Application Network       │
       │  ┌──────────────────────┐  │
       │  │   CDIL Gateway       │  │
       │  │   (Docker)           │  │
       │  └──────────┬───────────┘  │
       │             │              │
       │  ┌──────────▼───────────┐  │
       │  │   Database Volume    │  │
       │  │   (Encrypted)        │  │
       │  └──────────────────────┘  │
       └────────────────────────────┘
```

### Firewall Rules

**External Firewall (DMZ):**

```bash
# Allow HTTPS inbound from internet
iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# Allow established connections
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Block all other inbound
iptables -A INPUT -j DROP
```

**Internal Firewall (Application Network):**

```bash
# Allow only reverse proxy to reach CDIL
iptables -A INPUT -s 10.0.1.10 -p tcp --dport 8000 -j ACCEPT

# Allow CDIL to reach internal services (if needed)
# iptables -A OUTPUT -d 10.0.2.0/24 -j ACCEPT

# Block all other traffic
iptables -A INPUT -j DROP
iptables -A OUTPUT -j DROP
```

### VLAN Segmentation

Place CDIL in a dedicated VLAN:

- **VLAN 100**: DMZ (Reverse Proxy)
- **VLAN 200**: Application (CDIL)
- **VLAN 300**: Database (if separate)
- **VLAN 400**: Management (SSH, monitoring)

### HIPAA Compliance Considerations

1. **Access Control:**
   - Implement role-based access control (RBAC)
   - Use multi-factor authentication (MFA) for administrative access
   - Audit all access logs

2. **Encryption:**
   - TLS 1.2+ for data in transit
   - Database encryption at rest (LUKS, dm-crypt)
   - Encrypted backups

3. **Audit Trails:**
   - Enable comprehensive logging
   - Retain logs for 6+ years
   - Implement log integrity monitoring

4. **Disaster Recovery:**
   - Test backups monthly
   - Document recovery procedures
   - Maintain offsite backups

5. **Vulnerability Management:**
   - Regular security scans
   - Timely patching
   - Penetration testing annually

### Integration with EHR

**Read-Only Integration (Shadow Mode):**

CDIL can run alongside existing EHR workflows without direct integration:

1. **Manual Upload**: Clinicians copy/paste notes into CDIL web interface
2. **Batch Import**: Export notes from EHR, import into CDIL via API
3. **HL7 v2 Listener**: Parse ORU messages for note text (future)
4. **FHIR API**: Query DocumentReference resources (future)

**Example: Batch Import Script**

```python
import requests
import csv

# Read notes from CSV export
with open('notes_export.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        response = requests.post(
            'https://cdil.yourhospital.org/v1/shadow/intake',
            headers={'Authorization': f'Bearer {JWT_TOKEN}'},
            json={
                'note_text': row['note_text'],
                'encounter_id': row['encounter_id'],
                'note_type': row['note_type']
            }
        )
        print(f"Ingested: {response.json()['shadow_id']}")
```

---

## Security Checklist

Use this checklist before going to production:

### Infrastructure Security

- [ ] TLS 1.2+ enabled with valid certificate
- [ ] Firewall rules configured (allow only necessary ports)
- [ ] Network segmentation implemented (VLANs)
- [ ] DDoS protection enabled (Cloudflare, WAF)
- [ ] Intrusion detection system (IDS) deployed
- [ ] Security groups/network ACLs configured
- [ ] SSH access restricted (key-based, no password)
- [ ] Root login disabled
- [ ] Non-standard SSH port (if applicable)

### Application Security

- [ ] JWT_SECRET_KEY set (strong, random)
- [ ] Environment set to "production"
- [ ] STORE_NOTE_TEXT disabled (default: false)
- [ ] Rate limiting enabled (default: on)
- [ ] Debug mode disabled
- [ ] Error messages sanitized (no PHI leakage)
- [ ] Input validation enabled
- [ ] SQL injection protection (parameterized queries)
- [ ] CORS configured (restrict origins)
- [ ] Security headers set (HSTS, CSP, etc.)

### Database Security

- [ ] Database file permissions (600 or 640)
- [ ] Database encryption at rest
- [ ] WAL mode enabled (SQLite)
- [ ] Automated backups configured
- [ ] Backup encryption enabled
- [ ] Offsite backup storage
- [ ] Backup restoration tested
- [ ] Database integrity checks scheduled

### Logging and Monitoring

- [ ] PHI redaction filter enabled
- [ ] Structured logging configured
- [ ] Log aggregation set up (ELK, Splunk)
- [ ] Log retention policy (6+ years for HIPAA)
- [ ] Alerting configured (errors, security events)
- [ ] Health check monitoring
- [ ] Performance monitoring (APM)
- [ ] Uptime monitoring (Pingdom, UptimeRobot)

### Key Management

- [ ] Per-tenant keys generated
- [ ] Key rotation schedule defined
- [ ] Key backup procedure documented
- [ ] Key access audited
- [ ] Old keys retained (for verification)
- [ ] Key material stored securely (HSM, KMS)

### Compliance

- [ ] HIPAA BAA signed (if applicable)
- [ ] Security risk assessment completed
- [ ] Incident response plan documented
- [ ] Access control policies defined
- [ ] Audit logging enabled
- [ ] Penetration testing scheduled
- [ ] Security awareness training completed
- [ ] Disaster recovery plan tested

### Documentation

- [ ] Deployment architecture documented
- [ ] Runbook created (operations guide)
- [ ] Incident response procedures documented
- [ ] Contact information updated
- [ ] Change management process defined
- [ ] System diagrams current
- [ ] API documentation published
- [ ] User training materials created

---

## Support and Escalation

For security issues or deployment questions:

- **Email**: security@cdil.org
- **Phone**: 1-800-CDIL-SEC
- **PagerDuty**: cdil-security-oncall

### Incident Response

1. **Detect**: Monitoring alerts trigger
2. **Contain**: Isolate affected systems
3. **Investigate**: Review logs, forensics
4. **Remediate**: Patch, update, restore
5. **Report**: Document and notify stakeholders

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-01-01 | Initial release |

---

**Document Classification**: Internal Use Only  
**Last Updated**: 2024-01-01  
**Next Review**: 2024-04-01
