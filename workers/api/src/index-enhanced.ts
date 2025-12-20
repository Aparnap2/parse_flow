import { Hono } from "hono";
import { cors } from "hono/cors";
import { 
  CreateDocumentSchema, 
  BatchCreateSchema, 
  QuerySchema, 
  IngestJobSchema,
  WebhookEventSchema 
} from "../../../packages/shared/src/types";

type Env = {
  DB: D1Database;
  BUCKET: R2Bucket;
  VECTORIZE: VectorizeIndex;
  INGEST_QUEUE: Queue;
  EVENTS_QUEUE: Queue;
  AI: Ai;
  BASE_URL: string;
};

const app = new Hono<{ Bindings: Env; Variables: { projectId: string } }>();
app.use("/*", cors());

// Enhanced error types
class ExternalServiceError extends Error {
  constructor(service: string, message: string, public statusCode: number = 500) {
    super(`External service error (${service}): ${message}`);
    this.name = 'ExternalServiceError';
  }
}

class VectorizeError extends ExternalServiceError {
  constructor(message: string, statusCode: number = 500) {
    super('Vectorize', message, statusCode);
    this.name = 'VectorizeError';
  }
}

class AIError extends ExternalServiceError {
  constructor(message: string, statusCode: number = 500) {
    super('Workers AI', message, statusCode);
    this.name = 'AIError';
  }
}

class R2Error extends ExternalServiceError {
  constructor(message: string, statusCode: number = 500) {
    super('R2', message, statusCode);
    this.name = 'R2Error';
  }
}

// Standardized error response helper
function errorResponse(c: any, message: string, code: string = "ERROR", status: number = 500, details?: any) {
  return c.json({
    success: false,
    error: {
      code,
      message,
      details,
      service: 'api'
    },
    timestamp: Date.now()
  }, status);
}

function successResponse(c: any, data: any, message: string = "Success") {
  return c.json({
    success: true,
    message,
    data,
    timestamp: Date.now()
  });
}

// Enhanced error handling wrapper for external service calls
async function withErrorHandling<T>(
  operation: () => Promise<T>,
  serviceName: string,
  context: string,
  c: any
): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error(`Error in ${serviceName} during ${context}:`, errorMessage);
    
    if (error instanceof ExternalServiceError) {
      throw error; // Re-throw our custom errors
    }
    
    // Create appropriate error based on service
    if (serviceName === 'Vectorize') {
      throw new VectorizeError(`Failed to ${context}: ${errorMessage}`);
    } else if (serviceName === 'Workers AI') {
      throw new AIError(`Failed to ${context}: ${errorMessage}`);
    } else if (serviceName === 'R2') {
      throw new R2Error(`Failed to ${context}: ${errorMessage}`);
    } else {
      throw new ExternalServiceError(serviceName, `Failed to ${context}: ${errorMessage}`);
    }
  }
}

async function requireApiKey(c: any, next: any) {
  const raw = c.req.header("Authorization") || "";
  const key = raw.startsWith("Bearer ") ? raw.slice(7) : "";
  if (!key) return errorResponse(c, "Missing API key", "MISSING_API_KEY", 401);

  try {
    const row = await c.env.DB.prepare("SELECT project_id FROM api_keys WHERE key = ? AND revoked_at IS NULL")
      .bind(key)
      .first();

    if (!row) return errorResponse(c, "Invalid API key", "INVALID_API_KEY", 403);
    c.set("projectId", String(row.project_id));
    return next();
  } catch (error) {
    console.error("Database error during API key validation:", error);
    return errorResponse(c, "Database error during authentication", "DB_ERROR", 500);
  }
}

// Enhanced R2 operations with error handling
async function getR2Object(c: any, key: string): Promise<any> {
  return await withErrorHandling(
    async () => {
      const obj = await c.env.BUCKET.get(key);
      if (!obj) {
        throw new R2Error(`Object not found: ${key}`, 404);
      }
      return obj;
    },
    'R2',
    `get object ${key}`,
    c
  );
}

async function putR2Object(c: any, key: string, data: ArrayBuffer, contentType: string): Promise<void> {
  return await withErrorHandling(
    async () => {
      await c.env.BUCKET.put(key, data, {
        httpMetadata: { contentType },
      });
    },
    'R2',
    `put object ${key}`,
    c
  );
}

