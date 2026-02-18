-- ELI Sentinel Gateway Database Schema
-- SQLite MVP schema for transaction and key storage

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
    certificate_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

-- Indexes for certificate queries
CREATE INDEX IF NOT EXISTS idx_certificates_tenant ON certificates(tenant_id);
CREATE INDEX IF NOT EXISTS idx_certificates_timestamp ON certificates(timestamp);
CREATE INDEX IF NOT EXISTS idx_certificates_created ON certificates(created_at_utc);
