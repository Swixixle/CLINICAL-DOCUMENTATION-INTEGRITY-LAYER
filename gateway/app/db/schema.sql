-- CDIL Gateway Database Schema
-- SQLite MVP schema for transaction, certificate, and key storage

-- Transactions table
-- Stores full accountability packets as canonical JSON
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY,
    gateway_timestamp_utc TEXT NOT NULL,
    environment TEXT NOT NULL,
    client_id TEXT NOT NULL,
    feature_tag TEXT NOT NULL,
    policy_version_hash TEXT NOT NULL,
    final_hash TEXT NOT NULL,
    packet_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(gateway_timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_transactions_client ON transactions(client_id);
CREATE INDEX IF NOT EXISTS idx_transactions_environment ON transactions(environment);

-- Keys table
-- Stores public keys for verification
CREATE TABLE IF NOT EXISTS keys (
    key_id TEXT PRIMARY KEY,
    jwk_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

-- Index for active keys
CREATE INDEX IF NOT EXISTS idx_keys_status ON keys(status);

-- Certificates table
-- Stores clinical documentation integrity certificates
CREATE TABLE IF NOT EXISTS certificates (
    certificate_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    note_hash TEXT NOT NULL,
    chain_hash TEXT NOT NULL,
    key_id TEXT NOT NULL,
    certificate_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

-- Indexes for certificate queries
CREATE INDEX IF NOT EXISTS idx_certificates_tenant ON certificates(tenant_id);
CREATE INDEX IF NOT EXISTS idx_certificates_timestamp ON certificates(timestamp);
CREATE INDEX IF NOT EXISTS idx_certificates_created ON certificates(created_at_utc);
CREATE INDEX IF NOT EXISTS idx_certificates_key_id ON certificates(key_id);

-- Tenant keys table
-- Stores per-tenant cryptographic keys for signature isolation
CREATE TABLE IF NOT EXISTS tenant_keys (
    key_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    private_key_pem TEXT NOT NULL,
    public_jwk_json TEXT NOT NULL,
    status TEXT NOT NULL,  -- 'active' or 'rotated'
    created_at_utc TEXT NOT NULL
);

-- Indexes for tenant key queries
CREATE INDEX IF NOT EXISTS idx_tenant_keys_tenant ON tenant_keys(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_keys_status ON tenant_keys(tenant_id, status);

-- Used nonces table
-- Prevents replay attacks by tracking used nonces per tenant
CREATE TABLE IF NOT EXISTS used_nonces (
    tenant_id TEXT NOT NULL,
    nonce TEXT NOT NULL,
    used_at_utc TEXT NOT NULL,
    PRIMARY KEY (tenant_id, nonce)
);

-- Index for nonce cleanup (to purge old nonces)
CREATE INDEX IF NOT EXISTS idx_used_nonces_used_at ON used_nonces(used_at_utc);