async function deleteR2Object(c: any, key: string): Promise<void> {
  return await withErrorHandling(
    async () => {
      await c.env.BUCKET.delete(key);
    },
    'R2',
    `delete object ${key}`,
    c
  );
}

// Enhanced Vectorize operations with error handling
async function queryVectorize(
  c: any,
  queryVector: number[],
  topK: number,
  namespace: string,
  filter?: any
): Promise<any> {
  return await withErrorHandling(
    async () => {
      const results = await c.env.VECTORIZE.query(queryVector, {
        topK,
        namespace,
        returnMetadata: "all",
        filter,
      });
      
      if (!results || !Array.isArray(results.matches)) {
        throw new VectorizeError("Invalid response format from Vectorize");
      }
      
      return results;
    },
    'Vectorize',
    'query vectors',
    c
  );
}

async function generateEmbedding(c: any, text: string): Promise<number[]> {
  return await withErrorHandling(
    async () => {
      const emb = await c.env.AI.run("@cf/baai/bge-base-en-v1.5", { text: [text] });
      
      if (!emb || !Array.isArray(emb.data) || emb.data.length === 0) {
        throw new AIError("Invalid embedding response format");
      }
      
      return emb.data[0];
    },
    'Workers AI',
    `generate embedding for text: "${text.substring(0, 50)}..."`,
    c
  );
}

async function generateAnswer(c: any, context: string, query: string): Promise<string> {
  return await withErrorHandling(
    async () => {
      // Limit context to avoid token overflow
      const maxContextLength = 4000;
      const truncatedContext = context.length > maxContextLength
        ? context.substring(0, maxContextLength) + "..."
        : context;
      
      const resp = await c.env.AI.run("@cf/qwen/qwen-3-3b", {
        messages: [
          { role: "system", content: `Answer using only the provided context. If the answer is not in the context, say "I don't have enough information to answer that question."

Context:
${truncatedContext}` },
          { role: "user", content: query },
        ],
      });
      
      if (!resp || typeof (resp as any).response !== 'string') {
        throw new AIError("Invalid answer generation response format");
      }
      
      return (resp as any).response;
    },
    'Workers AI',
    'generate answer',
    c
  );
}

// Enhanced database operations with error handling
async function getDocumentById(c: any, docId: string, projectId: string): Promise<any> {
  return await withErrorHandling(
    async () => {
      const doc = await c.env.DB.prepare(
        "SELECT id, status, chunk_count, error, source_name, content_type, sha256, created_at, updated_at FROM documents WHERE id = ? AND project_id = ?"
      ).bind(docId, projectId).first();
      
      if (!doc) {
        throw new Error("Document not found");
      }
      
      return doc;
    },
    'D1 Database',
    `fetch document ${docId}`,
    c
  );
}

async function updateDocumentStatus(
  c: any,
  docId: string,
  status: string,
  error?: string
): Promise<void> {
  return await withErrorHandling(
    async () => {
      const now = Date.now();
      if (error) {
        await c.env.DB.prepare(
          "UPDATE documents SET status = ?, error = ?, updated_at = ? WHERE id = ?"
        ).bind(status, error, now, docId).run();
      } else {
        await c.env.DB.prepare(
          "UPDATE documents SET status = ?, error = NULL, updated_at = ? WHERE id = ?"
        ).bind(status, now, docId).run();
      }
    },
    'D1 Database',
    `update document ${docId} status to ${status}`,
    c
  );
}

// Project management
app.post("/v1/projects", async (c) => {
  try {
    const body = await c.req.json();
    const id = crypto.randomUUID();
    const name = body?.name || "Untitled";
    
    await c.env.DB.prepare("INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)")
      .bind(id, name, Date.now())
      .run();
    
    return successResponse(c, { id, name }, "Project created successfully");
  } catch (error) {
    console.error("Error creating project:", error);
    return errorResponse(c, "Failed to create project", "PROJECT_CREATE_ERROR", 500);
  }
});

