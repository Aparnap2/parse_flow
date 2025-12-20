-- D1 Database Schema for DocuFlow Document RAG System
-- Based on PRD specification lines 103-163

DROP TABLE IF EXISTS webhooks;
DROP TABLE IF EXISTS chunks;
DROP TABLE IF EXISTS documents;
DROP TABLE IF EXISTS api_keys;
DROP TABLE IF EXISTS projects;

CREATE TABLE projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE TABLE api_keys (
  key TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  revoked_at INTEGER,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE documents (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  source_name TEXT NOT NULL,
  content_type TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  r2_key TEXT NOT NULL,
  status TEXT NOT NULL,              -- CREATED|UPLOADED|PROCESSING|READY|FAILED|DELETED
  error TEXT,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(project_id, sha256),
  FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE chunks (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  content_md TEXT NOT NULL,
  page_start INTEGER,
  page_end INTEGER,
  created_at INTEGER NOT NULL,
  UNIQUE(document_id, chunk_index),
  FOREIGN KEY(project_id) REFERENCES projects(id),
  FOREIGN KEY(document_id) REFERENCES documents(id)
);

CREATE TABLE webhooks (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  url TEXT NOT NULL,
  secret TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);

-- Indexes for better query performance
CREATE INDEX idx_documents_project_id ON documents(project_id);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_sha256 ON documents(sha256);
CREATE INDEX idx_chunks_document_id ON chunks(document_id);
CREATE INDEX idx_chunks_project_id ON chunks(project_id);
CREATE INDEX idx_webhooks_project_id ON webhooks(project_id);
CREATE INDEX idx_api_keys_project_id ON api_keys(project_id);