-- ParseFlow.ai Database Schema
-- Cloudflare D1 SQL schema for document intelligence API

-- Accounts & Billing
CREATE TABLE accounts (
  id TEXT PRIMARY KEY,          -- 'acc_...'
  email TEXT UNIQUE,
  stripe_customer_id TEXT,
  credits_balance INTEGER DEFAULT 10,
  created_at INTEGER
);

-- Authentication
CREATE TABLE api_keys (
  key TEXT PRIMARY KEY,         -- 'pf_live_...'
  account_id TEXT NOT NULL,
  label TEXT,
  revoked BOOLEAN DEFAULT 0,
  created_at INTEGER,
  FOREIGN KEY (account_id) REFERENCES accounts(id)
);

-- Core Job Log
CREATE TABLE jobs (
  id TEXT PRIMARY KEY,          -- 'job_...'
  account_id TEXT NOT NULL,
  status TEXT,                  -- 'queued', 'processing', 'completed', 'failed'
  mode TEXT,                    -- 'general' (Docling) or 'financial' (DeepSeek)
  input_key TEXT,               -- R2 key: 'uploads/...'
  output_key TEXT,              -- R2 key: 'results/...'
  webhook_url TEXT,
  trust_score REAL,             -- 0.0 to 1.0
  error_message TEXT,
  created_at INTEGER,
  completed_at INTEGER
);

-- Performance Indexing
CREATE INDEX idx_jobs_acc_date ON jobs(account_id, created_at DESC);
CREATE INDEX idx_keys_lookup ON api_keys(key) WHERE revoked = 0;