// API key management
app.post("/v1/api-keys", async (c) => {
  try {
    const body = await c.req.json();
    const projectId = body?.project_id;
    if (!projectId) return errorResponse(c, "project_id required", "VALIDATION_ERROR", 400);

    // Verify project exists
    const project = await c.env.DB.prepare("SELECT id FROM projects WHERE id = ?")
      .bind(projectId).first();
    if (!project) return errorResponse(c, "Project not found", "PROJECT_NOT_FOUND", 404);

    const key = "sk_" + crypto.randomUUID().replaceAll("-", "");
    await c.env.DB.prepare("INSERT INTO api_keys (key, project_id, created_at) VALUES (?, ?, ?)")
      .bind(key, projectId, Date.now())
      .run();
    
    return successResponse(c, { key }, "API key created successfully");
  } catch (error) {
    console.error("Error creating API key:", error);
    return errorResponse(c, "Failed to create API key", "API_KEY_CREATE_ERROR", 500);
  }
});

// Webhook registration
app.post("/v1/webhooks", requireApiKey, async (c) => {
  try {
    const projectId = c.get("projectId");
    const body = await c.req.json();
    const url = body?.url;
    if (!url) return errorResponse(c, "url required", "VALIDATION_ERROR", 400);

    // Validate URL format
    try {
      new URL(url);
    } catch {
      return errorResponse(c, "Invalid webhook URL format", "VALIDATION_ERROR", 400);
    }

    const id = crypto.randomUUID();
    const secret = crypto.randomUUID().replaceAll("-", "");
    
    await c.env.DB.prepare(
      "INSERT INTO webhooks (id, project_id, url, secret, created_at) VALUES (?, ?, ?, ?, ?)"
    ).bind(id, projectId, url, secret, Date.now()).run();

    return successResponse(c, { webhook_id: id, secret }, "Webhook created successfully");
  } catch (error) {
    console.error("Error creating webhook:", error);
    return errorResponse(c, "Failed to create webhook", "WEBHOOK_CREATE_ERROR", 500);
  }
});

// Single document creation
app.post("/v1/documents", requireApiKey, async (c) => {
  try {
    const projectId = c.get("projectId");
    const input = CreateDocumentSchema.parse(await c.req.json());

    const existing = await c.env.DB.prepare(
      "SELECT id, status FROM documents WHERE project_id = ? AND sha256 = ? AND status != 'DELETED'"
    ).bind(projectId, input.sha256).first();

    if (existing) {
      return successResponse(c, {
        document_id: String(existing.id),
        status: String(existing.status),
        upload_url: `${c.env.BASE_URL}/v1/documents/${existing.id}/upload`,
        deduped: true,
      }, "Document already exists");
    }

    const docId = crypto.randomUUID();
    const r2Key = `${projectId}/${docId}/${input.source_name}`;

    await c.env.DB.prepare(
      `INSERT INTO documents
       (id, project_id, source_name, content_type, sha256, r2_key, status, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, 'CREATED', ?, ?)`
    ).bind(docId, projectId, input.source_name, input.content_type, input.sha256, r2Key, Date.now(), Date.now()).run();

    return successResponse(c, {
      document_id: docId,
      status: "CREATED",
      upload_url: `${c.env.BASE_URL}/v1/documents/${docId}/upload`,
    }, "Document created successfully");
  } catch (error) {
    console.error("Error creating document:", error);
    if (error instanceof Error && error.name === 'ZodError') {
      return errorResponse(c, "Invalid request data", "VALIDATION_ERROR", 400);
    }
    return errorResponse(c, "Failed to create document", "DOCUMENT_CREATE_ERROR", 500);
  }
});

