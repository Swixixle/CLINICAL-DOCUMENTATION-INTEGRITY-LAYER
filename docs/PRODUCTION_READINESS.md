# Production Readiness Checklist

## ⚠️ CURRENT STATUS: NOT PRODUCTION-READY

**Phase 1 Security**: ✅ Complete - Tenant isolation verified  
**Production Deployment**: ❌ Not Ready - Critical hardening required

## Document Information
- **Version**: 2.0
- **Date**: 2026-02-18
- **Target Audience**: DevOps, Security, Compliance Teams
- **Purpose**: Comprehensive checklist for production deployment

## ⛔ DO NOT DEPLOY TO PRODUCTION UNTIL:

1. ✅ All items marked **[CRITICAL]** are complete
2. ✅ Security audit by qualified third party completed
3. ✅ Penetration testing completed with all findings remediated
4. ✅ Incident response procedures documented and tested
5. ✅ Compliance requirements (HIPAA, SOC 2) verified if applicable

---

## 1. Infrastructure Requirements

### 1.1 Compute

- [ ] **Minimum**: 2 vCPUs, 4 GB RAM
- [ ] **Recommended**: 4 vCPUs, 8 GB RAM (for high-volume tenants)
- [ ] **Load Balancer**: Configured with health checks on `/healthz`
- [ ] **Auto-scaling**: Based on CPU > 70% and request queue depth

### 1.2 Network

- [ ] **TLS/SSL**: Certificate from trusted CA (not self-signed)
- [ ] **TLS Version**: Minimum TLS 1.2, prefer TLS 1.3
- [ ] **Cipher Suites**: Strong ciphers only (no RC4, 3DES, MD5)
- [ ] **HTTPS Everywhere**: All endpoints require HTTPS
- [ ] **CORS**: Configured for specific allowed origins (not `*`)
- [ ] **Firewall**: Whitelist only necessary ports (443, health check)

### 1.3 Database

- [ ] **Storage**: Persistent volume (not ephemeral)
- [ ] **Backup**: Automated daily backups with 30-day retention
- [ ] **Encryption**: Disk encryption enabled (e.g., AWS EBS encryption)
- [ ] **High Availability**: Replicas or multi-AZ deployment
- [ ] **Migration**: Consider PostgreSQL or MySQL for production scale

---

## 2. Security Configuration

### 2.1 Secrets Management **[CRITICAL]**

**Status**: ❌ NOT IMPLEMENTED - Currently using hardcoded dev secrets

**Critical**: Do NOT use hardcoded secrets. ALL secrets must be in secrets manager.

- [ ] **JWT Secret Key**: Stored in AWS Secrets Manager, Azure Key Vault, or GCP Secret Manager
  - Env var: `JWT_SECRET_KEY`
  - Current: Using `"dev-secret-key-change-in-production"` ⚠️
  - **CRITICAL**: Dev secret is committed to git history and is COMPROMISED
  - Production MUST use completely new secret (never use rotations of this value)
  - Length: Minimum 256 bits (32 bytes) for HS256
  - Rotation: Every 90 days with zero-downtime rotation

- [ ] **Tenant Signing Keys**: Migrate to KMS/HSM
  - Current: Stored in SQLite database ⚠️
  - Target: AWS KMS, Azure Key Vault, or GCP KMS
  - Private keys should NEVER be in application database
  - Rotation: Every 90 days

- [ ] **Database Credentials**: Stored in secrets manager
  - Connection string should use IAM authentication if possible

- [ ] **Cryptographic Keys**: Migrate to HSM/KMS
  - AWS KMS, GCP KMS, or Azure Key Vault
  - Never store private keys in database in production

### 2.2 JWT Configuration

- [ ] **Algorithm**: Set `JWT_ALGORITHM=RS256` (asymmetric)
- [ ] **Public Key**: Obtain from identity provider (e.g., Auth0 JWKS endpoint)
- [ ] **Token Expiration**: Enforce short-lived tokens (1-8 hours)
- [ ] **Refresh Tokens**: Implement if sessions longer than 8 hours
- [ ] **Issuer Validation**: Verify `iss` claim matches expected issuer

