#!/usr/bin/env python3
"""
Standardized Local API server for DocuFlow validation testing
Implements consistent response formats across all endpoints
"""

import asyncio
import hashlib
import json
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import uvicorn
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI(title="DocuFlow Standardized API Server", version="1.0.0")

# Database setup
DB_PATH = Path(__file__).parent / "test_db.sqlite"
conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
conn.row_factory = sqlite3.Row

# Initialize database
def init_db():
    # Drop existing tables to add updated_at columns
    conn.execute("DROP TABLE IF EXISTS chunks")
    conn.execute("DROP TABLE IF EXISTS documents")
    conn.execute("DROP TABLE IF EXISTS webhooks")
    conn.execute("DROP TABLE IF EXISTS api_keys")
    conn.execute("DROP TABLE IF EXISTS projects")
    
    conn.execute("""
        CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
    
    conn.execute("""
        CREATE TABLE api_keys (
            key TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            revoked_at INTEGER,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    
    conn.execute("""
        CREATE TABLE documents (
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
        CREATE TABLE chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content_md TEXT NOT NULL,
            page_start INTEGER,
            page_end INTEGER,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    """)
    
    conn.execute("""
        CREATE TABLE webhooks (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            url TEXT NOT NULL,
            secret TEXT NOT NULL,
            events TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
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

# Standardized response helpers
def success_response(data: Dict[str, Any], message: str = "Success") -> Dict[str, Any]:
    """Create standardized success response"""
    return {
        "success": True,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000)
    }

def error_response(message: str, code: str = "ERROR", details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create standardized error response"""
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details
        },
        "timestamp": int(time.time() * 1000)
    }

def format_project(project_row: sqlite3.Row) -> Dict[str, Any]:
    """Format project data consistently"""
    return {
        "id": project_row["id"],
        "name": project_row["name"],
        "created_at": project_row["created_at"],
        "updated_at": project_row["updated_at"]
    }

def format_api_key(key_row: sqlite3.Row) -> Dict[str, Any]:
    """Format API key data consistently"""
    return {
        "key": key_row["key"],
        "project_id": key_row["project_id"],
        "created_at": key_row["created_at"],
        "updated_at": key_row["updated_at"],
        "revoked_at": key_row["revoked_at"]
    }

def format_document(doc_row: sqlite3.Row, include_upload_url: bool = False) -> Dict[str, Any]:
    """Format document data consistently"""
    data = {
        "id": doc_row["id"],
        "project_id": doc_row["project_id"],
        "source_name": doc_row["source_name"],
        "content_type": doc_row["content_type"],
        "sha256": doc_row["sha256"],
        "status": doc_row["status"],
        "chunk_count": doc_row["chunk_count"],
        "error": doc_row["error"],
        "created_at": doc_row["created_at"],
        "updated_at": doc_row["updated_at"]
    }
    
    if include_upload_url and doc_row["status"] in ["CREATED", "UPLOADED"]:
        data["upload_url"] = generate_upload_url(doc_row["id"])
    
    return data

def format_webhook(webhook_row: sqlite3.Row) -> Dict[str, Any]:
    """Format webhook data consistently"""
    return {
        "id": webhook_row["id"],
        "project_id": webhook_row["project_id"],
        "url": webhook_row["url"],
        "events": json.loads(webhook_row["events"]),
        "active": bool(webhook_row["active"]),
        "created_at": webhook_row["created_at"],
        "updated_at": webhook_row["updated_at"]
    }

# Helper functions
def get_project_from_api_key(api_key: Optional[str]) -> Optional[str]:
    """Get project ID from API key"""
    if not api_key:
        return None
    if not api_key.startswith("Bearer "):
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

# API endpoints with standardized responses
@app.post("/v1/projects")
async def create_project(project: ProjectCreate):
    """Create a new project"""
    project_id = str(uuid.uuid4())
    now = int(time.time() * 1000)
    
    conn.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (project_id, project.name, now, now)
    )
    conn.commit()
    
    # Return formatted project data
    cursor = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    project_row = cursor.fetchone()
    
    return success_response(
        data=format_project(project_row),
        message="Project created successfully"
    )