// Batch document creation
app.post("/v1/documents/batch", requireApiKey, async (c) => {
  try {
    const projectId = c.get("projectId");
    const input = BatchCreateSchema.parse(await c.req.json());

    const out: any[] = [];
    for (const d of input.documents) {
      const existing = await c.env.DB.prepare(
        "SELECT id, status FROM documents WHERE project_id = ? AND sha256 = ? AND status != 'DELETED'"
      ).bind(projectId, d.sha256).first();

      if (existing) {
        out.push({
          document_id: String(existing.id),
          status: String(existing.status),
          upload_url: `${c.env.BASE_URL}/v1/documents/${existing.id}/upload`,
          deduped: true,
        });
        continue;
      }

      const docId = crypto.randomUUID();
      const r2Key = `${projectId}/${docId}/${d.source_name}`;

      await c.env.DB.prepare(
        `INSERT INTO documents
         (id, project_id, source_name, content_type, sha256, r2_key, status, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, 'CREATED', ?, ?)`
      ).bind(docId, projectId, d.source_name, d.content_type, d.sha256, r2Key, Date.now(), Date.now()).run();

      out.push({
        document_id: docId,
        status: "CREATED",
        upload_url: `${c.env.BASE_URL}/v1/documents/${docId}/upload`,
      });
    }

    return successResponse(c, { documents: out }, "Batch documents created successfully");
  } catch (error) {
    console.error("Error creating batch documents:", error);
    if (error instanceof Error && error.name === 'ZodError') {
      return errorResponse(c, "Invalid request data", "VALIDATION_ERROR", 400);
    }
    return errorResponse(c, "Failed to create batch documents", "BATCH_CREATE_ERROR", 500);
  }
});

// Document upload endpoint
app.put("/v1/documents/:id/upload", requireApiKey, async (c) => {
  try {
    const projectId = c.get("projectId");
    const docId = c.req.param("id");

    const doc = await getDocumentById(c, docId, projectId);
    
    if (String(doc.status) !== "CREATED") {
      return errorResponse(c, "Document not in CREATED state", "INVALID_DOCUMENT_STATE", 400);
    }

    const body = await c.req.arrayBuffer();
    if (body.byteLength === 0) {
      return errorResponse(c, "Empty file", "EMPTY_FILE", 400);
    }

    // Upload to R2 with error handling
    await putR2Object(c, String(doc.r2_key), body, String(doc.content_type));

    // Update document status
    await updateDocumentStatus(c, docId, "UPLOADED");

    return successResponse(c, { status: "UPLOADED" }, "Document uploaded successfully");
  } catch (error) {
    console.error("Error uploading document:", error);
    
    if (error instanceof Error && error.message === "Document not found") {
      return errorResponse(c, "Document not found", "DOCUMENT_NOT_FOUND", 404);
    }
    
    return errorResponse(c, "Failed to upload document", "UPLOAD_ERROR", 500);
  }
});

// Document completion and processing
app.post("/v1/documents/:id/complete", requireApiKey, async (c) => {
  try {
    const projectId = c.get("projectId");
    const docId = c.req.param("id");

    const doc = await getDocumentById(c, docId, projectId);
    
    if (String(doc.status) !== "UPLOADED") {
      return errorResponse(c, "Upload required first", "UPLOAD_REQUIRED", 400);
    }

    await updateDocumentStatus(c, docId, "PROCESSING");

    const job = IngestJobSchema.parse({ project_id: projectId, document_id: docId });
    await c.env.INGEST_QUEUE.send(job);

    return successResponse(c, { status: "PROCESSING" }, "Document processing started");
  } catch (error) {
    console.error("Error completing document:", error);
    
    if (error instanceof Error && error.message === "Document not found") {
      return errorResponse(c, "Document not found", "DOCUMENT_NOT_FOUND", 404);
    }
    
    return errorResponse(c, "Failed to complete document", "COMPLETE_ERROR", 500);
  }
});

// Get document status
app.get("/v1/documents/:id", requireApiKey, async (c) => {
  try {
    const projectId = c.get("projectId");
    const docId = c.req.param("id");

    const doc = await getDocumentById(c, docId, projectId);
    
    // Add upload URL if document is in CREATED or UPLOADED status
    const status = String(doc.status);
    const response: any = { ...doc };
    
    if (status === 'CREATED' || status === 'UPLOADED') {
      response.upload_url = `${c.env.BASE_URL}/v1/documents/${docId}/upload`;
    }
    
    return successResponse(c, response, "Document retrieved successfully");
  } catch (error) {
    console.error("Error getting document:", error);
    
    if (error instanceof Error && error.message === "Document not found") {
      return errorResponse(c, "Document not found", "DOCUMENT_NOT_FOUND", 404);
    }
    
    return errorResponse(c, "Failed to get document", "GET_DOCUMENT_ERROR", 500);
  }
});