### 2.3 Database Security

- [ ] **Path**: Set `CDIL_DB_PATH` to persistent volume outside container filesystem
- [ ] **Permissions**: Database file should be 0600 (owner read/write only)
- [ ] **WAL Mode**: Enabled (automatic via migration)
- [ ] **Connection Limits**: Set appropriate max connections
- [ ] **Audit Access**: Log all database connections

### 2.4 Rate Limiting

- [ ] **Per-Identity**: Implement identity-based rate limiting (not just IP)
- [ ] **DDoS Protection**: Use WAF (CloudFlare, AWS WAF) for Layer 7 protection
- [ ] **Health Check**: Exempt `/healthz` from rate limiting
- [ ] **Abuse Monitoring**: Alert on 429 responses > threshold

---

## 3. Application Configuration

### 3.1 Environment Variables

Required:
```bash
# JWT Configuration
export JWT_SECRET_KEY="<256-bit-secret-from-secrets-manager>"
export JWT_ALGORITHM="RS256"

# Database
export CDIL_DB_PATH="/data/cdil/eli_sentinel.db"

# Logging
export LOG_LEVEL="INFO"  # DEBUG only in staging
export LOG_FORMAT="json"  # For structured logging

# Rate Limiting
export RATE_LIMIT_ENABLED="true"
export RATE_LIMIT_STORAGE="redis://<redis-url>"  # For distributed rate limiting
```

### 3.2 Logging Configuration

- [ ] **Structured Logging**: JSON format for log aggregation
- [ ] **Log Level**: INFO in production (not DEBUG)
- [ ] **PHI Redaction**: All logs sanitized (no request bodies, no PHI)
- [ ] **Log Aggregation**: Centralized (e.g., DataDog, Splunk, ELK Stack)
- [ ] **Retention**: 90 days minimum for audit compliance
- [ ] **Alerting**: Critical errors trigger immediate alerts

### 3.3 Debug Mode

- [ ] **Disabled**: `debug=False` in FastAPI configuration (already set)
- [ ] **Verify**: No stack traces exposed to clients
- [ ] **Error Responses**: Generic messages only (no implementation details)

---

## 4. Monitoring & Observability

### 4.1 Application Metrics

- [ ] **Prometheus**: Expose `/metrics` endpoint (with authentication)
- [ ] **Grafana**: Dashboards for:
  - Certificate issuance rate
  - Verification success/failure rate
  - Average response times
  - Error rates by endpoint
  - Rate limit hits

### 4.2 Health Checks

- [ ] **Liveness**: `/healthz` returns 200 if app is running
- [ ] **Readiness**: Separate endpoint checking DB connectivity
- [ ] **Load Balancer**: Configured to use health check
- [ ] **Timeout**: Health check timeout < 5 seconds

### 4.3 Alerting

- [ ] **Error Rate**: Alert if > 5% of requests fail (5 min window)
- [ ] **Response Time**: Alert if p95 latency > 2 seconds
- [ ] **Certificate Failures**: Alert if verification failures spike
- [ ] **Database**: Alert on connection failures, disk space < 10%
- [ ] **Security**: Alert on repeated 401/403 responses (brute force attempt)

---

## 5. Compliance & Audit

### 5.1 Audit Logging

- [ ] **Structured Format**: JSON with:
  - timestamp
  - request_id
  - user_id (from JWT sub)
  - tenant_id
  - operation (issue_certificate, verify_certificate, etc.)
  - result (success/failure)
  - ip_address
  - user_agent

- [ ] **No PHI**: Logs never contain:
  - note_text
  - patient_reference
  - human_reviewer_id
  - Request bodies

- [ ] **Tamper-Proof**: Consider log signing or write-once storage

### 5.2 Compliance Documentation

