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

-- ============================================================================
-- Phase 2: Multi-Model Governance + Attribution
-- ============================================================================

-- AI Vendors table
-- Stores registered AI vendors who provide models
CREATE TABLE IF NOT EXISTS ai_vendors (
    vendor_id TEXT PRIMARY KEY,
    vendor_name TEXT NOT NULL,
    status TEXT NOT NULL,  -- 'active' or 'inactive'
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

-- Index for active vendors
CREATE INDEX IF NOT EXISTS idx_ai_vendors_status ON ai_vendors(status);

-- AI Models table
-- Stores registered AI models with metadata
CREATE TABLE IF NOT EXISTS ai_models (
    model_id TEXT PRIMARY KEY,
    vendor_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    status TEXT NOT NULL,  -- 'active', 'deprecated', or 'blocked'
    metadata_json TEXT,  -- Additional model metadata (capabilities, disclaimers, etc)
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    FOREIGN KEY (vendor_id) REFERENCES ai_vendors(vendor_id)
);

-- Indexes for model queries
CREATE INDEX IF NOT EXISTS idx_ai_models_vendor ON ai_models(vendor_id);
CREATE INDEX IF NOT EXISTS idx_ai_models_status ON ai_models(status);
CREATE INDEX IF NOT EXISTS idx_ai_models_name_version ON ai_models(model_name, model_version);

-- Vendor Model Keys table
-- Stores public keys for vendor model attestations
CREATE TABLE IF NOT EXISTS vendor_model_keys (
    key_id TEXT PRIMARY KEY,
    model_id TEXT NOT NULL,
    public_jwk_json TEXT NOT NULL,
    status TEXT NOT NULL,  -- 'active' or 'rotated'
    created_at_utc TEXT NOT NULL,
    rotated_at_utc TEXT,  -- Timestamp when key was rotated (if rotated)
    FOREIGN KEY (model_id) REFERENCES ai_models(model_id)
);

-- Indexes for vendor key queries
CREATE INDEX IF NOT EXISTS idx_vendor_model_keys_model ON vendor_model_keys(model_id);
CREATE INDEX IF NOT EXISTS idx_vendor_model_keys_status ON vendor_model_keys(model_id, status);

-- ============================================================================
-- Phase 3: Tenant-level Model Governance
-- ============================================================================

-- Tenant Allowed Models table
-- Controls which AI models are approved for use by each tenant
CREATE TABLE IF NOT EXISTS tenant_allowed_models (
    tenant_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    status TEXT NOT NULL,  -- 'allowed' or 'blocked'
    allowed_by TEXT,  -- Admin user who approved/blocked
    allow_reason TEXT,  -- Reason for allowlist decision
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY (tenant_id, model_id),
    FOREIGN KEY (model_id) REFERENCES ai_models(model_id)
);

-- Indexes for tenant model authorization queries
CREATE INDEX IF NOT EXISTS idx_tenant_allowed_models_tenant ON tenant_allowed_models(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_allowed_models_status ON tenant_allowed_models(tenant_id, status);