@app.post("/v1/api-keys")
async def create_api_key(api_key_create: ApiKeyCreate):
    """Create a new API key"""
    # Verify project exists
    cursor = conn.execute("SELECT id FROM projects WHERE id = ?", (api_key_create.project_id,))
    if not cursor.fetchone():
        return JSONResponse(
            status_code=404,
            content=error_response("Project not found", "PROJECT_NOT_FOUND")
        )
    
    key = f"sk_{str(uuid.uuid4()).replace('-', '')}"
    now = int(time.time() * 1000)
    
    conn.execute(
        "INSERT INTO api_keys (key, project_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (key, api_key_create.project_id, now, now)
    )
    conn.commit()
    
    # Return formatted API key data
    cursor = conn.execute("SELECT * FROM api_keys WHERE key = ?", (key,))
    key_row = cursor.fetchone()
    
    return success_response(
        data=format_api_key(key_row),
        message="API key created successfully"
    )

@app.post("/v1/documents")
async def create_document(
    document: DocumentCreate,
    authorization: str = Header(None)
):
    """Create a new document"""
    # Check for missing or malformed Authorization header
    if not authorization:
        return JSONResponse(
            status_code=401,
            content=error_response("Missing API key", "MISSING_API_KEY")
        )
    
    if not authorization.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content=error_response("Missing API key", "MISSING_API_KEY")
        )
    
    project_id = get_project_from_api_key(authorization)
    if not project_id:
        return JSONResponse(
            status_code=403,
            content=error_response("Invalid API key", "INVALID_API_KEY")
        )
    
    if document.project_id != project_id:
        return JSONResponse(
            status_code=403,
            content=error_response("Project ID mismatch", "PROJECT_MISMATCH")
        )
    
    # Check for duplicate
    cursor = conn.execute(
        "SELECT id, status FROM documents WHERE project_id = ? AND sha256 = ? AND status != 'DELETED'",
        (project_id, document.sha256)
    )
    existing = cursor.fetchone()
    
    if existing:
        # Return existing document with dedup flag
        cursor = conn.execute("SELECT * FROM documents WHERE id = ?", (existing[0],))
        doc_row = cursor.fetchone()
        
        return success_response(
            data={
                **format_document(doc_row, include_upload_url=True),
                "deduped": True
            },
            message="Document already exists"
        )
    
    # Create new document
    document_id = str(uuid.uuid4())
    r2_key = f"{project_id}/{document_id}/{document.source_name}"
    now = int(time.time() * 1000)
    
    conn.execute(
        """INSERT INTO documents 
           (id, project_id, source_name, content_type, sha256, r2_key, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'CREATED', ?, ?)""",
        (document_id, project_id, document.source_name, document.content_type, 
         document.sha256, r2_key, now, now)
    )
    conn.commit()
    
    # Return formatted document data
    cursor = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
    doc_row = cursor.fetchone()
    
    return success_response(
        data=format_document(doc_row, include_upload_url=True),
        message="Document created successfully"
    )

@app.get("/v1/documents/{document_id}")
async def get_document(
    document_id: str,
    authorization: str = Header(None)
):
    """Get document status"""
    # Check for missing or malformed Authorization header
    if not authorization:
        return JSONResponse(
            status_code=401,
            content=error_response("Missing API key", "MISSING_API_KEY")
        )
    
    if not authorization.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content=error_response("Missing API key", "MISSING_API_KEY")
        )
    
    project_id = get_project_from_api_key(authorization)
    if not project_id:
        return JSONResponse(
            status_code=403,
            content=error_response("Invalid API key", "INVALID_API_KEY")
        )
    
    cursor = conn.execute(
        """SELECT * FROM documents 
           WHERE id = ? AND project_id = ? AND status != 'DELETED'""",
        (document_id, project_id)
    )
    doc_row = cursor.fetchone()
    
    if not doc_row:
        return JSONResponse(
            status_code=404,
            content=error_response("Document not found", "DOCUMENT_NOT_FOUND")
        )
    
    return success_response(
        data=format_document(doc_row, include_upload_url=True),
        message="Document retrieved successfully"
    )