// Delete document
app.delete("/v1/documents/:id", requireApiKey, async (c) => {
  try {
    const projectId = c.get("projectId");
    const docId = c.req.param("id");

    const doc = await c.env.DB.prepare(
      "SELECT r2_key FROM documents WHERE id = ? AND project_id = ? AND status != 'DELETED'"
    ).bind(docId, projectId).first();
    
    if (!doc) return errorResponse(c, "Document not found", "DOCUMENT_NOT_FOUND", 404);

    // Delete from database first (safer operation)
    await c.env.DB.prepare("DELETE FROM chunks WHERE document_id = ? AND project_id = ?")
      .bind(docId, projectId).run();
    await c.env.DB.prepare("UPDATE documents SET status = 'DELETED', updated_at = ? WHERE id = ?")
      .bind(Date.now(), docId).run();

    // Delete from R2 (can fail independently)
    try {
      await deleteR2Object(c, String(doc.r2_key));
    } catch (r2Error) {
      console.error("Failed to delete R2 object, but document is marked as deleted:", r2Error);
      // Continue - document is already marked as deleted in DB
    }

    return successResponse(c, { ok: true }, "Document deleted successfully");
  } catch (error) {
    console.error("Error deleting document:", error);
    return errorResponse(c, "Failed to delete document", "DELETE_ERROR", 500);
  }
});

// Query endpoint with enhanced error handling
app.post("/v1/query", requireApiKey, async (c) => {
  try {
    const projectId = c.get("projectId");
    const input = QuerySchema.parse(await c.req.json());

    // Generate embedding with error handling
    let queryVector: number[];
    try {
      queryVector = await generateEmbedding(c, input.query);
    } catch (embeddingError) {
      if (embeddingError instanceof AIError) {
        return errorResponse(c, "Failed to generate query embedding", "EMBEDDING_ERROR", 500);
      }
      throw embeddingError;
    }

    const filter: any = {};
    if (input.document_id) filter.documentId = input.document_id;

    // Query Vectorize with error handling
    let results;
    try {
      results = await queryVectorize(c, queryVector, input.top_k, projectId, filter);
    } catch (vectorizeError) {
      if (vectorizeError instanceof VectorizeError) {
        return errorResponse(c, "Vector search failed", "VECTOR_SEARCH_ERROR", 500);
      }
      throw vectorizeError;
    }

    const ids = results.matches.map((m: any) => m.id);
    if (ids.length === 0) {
      return successResponse(c, {
        mode: input.mode,
        chunks: [],
        citations: []
      }, "No relevant documents found");
    }

    // Fetch chunk content from D1
    const placeholders = ids.map(() => "?").join(",");
    const rows = await c.env.DB.prepare(
      `SELECT id, document_id, chunk_index, content_md, page_start, page_end
       FROM chunks WHERE id IN (${placeholders})`
    ).bind(...ids).all();

    const chunks = rows.results as any[];
    const citations = chunks.map((x) => ({
      document_id: x.document_id,
      chunk_id: x.id,
      chunk_index: x.chunk_index,
      page_start: x.page_start,
      page_end: x.page_end,
    }));

    // Generate answer if requested
    if (input.mode === "answer") {
      const context = chunks.map((x) => x.content_md).join("\n\n");
      
      try {
        const answer = await generateAnswer(c, context, input.query);
        return successResponse(c, {
          mode: input.mode,
          answer,
          chunks,
          citations
        }, "Answer generated successfully");
      } catch (answerError) {
        if (answerError instanceof AIError) {
          return errorResponse(c, "Failed to generate answer", "ANSWER_GENERATION_ERROR", 500);
        }
        throw answerError;
      }
    }

    return successResponse(c, {
      mode: input.mode,
      chunks,
      citations
    }, "Query processed successfully");
  } catch (error) {
    console.error("Error processing query:", error);
    
    if (error instanceof Error && error.name === 'ZodError') {
      return errorResponse(c, "Invalid request data", "VALIDATION_ERROR", 400);
    }
    
    return errorResponse(c, "Failed to process query", "QUERY_ERROR", 500);
  }
});

export default app;