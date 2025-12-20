#!/usr/bin/env python3
"""
Local API server for DocuFlow validation testing
Simulates Cloudflare Workers API behavior
"""

import asyncio
import hashlib
import json
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import uvicorn
from fastapi import FastAPI, HTTPException, Header, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="DocuFlow Local API Server", version="1.0.0")

# Database setup
DB_PATH = Path(__file__).parent / "test_db.sqlite"
conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
conn.row_factory = sqlite3.Row

# Initialize database
def init_db():
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            revoked_at INTEGER,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            content_type TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            r2_key TEXT,
            status TEXT NOT NULL,
            chunk_count INTEGER DEFAULT 0,
            error TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content_md TEXT NOT NULL,
            page_start INTEGER,
            page_end INTEGER,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webhooks (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            url TEXT NOT NULL,
            secret TEXT NOT NULL,
            events TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    
    conn.commit()

init_db()

# Pydantic models
class ProjectCreate(BaseModel):
    name: str

class ApiKeyCreate(BaseModel):
    project_id: str
    name: str

class DocumentCreate(BaseModel):
    project_id: str
    source_name: str
    content_type: str
    sha256: str

class DocumentComplete(BaseModel):
    document_id: str

class QueryRequest(BaseModel):
    query: str
    document_id: Optional[str] = None
    mode: str = "chunks"
    top_k: int = 5

class WebhookCreate(BaseModel):
    project_id: str
    url: str
    events: list[str]
    active: bool = True

# Helper functions
def get_project_from_api_key(api_key: Optional[str]) -> Optional[str]:
    """Get project ID from API key"""
    if not api_key or not api_key.startswith("Bearer "):
        return None
    key = api_key[7:]
    
    cursor = conn.execute(
        "SELECT project_id FROM api_keys WHERE key = ? AND revoked_at IS NULL",
        (key,)
    )
    row = cursor.fetchone()
    return row[0] if row else None

def generate_upload_url(document_id: str) -> str:
    """Generate upload URL for document"""
    return f"http://localhost:8787/v1/documents/{document_id}/upload"

# API endpoints
@app.post("/v1/projects")
async def create_project(project: ProjectCreate):
    """Create a new project"""
    project_id = str(uuid.uuid4())
    created_at = int(time.time() * 1000)
    
    conn.execute(
        "INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)",
        (project_id, project.name, created_at)
    )
    conn.commit()
    
    return {"id": project_id, "name": project.name}

@app.post("/v1/api-keys")
async def create_api_key(api_key_create: ApiKeyCreate):
    """Create a new API key"""
    # Verify project exists
    cursor = conn.execute("SELECT id FROM projects WHERE id = ?", (api_key_create.project_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Project not found")
    
    key = f"sk_{str(uuid.uuid4()).replace('-', '')}"
    created_at = int(time.time() * 1000)
    
    conn.execute(
        "INSERT INTO api_keys (key, project_id, created_at) VALUES (?, ?, ?)",
        (key, api_key_create.project_id, created_at)
    )
    conn.commit()
    
    return {"key": key}

@app.post("/v1/documents")
async def create_document(
    document: DocumentCreate,
    authorization: str = Header(None)
):
    """Create a new document"""
    project_id = get_project_from_api_key(authorization)
    if not project_id:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    if document.project_id != project_id:
        raise HTTPException(status_code=403, detail="Project ID mismatch")
    
    # Check for duplicate
    cursor = conn.execute(
        "SELECT id, status FROM documents WHERE project_id = ? AND sha256 = ? AND status != 'DELETED'",
        (project_id, document.sha256)
    )
    existing = cursor.fetchone()
    
    if existing:
        return {
            "document_id": existing[0],
            "status": existing[1],
            "upload_url": generate_upload_url(existing[0]),
            "deduped": True
        }
    
    # Create new document
    document_id = str(uuid.uuid4())
    r2_key = f"{project_id}/{document_id}/{document.source_name}"
    created_at = int(time.time() * 1000)
    
    conn.execute(
        """INSERT INTO documents 
           (id, project_id, source_name, content_type, sha256, r2_key, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'CREATED', ?, ?)""",
        (document_id, project_id, document.source_name, document.content_type, 
         document.sha256, r2_key, created_at, created_at)
    )
    conn.commit()
    
    return {
        "document_id": document_id,
        "status": "CREATED",
        "upload_url": generate_upload_url(document_id)
    }

@app.get("/v1/documents/{document_id}")
async def get_document(
    document_id: str,
    authorization: str = Header(None)
):
    """Get document status"""
    project_id = get_project_from_api_key(authorization)
    if not project_id:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    cursor = conn.execute(
        """SELECT id, status, chunk_count, error, source_name, content_type, sha256, created_at, updated_at 
           FROM documents WHERE id = ? AND project_id = ?""",
        (document_id, project_id)
    )
    doc = cursor.fetchone()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    result = dict(doc)
    if result["status"] in ["CREATED", "UPLOADED"]:
        result["upload_url"] = generate_upload_url(document_id)
    
    return result

@app.put("/v1/documents/{document_id}/upload")
async def upload_document(
    document_id: str,
    authorization: str = Header(None),
    file: UploadFile = File(...)
):
    """Upload document file"""
    project_id = get_project_from_api_key(authorization)
    if not project_id:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    # Verify document exists and is in correct state
    cursor = conn.execute(
        "SELECT status FROM documents WHERE id = ? AND project_id = ? AND status != 'DELETED'",
        (document_id, project_id)
    )
    doc = cursor.fetchone()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if doc[0] != "CREATED":
        raise HTTPException(status_code=400, detail="Document not in CREATED state")
    
    # Read file content
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    
    # Update document status
    updated_at = int(time.time() * 1000)
    conn.execute(
        "UPDATE documents SET status = 'UPLOADED', updated_at = ? WHERE id = ?",
        (updated_at, document_id)
    )
    conn.commit()
    
    return {"ok": True, "status": "UPLOADED"}

@app.post("/v1/documents/{document_id}/complete")
async def complete_document(
    document_id: str,
    authorization: str = Header(None)
):
    """Mark document as ready for processing"""
    project_id = get_project_from_api_key(authorization)
    if not project_id:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    # Verify document exists and is uploaded
    cursor = conn.execute(
        "SELECT status FROM documents WHERE id = ? AND project_id = ? AND status != 'DELETED'",
        (document_id, project_id)
    )
    doc = cursor.fetchone()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if doc[0] != "UPLOADED":
        raise HTTPException(status_code=400, detail="Upload required first")
    
    # Update status to processing
    updated_at = int(time.time() * 1000)
    conn.execute(
        "UPDATE documents SET status = 'PROCESSING', updated_at = ? WHERE id = ?",
        (updated_at, document_id)
    )
    conn.commit()
    
    # Process document synchronously for reliable testing
    try:
        await process_document_synchronously(document_id, project_id)
        final_status = "READY"
    except Exception as e:
        print(f"Document processing failed: {e}")
        final_status = "FAILED"
    
    return {"ok": True, "status": final_status}

async def process_document_synchronously(document_id: str, project_id: str):
    """Process document synchronously for reliable testing"""
    try:
        # Create a new database connection for this thread
        import sqlite3
        thread_conn = sqlite3.connect(str(DB_PATH), check_same_thread=True)
        thread_conn.row_factory = sqlite3.Row
        
        # Simulate processing time (shorter for testing)
        await asyncio.sleep(0.5)
        
        # Simulate engine call - 90% success rate
        import random
        if random.random() < 0.1:  # 10% failure rate for testing
            raise Exception("Simulated engine failure")
        
        # Create realistic chunks with varied content
        chunks = [
            {"content_md": "This document contains important information about the project requirements and specifications.", "chunk_index": 0},
            {"content_md": "The system should process documents efficiently and extract meaningful content for vector search.", "chunk_index": 1},
            {"content_md": "Key features include document upload, processing, chunking, embedding generation, and vector storage.", "chunk_index": 2},
            {"content_md": "The architecture follows an event-driven design with queue-based processing for scalability.", "chunk_index": 3}
        ]
        
        # Insert chunks
        created_at = int(time.time() * 1000)
        for chunk in chunks:
            chunk_id = str(uuid.uuid4())
            thread_conn.execute(
                """INSERT INTO chunks (id, document_id, project_id, chunk_index, content_md, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (chunk_id, document_id, project_id, chunk["chunk_index"], chunk["content_md"], created_at)
            )
        
        # Update document status to READY
        thread_conn.execute(
            "UPDATE documents SET status = 'READY', chunk_count = ?, updated_at = ?, error = NULL WHERE id = ?",
            (len(chunks), created_at, document_id)
        )
        thread_conn.commit()
        thread_conn.close()
        
        print(f"✅ Document {document_id} processed successfully with {len(chunks)} chunks")
        
    except Exception as e:
        # Update document status to FAILED with error
        error_at = int(time.time() * 1000)
        try:
            thread_conn.execute(
                "UPDATE documents SET status = 'FAILED', error = ?, updated_at = ? WHERE id = ?",
                (str(e), error_at, document_id)
            )
            thread_conn.commit()
            thread_conn.close()
        except:
            pass  # Connection might already be closed
        print(f"❌ Document {document_id} processing failed: {e}")
        raise  # Re-raise the exception so the caller knows it failed

@app.post("/v1/query")
async def query_documents(
    query_request: QueryRequest,
    authorization: str = Header(None)
):
    """Query documents"""
    project_id = get_project_from_api_key(authorization)
    if not project_id:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    # Simple mock query - find chunks containing query terms
    query_terms = query_request.query.lower().split()
    
    sql = """SELECT c.id, c.document_id, c.chunk_index, c.content_md, c.page_start, c.page_end, d.source_name
             FROM chunks c
             JOIN documents d ON c.document_id = d.id
             WHERE c.project_id = ? AND d.status = 'READY'"""
    
    params = [project_id]
    
    if query_request.document_id:
        sql += " AND c.document_id = ?"
        params.append(query_request.document_id)
    
    sql += " ORDER BY c.chunk_index LIMIT ?"
    params.append(query_request.top_k)
    
    cursor = conn.execute(sql, params)
    rows = cursor.fetchall()
    
    # Filter by relevance (simple keyword matching)
    relevant_chunks = []
    for row in rows:
        content = row["content_md"].lower()
        relevance_score = sum(1 for term in query_terms if term in content)
        if relevance_score > 0:
            relevant_chunks.append({
                "chunk": dict(row),
                "relevance": relevance_score
            })
    
    # Sort by relevance and take top results
    relevant_chunks.sort(key=lambda x: x["relevance"], reverse=True)
    top_chunks = relevant_chunks[:query_request.top_k]
    
    chunks = []
    citations = []
    
    for item in top_chunks:
        row = item["chunk"]
        chunks.append({
            "id": row[0],
            "document_id": row[1],
            "chunk_index": row[2],
            "content_md": row[3],
            "page_start": row[4],
            "page_end": row[5]
        })
        citations.append({
            "document_id": row[1],
            "chunk_id": row[0],
            "chunk_index": row[2],
            "page_start": row[4],
            "page_end": row[5]
        })
    
    # Generate answer if requested
    if query_request.mode == "answer":
        context = "\n\n".join(chunk["content_md"] for chunk in chunks)
        answer = f"Based on the document content, here's what I found: {query_request.query}"
        if context:
            answer += f" The relevant information includes: {context[:200]}..."
        else:
            answer = "I don't have enough information to answer that question."
        
        return {
            "mode": "answer",
            "answer": answer,
            "chunks": chunks,
            "citations": citations
        }
    
    return {
        "mode": query_request.mode,
        "chunks": chunks,
        "citations": citations
    }

@app.post("/v1/webhooks")
async def create_webhook(
    webhook: WebhookCreate,
    authorization: str = Header(None)
):
    """Create webhook"""
    project_id = get_project_from_api_key(authorization)
    if not project_id:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    if webhook.project_id != project_id:
        raise HTTPException(status_code=403, detail="Project ID mismatch")
    
    webhook_id = str(uuid.uuid4())
    secret = str(uuid.uuid4()).replace("-", "")
    created_at = int(time.time() * 1000)
    events_json = json.dumps(webhook.events)
    
    conn.execute(
        """INSERT INTO webhooks (id, project_id, url, secret, events, active, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (webhook_id, project_id, webhook.url, secret, events_json, 
         1 if webhook.active else 0, created_at)
    )
    conn.commit()
    
    return {"webhook_id": webhook_id, "secret": secret}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8787)