- [ ] **SOC 2**: System description updated with CDIL architecture
- [ ] **HIPAA**: Business Associate Agreement (BAA) in place
- [ ] **21 CFR Part 11**: Validation documentation for e-signatures
- [ ] **GDPR**: Data Processing Agreement (DPA) if EU patients

### 5.3 Data Retention

- [ ] **Certificates**: Retention policy defined (e.g., 7 years per HIPAA)
- [ ] **Logs**: 90 days retention minimum
- [ ] **Nonces**: Purge nonces older than 30 days (configurable)
- [ ] **Rotated Keys**: Retention for verification (e.g., 2 years)

---

## 6. Disaster Recovery

### 6.1 Backup Strategy

- [ ] **Database**: Automated daily backups
- [ ] **Backup Testing**: Monthly restore test to verify backups work
- [ ] **Off-site**: Backups stored in separate region/availability zone
- [ ] **Encryption**: Backups encrypted at rest

### 6.2 Recovery Procedures

- [ ] **RTO**: Recovery Time Objective defined (e.g., 4 hours)
- [ ] **RPO**: Recovery Point Objective defined (e.g., 24 hours)
- [ ] **Runbook**: Documented disaster recovery procedures
- [ ] **Failover**: Tested failover to secondary region/instance

### 6.3 Key Recovery

- [ ] **Key Backup**: Tenant keys backed up securely (encrypted)
- [ ] **Key Escrow**: Consider key escrow for catastrophic recovery
- [ ] **Recovery Testing**: Quarterly test of key recovery procedure

---

## 7. Incident Response

### 7.1 Security Incidents

- [ ] **Incident Response Plan**: Documented procedures for:
  - Key compromise
  - Database breach
  - DDoS attack
  - Insider threat

- [ ] **Contact List**: On-call security team with escalation path
- [ ] **Communication Plan**: Customer notification template ready
- [ ] **Forensics**: Preserve logs for forensic analysis

### 7.2 Key Rotation (Emergency)

If key compromise suspected:
1. [ ] Rotate affected tenant's keys immediately
2. [ ] Revoke compromised key (mark as "revoked" in DB)
3. [ ] Notify affected tenant
4. [ ] Review audit logs for unauthorized certificate issuance
5. [ ] Forensic analysis to determine blast radius

---

## 8. Performance Tuning

### 8.1 Database Optimization

- [ ] **Indexes**: Verify all indexes from schema.sql are created
- [ ] **Connection Pool**: Configure uvicorn workers appropriately
- [ ] **Query Optimization**: Review slow query logs
- [ ] **Vacuum**: Periodic SQLite VACUUM or migrate to PostgreSQL

### 8.2 Application Tuning

- [ ] **Uvicorn Workers**: Set to 2x CPU cores
- [ ] **Async I/O**: FastAPI async endpoints used where appropriate
- [ ] **Caching**: Consider caching public keys (already done in KeyRegistry)
- [ ] **Rate Limiting Storage**: Use Redis for distributed rate limiting

---

## 9. Testing & Validation

### 9.1 Pre-Production Testing

- [ ] **Load Testing**: Simulate peak load (e.g., 100 concurrent users)
- [ ] **Penetration Testing**: Third-party security assessment
- [ ] **Chaos Engineering**: Test failure scenarios (DB down, network partition)
- [ ] **Compliance Testing**: Validate against 21 CFR Part 11, HIPAA requirements

### 9.2 Security Testing

- [ ] **OWASP Top 10**: Verify no vulnerabilities
- [ ] **SQL Injection**: Parameterized queries only (already done)
- [ ] **XSS**: No user input rendered in responses
- [ ] **CSRF**: Not applicable (API-only, no cookies)
- [ ] **JWT Validation**: Test with expired, malformed, tampered tokens

---

## 10. Deployment Checklist

### 10.1 Pre-Deployment

