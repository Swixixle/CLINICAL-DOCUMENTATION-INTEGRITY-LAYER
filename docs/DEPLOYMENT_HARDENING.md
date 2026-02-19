# Production Deployment Hardening Guide

## Overview

This document provides concrete, actionable guidance for deploying CDIL (Clinical Documentation Integrity Layer) in a production environment with courtroom-grade security.

**Audience**: DevOps, Security Engineers, Compliance Officers

**Prerequisites**:
- Linux/Unix server environment
- TLS certificates
- Secrets management system
- Monitoring infrastructure

---

## 1. TLS Termination

### Requirements

✅ **MUST**: TLS 1.2 or higher  
✅ **MUST**: Valid certificate from trusted CA  
✅ **MUST**: HTTP Strict Transport Security (HSTS)  
❌ **MUST NOT**: Self-signed certificates in production  
❌ **MUST NOT**: TLS 1.0 or 1.1

### Configuration

**Certificate Requirements**:
- 2048-bit RSA or 256-bit ECC minimum
- Valid chain to trusted root CA
- Wildcard or SAN certificate for multiple subdomains
- Auto-renewal configured (Let's Encrypt, AWS ACM, etc.)

**Cipher Suite** (TLS 1.2+):
```
ECDHE-ECDSA-AES256-GCM-SHA384
ECDHE-RSA-AES256-GCM-SHA384
ECDHE-ECDSA-CHACHA20-POLY1305
ECDHE-RSA-CHACHA20-POLY1305
ECDHE-ECDSA-AES128-GCM-SHA256
ECDHE-RSA-AES128-GCM-SHA256
```

**Disable**:
- SSLv2, SSLv3, TLS 1.0, TLS 1.1
- NULL ciphers
- Export ciphers
- Anonymous ciphers
- MD5 ciphers

---

## 2. Reverse Proxy Configuration (Nginx)

### Production Nginx Configuration

```nginx
# /etc/nginx/sites-available/cdil

upstream cdil_backend {
    # Use IP hash for session affinity if needed
    least_conn;
    
    server 127.0.0.1:8000 max_fails=3 fail_timeout=30s;
    server 127.0.0.1:8001 max_fails=3 fail_timeout=30s backup;
    
    keepalive 32;
}

server {
    listen 80;
    listen [::]:80;
    server_name cdil.yourhospital.com;
    
    # Redirect all HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name cdil.yourhospital.com;
    
    # TLS Configuration
    ssl_certificate /etc/ssl/certs/cdil.yourhospital.com.crt;
    ssl_certificate_key /etc/ssl/private/cdil.yourhospital.com.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305';
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling on;
    ssl_stapling_verify on;
    
    # HSTS (HTTP Strict Transport Security)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    
    # Security Headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';" always;
    
    # Rate Limiting (belt-and-suspenders with app-level rate limiting)
    limit_req_zone $binary_remote_addr zone=cdil_api:10m rate=100r/m;
    limit_req zone=cdil_api burst=20 nodelay;
    
    # Request Size Limits
    client_max_body_size 10M;  # Adjust based on max certificate size
    
    # Timeouts
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
    send_timeout 60s;
    
    # Logging (HIPAA-compliant - no PHI)
    access_log /var/log/nginx/cdil_access.log combined;
    error_log /var/log/nginx/cdil_error.log warn;
    
    location / {
        # Proxy to CDIL application
        proxy_pass http://cdil_backend;
        
        # Preserve client information
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Disable buffering for streaming responses
        proxy_buffering off;
        
        # Connection reuse
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
    
    location /health {
        # Health check endpoint - no auth required
        proxy_pass http://cdil_backend/health;
        access_log off;
    }
    
    # Block access to internal admin routes if exposed
    location /internal/ {
        deny all;
        return 404;
    }
}
```

### Load Balancer Notes

If using AWS ALB, Azure Load Balancer, or GCP Load Balancer:
- Enable connection draining (30-60 seconds)
- Configure health checks: `GET /health` with 200 OK expected
- Enable sticky sessions (cookie-based) if needed
- Set idle timeout to 60 seconds minimum

---

## 3. Secrets Management

### Requirements

✅ **MUST**: Use secrets management system (AWS Secrets Manager, Azure Key Vault, HashiCorp Vault)  
✅ **MUST**: Rotate secrets at least every 90 days  
✅ **MUST**: Audit all secret access  
❌ **MUST NOT**: Store secrets in environment variables  
❌ **MUST NOT**: Store secrets in code or config files  
❌ **MUST NOT**: Use dev keys in production

### Environment Variables (Non-Secret Config Only)

```bash
# /etc/systemd/system/cdil.service.d/override.conf

[Service]
# Application Config (NOT SECRETS)
Environment="ENV=PRODUCTION"
Environment="LOG_LEVEL=INFO"
Environment="DB_PATH=/var/lib/cdil/certificates.db"

# Secrets Manager References (actual secrets fetched at runtime)
Environment="SECRETS_MANAGER_ARN=arn:aws:secretsmanager:us-east-1:123456789012:secret:cdil/prod"
Environment="AWS_REGION=us-east-1"
```

### Secret Fetching Pattern

```python
# In production startup (main.py or separate config module)
import boto3
import json

def load_secrets():
    """Load secrets from AWS Secrets Manager at application startup."""
    client = boto3.client('secretsmanager', region_name=os.environ['AWS_REGION'])
    secret_arn = os.environ['SECRETS_MANAGER_ARN']
    
    response = client.get_secret_value(SecretId=secret_arn)
    secrets = json.loads(response['SecretString'])
    
    # Set secrets in memory only (never write to disk)
    os.environ['JWT_SECRET'] = secrets['jwt_secret']
    os.environ['DATABASE_ENCRYPTION_KEY'] = secrets['database_encryption_key']
    
    # DO NOT LOG SECRETS
    print("Secrets loaded successfully")
```

### Secrets to Manage

1. **JWT Signing Secret**: For API authentication
2. **Database Encryption Key**: For encrypting tenant keys at rest
3. **HSM Credentials**: For accessing hardware security module (if used)
4. **Backup Encryption Key**: For encrypting database backups

### Secret Rotation Process

**JWT Secret Rotation**:
1. Generate new secret
2. Store in secrets manager with new version
3. Update application to accept both old and new for 24 hours
4. Deploy application update
5. After 24 hours, remove old secret
6. Invalidate all tokens older than rotation time

**Database Encryption Key Rotation**:
1. Generate new key
2. Re-encrypt all tenant keys with new key
3. Update secrets manager
4. Deploy application update
5. Verify all keys accessible
6. Delete old key

---

## 4. Hardware Security Module (HSM) Recommendations

### When to Use HSM

Use HSM when:
- ✅ HIPAA compliance requires FIPS 140-2 Level 2 or higher
- ✅ Handling high-value certificates (e.g., legal proceedings)
- ✅ Regulatory requirement for hardware-backed keys
- ✅ Organization policy mandates HSM

### HSM Options

**AWS CloudHSM**:
- FIPS 140-2 Level 3 validated
- $1.60/hour per HSM (~$1,200/month)
- Minimum 2 HSMs for HA
- Full PKCS#11, JCE, CNG support

**Azure Dedicated HSM**:
- FIPS 140-2 Level 3 validated
- Similar pricing to AWS
- Thales SafeNet Luna HSM

**On-Premises HSM**:
- Thales Luna, Entrust nShield
- $10k-$50k initial cost
- Annual maintenance fees

### HSM Integration Pattern

```python
# gateway/app/services/hsm_key_registry.py

import pkcs11
from pkcs11 import Mechanism

class HSMKeyRegistry:
    """Key registry backed by HSM for production environments."""
    
    def __init__(self, hsm_slot: int, hsm_pin: str):
        self.lib = pkcs11.lib(os.environ['PKCS11_MODULE'])
        self.slot = self.lib.get_slots()[hsm_slot]
        self.session = self.slot.open()
        self.session.login(hsm_pin)
    
    def generate_key_for_tenant(self, tenant_id: str) -> str:
        """Generate ECDSA key pair in HSM."""
        # Key generation in HSM (never leaves hardware)
        public_key, private_key = self.session.generate_keypair(
            Mechanism.ECDSA_KEY_PAIR_GEN,
            {
                pkcs11.Attribute.EC_PARAMS: SECP256R1_OID,
                pkcs11.Attribute.LABEL: f"cdil-tenant-{tenant_id}",
                pkcs11.Attribute.TOKEN: True,
                pkcs11.Attribute.SIGN: True
            },
            {
                pkcs11.Attribute.LABEL: f"cdil-tenant-{tenant_id}",
                pkcs11.Attribute.TOKEN: True,
                pkcs11.Attribute.PRIVATE: True,
                pkcs11.Attribute.SENSITIVE: True,
                pkcs11.Attribute.EXTRACTABLE: False  # Cannot be exported
            }
        )
        
        return f"hsm-key-{tenant_id}"
    
    def sign(self, key_label: str, message: bytes) -> bytes:
        """Sign message using HSM-backed key."""
        private_key = self.session.get_key(label=key_label)
        signature = private_key.sign(message, mechanism=Mechanism.ECDSA_SHA256)
        return signature
```

### HSM Backup & DR

**Backup Strategy**:
- HSM keys are backed up within HSM cluster
- Use M-of-N key splitting for disaster recovery
- Store backup keys in geographically separate locations
- Test restore process quarterly

**Disaster Recovery**:
1. Maintain hot standby HSM in secondary region
2. Sync keys between primary and standby
3. Automate failover for < 5 minute RTO
4. Document manual failover procedure

---

## 5. Key Rotation Process

### Rotation Schedule

| Key Type | Rotation Frequency | Method |
|----------|-------------------|--------|
| Tenant Signing Keys | 1 year or on compromise | Blue-green rotation |
| JWT Secret | 90 days | Dual-accept period |
| Database Encryption Key | 1 year | Re-encryption |
| TLS Certificate | 90 days (auto-renewal) | Let's Encrypt/ACME |

### Tenant Key Rotation Procedure

**Overview**: Blue-green rotation with no downtime.

**Steps**:

1. **Generate New Key** (T+0):
   ```bash
   POST /v1/admin/keys/rotate
   Headers: X-Admin-Token: <admin_jwt>
   Body: {"tenant_id": "hospital-alpha"}
   ```
   - Generates new key with `status=pending`
   - Old key remains `status=active`

2. **Test New Key** (T+1 hour):
   ```bash
   POST /v1/admin/keys/test
   Body: {"tenant_id": "hospital-alpha", "key_id": "new-key-id"}
   ```
   - Issues test certificate with new key
   - Verifies signature
   - Confirms no regression

3. **Activate New Key** (T+24 hours):
   ```bash
   POST /v1/admin/keys/activate
   Body: {"tenant_id": "hospital-alpha", "key_id": "new-key-id"}
   ```
   - Sets new key to `status=active`
   - Sets old key to `status=retired`
   - All new certificates use new key
   - Old certificates still verifiable with old key

4. **Archive Old Key** (T+90 days):
   ```bash
   POST /v1/admin/keys/archive
   Body: {"tenant_id": "hospital-alpha", "key_id": "old-key-id"}
   ```
   - Moves key to cold storage
   - Maintains for legal retention period (typically 7 years for healthcare)

### Key Compromise Response

If key compromise suspected:

1. **IMMEDIATE** (< 15 minutes):
   - Revoke compromised key in key registry
   - Block all certificate issuance for affected tenant
   - Alert security team

2. **SHORT-TERM** (< 1 hour):
   - Generate new emergency key
   - Issue new certificates with emergency key
   - Notify affected tenant

3. **MEDIUM-TERM** (< 24 hours):
   - Forensic analysis of compromise
   - Determine blast radius
   - Notify customers if certificates issued during compromise window

4. **LONG-TERM** (< 7 days):
   - Complete incident report
   - Update rotation procedures
   - Implement additional controls

---

## 6. Incident Response Playbook

### Scenario: Compromised Signing Key

**Detection Indicators**:
- Certificates issued without corresponding API requests
- Suspicious certificate content or patterns
- Alerts from key access monitoring
- Report from tenant or security researcher

**Response Procedure**:

**Phase 1: CONTAIN** (0-15 minutes)

```bash
# 1. Revoke compromised key immediately
psql cdil_prod << EOF
UPDATE tenant_keys
SET status = 'COMPROMISED'
WHERE tenant_id = 'hospital-alpha' AND key_id = 'key-abc-123';
EOF

# 2. Block certificate issuance for tenant
psql cdil_prod << EOF
INSERT INTO tenant_blocks (tenant_id, reason, blocked_at)
VALUES ('hospital-alpha', 'KEY_COMPROMISE_INVESTIGATION', NOW());
EOF

# 3. Snapshot database for forensics
pg_dump cdil_prod > /secure/forensics/cdil_snapshot_$(date +%Y%m%d_%H%M%S).sql

# 4. Alert on-call security team
aws sns publish --topic-arn arn:aws:sns:us-east-1:123:cdil-security-alerts \
    --message "KEY COMPROMISE: tenant=hospital-alpha, key=key-abc-123"
```

**Phase 2: ASSESS** (15-60 minutes)

1. **Query all certificates issued by compromised key**:
   ```sql
   SELECT certificate_id, timestamp, note_hash
   FROM certificates
   WHERE tenant_id = 'hospital-alpha'
     AND key_id = 'key-abc-123'
     AND created_at_utc >= '2024-01-01'
   ORDER BY created_at_utc DESC;
   ```

2. **Check for anomalous certificates**:
   - Certificates issued outside business hours
   - Unusual model versions
   - Missing human attestation when expected

3. **Review access logs**:
   ```bash
   grep "hospital-alpha" /var/log/cdil/access.log | grep "POST /v1/clinical/documentation"
   ```

4. **Determine compromise window**:
   - First unauthorized certificate
   - Last authorized certificate
   - Total certificates affected

**Phase 3: ERADICATE** (1-4 hours)

1. **Generate new emergency key**:
   ```bash
   POST /v1/admin/keys/emergency-generate
   Headers: X-Admin-Token: <admin_jwt>
   Body: {
       "tenant_id": "hospital-alpha",
       "reason": "key_compromise_response"
   }
   ```

2. **Re-enable certificate issuance with new key**:
   ```sql
   DELETE FROM tenant_blocks
   WHERE tenant_id = 'hospital-alpha';
   ```

3. **Notify tenant**:
   ```
   Subject: Security Incident - Certificate Signing Key Compromised
   
   We have detected unauthorized access to your certificate signing key.
   
   Actions taken:
   - Compromised key immediately revoked
   - New key generated and activated
   - All certificates issued 2024-01-15 to 2024-01-20 flagged for review
   
   Required actions:
   - Review flagged certificates (see attached list)
   - Revoke any fraudulent certificates
   - Re-issue legitimate certificates with new key
   
   Timeline:
   - Compromise detected: 2024-01-20 14:32 UTC
   - Key revoked: 2024-01-20 14:35 UTC (3 minutes)
   - New key activated: 2024-01-20 15:10 UTC (38 minutes)
   
   Contact: security@cdil.com for questions
   ```

**Phase 4: RECOVER** (4-24 hours)

1. **Tenant re-issues certificates**:
   - Tenant reviews all certificates in compromise window
   - Tenant re-issues legitimate certificates with new key
   - Old certificates marked as revoked

2. **Update certificate revocation list**:
   ```sql
   INSERT INTO revoked_certificates (certificate_id, reason, revoked_at)
   SELECT certificate_id, 'KEY_COMPROMISE', NOW()
   FROM certificates
   WHERE key_id = 'key-abc-123'
     AND created_at_utc >= '2024-01-15'
     AND created_at_utc <= '2024-01-20';
   ```

**Phase 5: LESSONS LEARNED** (24-72 hours)

1. Complete incident report
2. Root cause analysis
3. Update access controls
4. Enhance monitoring
5. Train team on updated procedures

### Monitoring & Alerting

**Key Access Monitoring**:
```python
# Log all key access for audit
def audit_key_access(tenant_id: str, key_id: str, operation: str):
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tenant_id": tenant_id,
        "key_id": key_id,
        "operation": operation,
        "source_ip": request.remote_addr,
        "user_agent": request.headers.get("User-Agent")
    }
    
    # Send to SIEM
    send_to_siem(log_entry)
    
    # Alert on suspicious patterns
    if is_suspicious(log_entry):
        send_security_alert(log_entry)
```

**Alert Conditions**:
- Key access outside business hours
- Rapid key generation (> 10 keys/hour)
- Certificate issuance rate spike (> 1000 certs/hour)
- Failed signature verifications
- Cross-tenant key access attempts

---

## 7. Database Security

### At-Rest Encryption

```bash
# Enable full-disk encryption (Linux - LUKS)
cryptsetup luksFormat /dev/sdb
cryptsetup luksOpen /dev/sdb cdil_data
mkfs.ext4 /dev/mapper/cdil_data
mount /dev/mapper/cdil_data /var/lib/cdil
```

### Application-Level Encryption

```python
# Encrypt tenant keys before storing in database
from cryptography.fernet import Fernet

def encrypt_key(private_key_pem: bytes) -> bytes:
    """Encrypt private key with database encryption key."""
    encryption_key = os.environ['DATABASE_ENCRYPTION_KEY'].encode()
    f = Fernet(encryption_key)
    return f.encrypt(private_key_pem)

def decrypt_key(encrypted_key: bytes) -> bytes:
    """Decrypt private key."""
    encryption_key = os.environ['DATABASE_ENCRYPTION_KEY'].encode()
    f = Fernet(encryption_key)
    return f.decrypt(encrypted_key)
```

### Backup Strategy

```bash
# Daily encrypted backups to S3
#!/bin/bash
# /usr/local/bin/cdil-backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="/tmp/cdil_backup_${DATE}.sql"
ENCRYPTED_FILE="/tmp/cdil_backup_${DATE}.sql.gpg"

# Dump database
sqlite3 /var/lib/cdil/certificates.db ".backup ${BACKUP_FILE}"

# Encrypt with GPG
gpg --encrypt --recipient cdil-backup@company.com "${BACKUP_FILE}"

# Upload to S3 with versioning
aws s3 cp "${ENCRYPTED_FILE}" "s3://cdil-backups/prod/${DATE}/" \
    --server-side-encryption AES256 \
    --storage-class STANDARD_IA

# Clean up
rm "${BACKUP_FILE}" "${ENCRYPTED_FILE}"

# Retain backups: 7 days daily, 4 weeks weekly, 12 months monthly
```

---

## 8. Network Security

### Firewall Rules

```bash
# iptables (Linux)
# Allow HTTPS only from internal load balancer
iptables -A INPUT -p tcp --dport 8000 -s 10.0.1.0/24 -j ACCEPT
iptables -A INPUT -p tcp --dport 8000 -j DROP

# Allow SSH only from bastion host
iptables -A INPUT -p tcp --dport 22 -s 10.0.0.5 -j ACCEPT
iptables -A INPUT -p tcp --dport 22 -j DROP

# Allow health checks from load balancer
iptables -A INPUT -p tcp --dport 8000 -s 10.0.2.0/24 -j ACCEPT
```

### Network Segmentation

```
[Internet] 
    ↓ (HTTPS/443)
[ALB / CloudFront]
    ↓ (HTTPS/443)
[WAF]
    ↓ (HTTP/8000 - internal only)
[CDIL Application Servers] (Private subnet)
    ↓ (PostgreSQL/5432 - internal only)
[Database] (Private subnet, no internet access)
```

### VPC Configuration (AWS Example)

```hcl
# Terraform - VPC setup
resource "aws_vpc" "cdil" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
}

resource "aws_subnet" "public" {
  vpc_id            = aws_vpc.cdil.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"
}

resource "aws_subnet" "private_app" {
  vpc_id            = aws_vpc.cdil.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "us-east-1a"
}

resource "aws_subnet" "private_db" {
  vpc_id            = aws_vpc.cdil.id
  cidr_block        = "10.0.3.0/24"
  availability_zone = "us-east-1a"
}

resource "aws_security_group" "cdil_app" {
  vpc_id = aws_vpc.cdil.id
  
  # Allow HTTPS from ALB only
  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  
  # Allow all outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "cdil_db" {
  vpc_id = aws_vpc.cdil.id
  
  # Allow PostgreSQL from app servers only
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.cdil_app.id]
  }
  
  # NO outbound internet access
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["10.0.0.0/16"]  # VPC only
  }
}
```

---

## 9. Monitoring & Logging

### Metrics to Monitor

| Metric | Threshold | Action |
|--------|-----------|--------|
| Certificate Issuance Rate | > 1000/min | Alert |
| API Error Rate | > 5% | Alert |
| Database Latency | > 100ms | Investigate |
| Signature Verification Failures | > 1% | Alert |
| Key Access Outside Business Hours | Any | Alert |
| Failed Authentication Attempts | > 100/min | Block IP |

### Logging Best Practices

**DO**:
- ✅ Log all authentication attempts
- ✅ Log all certificate issuances
- ✅ Log all key access
- ✅ Log all admin operations
- ✅ Send logs to centralized SIEM

**DO NOT**:
- ❌ Log PHI (note text, patient identifiers)
- ❌ Log private keys
- ❌ Log JWT secrets
- ❌ Log password/credentials

### Sample Log Entry (HIPAA-Compliant)

```json
{
  "timestamp": "2024-01-20T15:32:10Z",
  "level": "INFO",
  "event": "certificate_issued",
  "certificate_id": "019c734c-fabf-7e13-8fe7-b28d504ccd36",
  "tenant_id": "hospital-alpha",
  "model_name": "gpt-4",
  "human_reviewed": true,
  "note_hash": "abc123...",  // Hash only, not plaintext
  "source_ip": "10.0.2.45",
  "user_agent": "CDIL-Client/1.0"
}
```

---

## 10. Compliance Checklist

### HIPAA

- [ ] PHI encrypted at rest
- [ ] PHI encrypted in transit (TLS)
- [ ] Access controls implemented
- [ ] Audit logging enabled
- [ ] Business Associate Agreements (BAAs) signed
- [ ] Breach notification process documented
- [ ] Risk assessment completed annually
- [ ] Security training for all staff

### SOC 2 Type II

- [ ] Change management process documented
- [ ] Incident response plan tested quarterly
- [ ] Penetration testing annually
- [ ] Vulnerability scanning monthly
- [ ] Access reviews quarterly
- [ ] Backup/restore tested quarterly

---

## Summary

This deployment hardening guide provides concrete, actionable steps for securing CDIL in production. Key takeaways:

1. **Never use dev keys in production** - Generate production keys with HSM if possible
2. **Secrets management is mandatory** - Use AWS Secrets Manager, Azure Key Vault, or Vault
3. **TLS everywhere** - No exceptions for unencrypted traffic
4. **Monitor key access** - Alert on suspicious patterns immediately
5. **Practice incident response** - Quarterly drills for key compromise scenarios
6. **Automate backups** - Daily encrypted backups to geographically separate location
7. **Rotate keys regularly** - Annual rotation minimum, 90 days for high-security environments

**Questions?** Contact: security@cdil.com