@app.put("/v1/documents/{document_id}/upload")
async def upload_document(
    document_id: str,
    authorization: str = Header(None),
    file: UploadFile = File(...)
):
    """Upload document file"""
    # Check for missing or malformed Authorization header
    if not authorization:
        return JSONResponse(
            status_code=401,
            content=error_response("Missing API key", "MISSING_API_KEY")
        )
    
    if not authorization.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content=error_response("Missing API key", "MISSING_API_KEY")
        )
    
    project_id = get_project_from_api_key(authorization)
    if not project_id:
        return JSONResponse(
            status_code=403,
            content=error_response("Invalid API key", "INVALID_API_KEY")
        )
    
    # Verify document exists and is in correct state
    cursor = conn.execute(
        "SELECT status FROM documents WHERE id = ? AND project_id = ? AND status != 'DELETED'",
        (document_id, project_id)
    )
    doc = cursor.fetchone()
    
    if not doc:
        return JSONResponse(
            status_code=404,
            content=error_response("Document not found", "DOCUMENT_NOT_FOUND")
        )
    
    if doc[0] not in ["CREATED", "UPLOADED"]:
        return JSONResponse(
            status_code=400,
            content=error_response("Document not in uploadable state", "INVALID_DOCUMENT_STATE")
        )
    
    # Read file content
    try:
        content = await file.read()
        if len(content) == 0:
            return JSONResponse(
                status_code=400,
                content=error_response("Empty file", "EMPTY_FILE")
            )
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content=error_response("Failed to read file", "FILE_READ_ERROR", {"details": str(e)})
        )
    
    # Update document status
    now = int(time.time() * 1000)
    conn.execute(
        "UPDATE documents SET status = 'UPLOADED', updated_at = ? WHERE id = ?",
        (now, document_id)
    )
    conn.commit()
    
    return success_response(
        data={"status": "UPLOADED"},
        message="Document uploaded successfully"
    )

