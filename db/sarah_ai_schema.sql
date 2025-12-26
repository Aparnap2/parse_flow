-- Sarah AI Database Schema
-- Cloudflare D1 SQL schema for configurable data entry system

-- Users & Authentication
CREATE TABLE users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  google_id TEXT UNIQUE, -- For OAuth
  inbox_alias TEXT UNIQUE, -- 'uuid@sarah.ai'
  created_at INTEGER
);

-- Extraction Blueprints (Custom Schemas)
CREATE TABLE blueprints (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  name TEXT, -- "Xero Import"
  schema_json TEXT, -- JSON: [{ name: "Total", type: "currency", instruction: "..." }]
  target_sheet_id TEXT, -- Optional: Google Sheet ID
  FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Processing Jobs
CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  user_id TEXT,
  status TEXT, -- 'queued', 'review', 'completed'
  r2_key TEXT,
  result_json TEXT, -- Extracted Data
  confidence REAL,
  created_at INTEGER
);

-- Performance Indexing
CREATE INDEX idx_jobs_user_date ON jobs(user_id, created_at DESC);
CREATE INDEX idx_users_google_id ON users(google_id);
CREATE INDEX idx_users_inbox_alias ON users(inbox_alias);