- [ ] All critical items in this checklist completed
- [ ] Security review approved
- [ ] Compliance review approved
- [ ] Load testing passed
- [ ] Staging environment mirrors production

### 10.2 Deployment

- [ ] **Blue-Green Deployment**: Zero-downtime deployment strategy
- [ ] **Database Migration**: Run schema migrations before code deployment
- [ ] **Rollback Plan**: Documented rollback procedure
- [ ] **Smoke Tests**: Automated tests run post-deployment

### 10.3 Post-Deployment

- [ ] **Monitoring**: Verify metrics are being collected
- [ ] **Alerts**: Verify alert rules are active
- [ ] **Logging**: Verify logs are flowing to aggregation system
- [ ] **Health Checks**: Verify load balancer sees healthy instances

---

## 11. Operational Procedures

### 11.1 Routine Maintenance

**Daily**:
- [ ] Review error logs for anomalies
- [ ] Check database disk space

**Weekly**:
- [ ] Review rate limiting metrics
- [ ] Check certificate issuance trends

**Monthly**:
- [ ] Security patch updates
- [ ] Backup restore test
- [ ] Review and rotate access credentials

**Quarterly**:
- [ ] JWT secret rotation (if using HS256)
- [ ] Tenant key rotation (recommended)
- [ ] Disaster recovery drill
- [ ] Security training for team

### 11.2 Tenant Onboarding

For each new tenant:
1. [ ] Generate unique tenant_id (UUID)
2. [ ] Configure JWT issuer to include tenant_id in claims
3. [ ] Generate initial key pair (automatic on first certificate)
4. [ ] Verify tenant isolation (test cross-tenant access blocked)
5. [ ] Provide tenant with API documentation

---

## 12. Documentation

### 12.1 Required Documentation

- [ ] **API Documentation**: OpenAPI/Swagger docs accessible
- [ ] **Integration Guide**: For EHR vendors
- [ ] **Security Architecture**: This threat model document
- [ ] **Runbooks**: Operational procedures documented
- [ ] **Compliance Artifacts**: Validation documentation

### 12.2 Training

- [ ] **Operations Team**: Trained on CDIL operations
- [ ] **Security Team**: Trained on incident response
- [ ] **Developers**: Trained on secure coding practices

---

## 13. Post-Launch

### 13.1 Monitoring (First 30 Days)

- [ ] **Daily Reviews**: Errors, performance, security logs
- [ ] **Weekly Reports**: KPIs to stakeholders
- [ ] **Customer Feedback**: Collect integration feedback

### 13.2 Continuous Improvement

- [ ] **Security Patches**: Apply within 7 days of release
- [ ] **Vulnerability Scanning**: Continuous or weekly scans
- [ ] **Threat Intelligence**: Monitor for new attack vectors
- [ ] **Performance Optimization**: Based on real-world usage patterns

---

## 14. Sign-Off

This checklist must be signed off by:

- [ ] **Security Lead**: [Name] _______________ Date: ___________
- [ ] **Compliance Lead**: [Name] _______________ Date: ___________
- [ ] **Engineering Lead**: [Name] _______________ Date: ___________
- [ ] **DevOps Lead**: [Name] _______________ Date: ___________

---

## Contact Information

**Security Incidents**: security@example.com  
**On-Call Pager**: [PagerDuty/OpsGenie link]  
**Escalation**: [CTO/CISO contact]

---

## Appendix: Configuration Examples

### A.1 Production docker-compose.yml (Example)

```yaml
version: '3.8'
services:
  cdil:
    image: cdil:v2.0.0
    environment:
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - JWT_ALGORITHM=RS256
      - CDIL_DB_PATH=/data/eli_sentinel.db
      - LOG_LEVEL=INFO
      - LOG_FORMAT=json
    volumes:
      - ./data:/data
    ports:
      - "8000:8000"
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### A.2 Example Nginx TLS Config

```nginx
server {
    listen 443 ssl http2;
    server_name api.cdil.example.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers on;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

**Document End**