@app.post("/v1/documents/{document_id}/complete")
async def complete_document(
    document_id: str,
    authorization: str = Header(None)
):
    """Mark document as ready for processing"""
    # Check for missing or malformed Authorization header
    if not authorization:
        return JSONResponse(
            status_code=401,
            content=error_response("Missing API key", "MISSING_API_KEY")
        )
    
    if not authorization.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content=error_response("Missing API key", "MISSING_API_KEY")
        )
    
    project_id = get_project_from_api_key(authorization)
    if not project_id:
        return JSONResponse(
            status_code=403,
            content=error_response("Invalid API key", "INVALID_API_KEY")
        )
    
    # Verify document exists and is uploaded
    cursor = conn.execute(
        "SELECT status FROM documents WHERE id = ? AND project_id = ? AND status != 'DELETED'",
        (document_id, project_id)
    )
    doc = cursor.fetchone()
    
    if not doc:
        return JSONResponse(
            status_code=404,
            content=error_response("Document not found", "DOCUMENT_NOT_FOUND")
        )
    
    if doc[0] != "UPLOADED":
        return JSONResponse(
            status_code=400,
            content=error_response("Upload required first", "UPLOAD_REQUIRED")
        )
    
    # Update status to processing
    now = int(time.time() * 1000)
    conn.execute(
        "UPDATE documents SET status = 'PROCESSING', updated_at = ? WHERE id = ?",
        (now, document_id)
    )
    conn.commit()
    
    # Process document synchronously for reliable testing
    try:
        await process_document_synchronously(document_id, project_id)
        final_status = "READY"
        message = "Document processed successfully"
    except Exception as e:
        print(f"Document processing failed: {e}")
        final_status = "FAILED"
        message = f"Document processing failed: {str(e)}"
    
    return success_response(
        data={"status": final_status},
        message=message
    )

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
        now = int(time.time() * 1000)
        for chunk in chunks:
            chunk_id = str(uuid.uuid4())
            thread_conn.execute(
                """INSERT INTO chunks (id, document_id, project_id, chunk_index, content_md, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (chunk_id, document_id, project_id, chunk["chunk_index"], chunk["content_md"], now, now)
            )
        
        # Update document status to READY
        thread_conn.execute(
            "UPDATE documents SET status = 'READY', chunk_count = ?, updated_at = ?, error = NULL WHERE id = ?",
            (len(chunks), now, document_id)
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
    # Check for missing or malformed Authorization header
    if not authorization:
        return JSONResponse(
            status_code=401,
            content=error_response("Missing API key", "MISSING_API_KEY")
        )
    
    if not authorization.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content=error_response("Missing API key", "MISSING_API_KEY")
        )
    
    project_id = get_project_from_api_key(authorization)
    if not project_id:
        return JSONResponse(
            status_code=403,
            content=error_response("Invalid API key", "INVALID_API_KEY")
        )
    
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
            "id": row["id"],
            "document_id": row["document_id"],
            "chunk_index": row["chunk_index"],
            "content_md": row["content_md"],
            "page_start": row["page_start"],
            "page_end": row["page_end"]
        })
        citations.append({
            "document_id": row["document_id"],
            "chunk_id": row["id"],
            "chunk_index": row["chunk_index"],
            "page_start": row["page_start"],
            "page_end": row["page_end"]
        })
    
    # Generate answer if requested
    if query_request.mode == "answer":
        context = "\n\n".join(chunk["content_md"] for chunk in chunks)
        answer = f"Based on the document content, here's what I found: {query_request.query}"
        if context:
            answer += f" The relevant information includes: {context[:200]}..."
        else:
            answer = "I don't have enough information to answer that question."
        
        return success_response(
            data={
                "mode": "answer",
                "answer": answer,
                "chunks": chunks,
                "citations": citations
            },
            message="Query processed successfully"
        )
    
    return success_response(
        data={
            "mode": query_request.mode,
            "chunks": chunks,
            "citations": citations
        },
        message="Query processed successfully"
    )

@app.post("/v1/webhooks")
async def create_webhook(
    webhook: WebhookCreate,
    authorization: str = Header(None)
):
    """Create webhook"""
    # Check for missing or malformed Authorization header
    if not authorization:
        return JSONResponse(
            status_code=401,
            content=error_response("Missing API key", "MISSING_API_KEY")
        )
    
    if not authorization.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content=error_response("Missing API key", "MISSING_API_KEY")
        )
    
    project_id = get_project_from_api_key(authorization)
    if not project_id:
        return JSONResponse(
            status_code=403,
            content=error_response("Invalid API key", "INVALID_API_KEY")
        )
    
    if webhook.project_id != project_id:
        return JSONResponse(
            status_code=403,
            content=error_response("Project ID mismatch", "PROJECT_MISMATCH")
        )
    
    # Validate webhook URL format
    if not webhook.url or not webhook.url.startswith(('http://', 'https://')):
        return JSONResponse(
            status_code=400,
            content=error_response("Invalid webhook URL format", "INVALID_WEBHOOK_URL")
        )
    
    # Validate events
    if not webhook.events or len(webhook.events) == 0:
        return JSONResponse(
            status_code=400,
            content=error_response("At least one event must be specified", "MISSING_EVENTS")
        )
    
    webhook_id = str(uuid.uuid4())
    secret = str(uuid.uuid4()).replace("-", "")
    now = int(time.time() * 1000)
    events_json = json.dumps(webhook.events)
    
    try:
        conn.execute(
            """INSERT INTO webhooks (id, project_id, url, secret, events, active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (webhook_id, project_id, webhook.url, secret, events_json,
             1 if webhook.active else 0, now, now)
        )
        conn.commit()
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=error_response("Failed to create webhook", "WEBHOOK_CREATION_ERROR", {"details": str(e)})
        )
    
    # Return formatted webhook data
    cursor = conn.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,))
    webhook_row = cursor.fetchone()
    
    return success_response(
        data=format_webhook(webhook_row),
        message="Webhook created successfully"
    )

# Debug endpoint to check request details
@app.post("/debug/upload-test")
async def debug_upload_test(
    request: Request,
    authorization: str = Header(None),
    file: UploadFile = File(...)
):
    """Debug endpoint to test upload issues"""
    logger.info(f"Authorization header: {authorization}")
    logger.info(f"File: {file.filename}, size: {file.size}, content_type: {file.content_type}")
    
    try:
        content = await file.read()
        logger.info(f"File content length: {len(content)}")
        return success_response({
            "filename": file.filename,
            "content_length": len(content),
            "content_type": file.content_type
        }, "Debug upload successful")
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return JSONResponse(
            status_code=400,
            content=error_response("Upload failed", "UPLOAD_DEBUG_ERROR", {"details": str(e)})
        )

# Add exception handler for validation errors
@app.exception_handler(422)
async def validation_exception_handler(request: Request, exc):
    """Handle validation errors with proper error response"""
    logger.error(f"Validation error: {exc}")
    return JSONResponse(
        status_code=422,
        content=error_response("Validation error", "VALIDATION_ERROR", {"details": str(exc)})
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8787, log_level="debug")