import { IngestJobSchema } from "../../../packages/shared/src/types";

type Env = {
  DB: D1Database;
  BUCKET: R2Bucket;
  VECTORIZE: VectorizeIndex;
  EVENTS_QUEUE: Queue;
  AI: Ai;
};

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

class EngineError extends ExternalServiceError {
  constructor(message: string, statusCode: number = 500) {
    super('DocuFlow Engine', message, statusCode);
    this.name = 'EngineError';
  }
}

// Enhanced error handling wrapper for external service calls
async function withErrorHandling<T>(
  operation: () => Promise<T>,
  serviceName: string,
  context: string,
  job: any
): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error(`Error in ${serviceName} during ${context} for job ${job.document_id}:`, errorMessage);
    
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
    } else if (serviceName === 'DocuFlow Engine') {
      throw new EngineError(`Failed to ${context}: ${errorMessage}`);
    } else {
      throw new ExternalServiceError(serviceName, `Failed to ${context}: ${errorMessage}`);
    }
  }
}

// Enhanced R2 operations with error handling
async function getR2Object(env: Env, key: string, job: any): Promise<any> {
  return await withErrorHandling(
    async () => {
      const obj = await env.BUCKET.get(key);
      if (!obj) {
        throw new R2Error(`Object not found: ${key}`, 404);
      }
      return obj;
    },
    'R2',
    `get object ${key}`,
    job
  );
}

// Enhanced Vectorize operations with error handling
async function upsertVectorize(
  env: Env,
  vectors: any[],
  namespace: string,
  job: any
): Promise<void> {
  return await withErrorHandling(
    async () => {
      if (!vectors || vectors.length === 0) {
        throw new VectorizeError("No vectors to upsert");
      }
      
      const result = await env.VECTORIZE.upsert(vectors, { namespace });
      
      if (!result || typeof result.count !== 'number') {
        throw new VectorizeError("Invalid response format from Vectorize upsert");
      }
      
      console.log(`Successfully upserted ${result.count} vectors to Vectorize`);
    },
    'Vectorize',
    `upsert ${vectors.length} vectors`,
    job
  );
}

async function deleteVectorize(
  env: Env,
  ids: string[],
  namespace: string,
  job: any
): Promise<void> {
  return await withErrorHandling(
    async () => {
      if (!ids || ids.length === 0) {
        return; // Nothing to delete
      }
      
      await env.VECTORIZE.delete(ids, { namespace });
      console.log(`Successfully deleted ${ids.length} vectors from Vectorize`);
    },
    'Vectorize',
    `delete ${ids.length} vectors`,
    job
  );
}

// Enhanced AI operations with error handling
async function generateEmbedding(env: Env, text: string, job: any): Promise<number[]> {
  return await withErrorHandling(
    async () => {
      if (!text || text.trim().length === 0) {
        throw new AIError("Empty text provided for embedding");
      }
      
      const emb = await env.AI.run("@cf/baai/bge-base-en-v1.5", { text: [text] });
      
      if (!emb || !Array.isArray(emb.data) || emb.data.length === 0) {
        throw new AIError("Invalid embedding response format");
      }
      
      return emb.data[0];
    },
    'Workers AI',
    `generate embedding for text: "${text.substring(0, 50)}..."`,
    job
  );
}

// Enhanced database operations with error handling
async function updateDocumentStatus(
  env: Env,
  docId: string,
  status: string,
  error?: string,
  job?: any
): Promise<void> {
  return await withErrorHandling(
    async () => {
      const now = Date.now();
      if (error) {
        await env.DB.prepare(
          "UPDATE documents SET status = ?, error = ?, updated_at = ? WHERE id = ?"
        ).bind(status, error, now, docId).run();
      } else {
        await env.DB.prepare(
          "UPDATE documents SET status = ?, error = NULL, updated_at = ? WHERE id = ?"
        ).bind(status, now, docId).run();
      }
    },
    'D1 Database',
    `update document ${docId} status to ${status}`,
    job || { document_id: docId }
  );
}

async function getDocumentById(env: Env, docId: string, projectId: string, job: any): Promise<any> {
  return await withErrorHandling(
    async () => {
      const doc = await env.DB.prepare(
        "SELECT id, status, r2_key, chunk_count, error FROM documents WHERE id = ? AND project_id = ?"
      ).bind(docId, projectId).first();
      
      if (!doc) {
        throw new Error("Document not found");
      }
      
      return doc;
    },
    'D1 Database',
    `fetch document ${docId}`,
    job
  );
}

async function insertChunks(env: Env, chunks: any[], job: any): Promise<void> {
  return await withErrorHandling(
    async () => {
      if (!chunks || chunks.length === 0) {
        return; // Nothing to insert
      }
      
      // Batch insert chunks
      for (const chunk of chunks) {
        await env.DB.prepare(
          `INSERT INTO chunks
           (id, document_id, project_id, chunk_index, content_md, page_start, page_end, embedding_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
        ).bind(
          chunk.id,
          chunk.document_id,
          chunk.project_id,
          chunk.chunk_index,
          chunk.content_md,
          chunk.page_start,
          chunk.page_end,
          chunk.embedding_id,
          Date.now()
        ).run();
      }
      
      console.log(`Successfully inserted ${chunks.length} chunks into database`);
    },
    'D1 Database',
    `insert ${chunks.length} chunks`,
    job
  );
}

async function deleteChunksByDocument(env: Env, docId: string, projectId: string, job: any): Promise<string[]> {
  return await withErrorHandling(
    async () => {
      const rows = await env.DB.prepare(
        "SELECT id, embedding_id FROM chunks WHERE document_id = ? AND project_id = ?"
      ).bind(docId, projectId).all();
      
      const embeddingIds = rows.results.map((r: any) => r.embedding_id);
      
      await env.DB.prepare("DELETE FROM chunks WHERE document_id = ? AND project_id = ?")
        .bind(docId, projectId).run();
      
      console.log(`Successfully deleted ${rows.results.length} chunks from database`);
      return embeddingIds;
    },
    'D1 Database',
    `delete chunks for document ${docId}`,
    job
  );
}

// Enhanced webhook operations with error handling
async function sendWebhookEvent(env: Env, event: any, job: any): Promise<void> {
  return await withErrorHandling(
    async () => {
      const webhooks = await env.DB.prepare(
        "SELECT id, url, secret FROM webhooks WHERE project_id = ? AND revoked_at IS NULL"
      ).bind(event.project_id).all();

      if (!webhooks.results || webhooks.results.length === 0) {
        console.log(`No active webhooks for project ${event.project_id}`);
        return;
      }

      const promises = webhooks.results.map(async (wh: any) => {
        try {
          const payload = JSON.stringify(event);
          const signature = await crypto.subtle.sign(
            "HMAC",
            await crypto.subtle.importKey(
              "raw",
              new TextEncoder().encode(wh.secret),
              { name: "HMAC", hash: "SHA-256" },
              false,
              ["sign"]
            ),
            new TextEncoder().encode(payload)
          );
          const sigHex = Array.from(new Uint8Array(signature))
            .map(b => b.toString(16).padStart(2, "0"))
            .join("");

          const res = await fetch(wh.url, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-DocuFlow-Signature": `sha256=${sigHex}`,
            },
            body: payload,
          });

          if (!res.ok) {
            console.error(`Webhook ${wh.id} returned ${res.status}: ${res.statusText}`);
          } else {
            console.log(`Webhook ${wh.id} delivered successfully`);
          }
        } catch (err) {
          console.error(`Failed to deliver webhook ${wh.id}:`, err);
        }
      });

      await Promise.allSettled(promises);
    },
    'Webhook System',
    `send webhook event for job ${job.document_id}`,
    job
  );
}

// Enhanced document processing with comprehensive error handling
async function processDocument(env: Env, job: any): Promise<void> {
  const { project_id, document_id } = job;
  console.log(`Starting document processing for ${document_id} in project ${project_id}`);

  try {
    // Get document with error handling
    const doc = await getDocumentById(env, document_id, project_id, job);
    
    if (String(doc.status) !== "PROCESSING") {
      throw new Error(`Document not in PROCESSING state (current: ${doc.status})`);
    }

    // Get file from R2 with error handling
    const obj = await getR2Object(env, String(doc.r2_key), job);
    const buffer = await obj.arrayBuffer();

    // Call engine with enhanced error handling
    let parsed;
    try {
      const engineUrl = "https://docuflow-engine.your-domain.com/parse";
      const form = new FormData();
      form.append("file", new Blob([buffer], { type: obj.httpMetadata?.contentType || "application/octet-stream" }));
      form.append("filename", obj.httpMetadata?.contentDisposition || "document");

      const resp = await fetch(engineUrl, {
        method: "POST",
        body: form,
        headers: {
          "X-Project-ID": project_id,
          "X-Document-ID": document_id,
        },
      });

      if (!resp.ok) {
        const errorText = await resp.text();
        throw new EngineError(`Engine returned ${resp.status}: ${errorText}`, resp.status);
      }

      parsed = await resp.json();
      
      if (!parsed || !Array.isArray(parsed.chunks) || parsed.chunks.length === 0) {
        throw new EngineError("Invalid response format from engine");
      }
      
    } catch (engineError) {
      if (engineError instanceof EngineError) {
        throw engineError;
      }
      throw new EngineError(`Failed to call engine: ${engineError instanceof Error ? engineError.message : String(engineError)}`);
    }

    // Delete existing chunks and vectors if reprocessing
    const existingEmbeddingIds = await deleteChunksByDocument(env, document_id, project_id, job);
    if (existingEmbeddingIds.length > 0) {
      await deleteVectorize(env, existingEmbeddingIds, project_id, job);
    }

    // Generate embeddings with error handling
    const vectors: any[] = [];
    const dbChunks: any[] = [];
    
    for (let i = 0; i < parsed.chunks.length; i++) {
      const chunk = parsed.chunks[i];
      
      try {
        const embedding = await generateEmbedding(env, chunk.text, job);
        
        const embeddingId = `${document_id}_${i}`;
        vectors.push({
          id: embeddingId,
          values: embedding,
          metadata: {
            documentId: document_id,
            chunkIndex: i,
            pageStart: chunk.page_start,
            pageEnd: chunk.page_end,
          },
        });

        dbChunks.push({
          id: crypto.randomUUID(),
          document_id,
          project_id,
          chunk_index: i,
          content_md: chunk.text,
          page_start: chunk.page_start,
          page_end: chunk.page_end,
          embedding_id: embeddingId,
        });
      } catch (embeddingError) {
        if (embeddingError instanceof AIError) {
          console.error(`Failed to generate embedding for chunk ${i}, skipping:`, embeddingError.message);
          continue; // Skip this chunk but continue processing others
        }
        throw embeddingError;
      }
    }

    if (vectors.length === 0) {
      throw new Error("No chunks were successfully processed");
    }

    // Insert chunks into database
    await insertChunks(env, dbChunks, job);

    // Upsert vectors to Vectorize
    await upsertVectorize(env, vectors, project_id, job);

    // Update document status
    await updateDocumentStatus(env, document_id, "READY", undefined, job);

    // Send webhook event
    await sendWebhookEvent(env, {
      type: "document.ready",
      project_id,
      document_id,
      timestamp: Date.now(),
    }, job);

    console.log(`Successfully processed document ${document_id} with ${vectors.length} chunks`);
  } catch (error) {
    console.error(`Error processing document ${document_id}:`, error);
    
    let errorMessage = "Unknown error during processing";
    let errorCode = "PROCESSING_ERROR";
    
    if (error instanceof ExternalServiceError) {
      errorMessage = error.message;
      errorCode = error.name.toUpperCase();
    } else if (error instanceof Error) {
      errorMessage = error.message;
    }
    
    // Update document with error status
    await updateDocumentStatus(env, document_id, "FAILED", errorMessage, job);
    
    // Send webhook event for failure
    await sendWebhookEvent(env, {
      type: "document.failed",
      project_id: job.project_id,
      document_id: job.document_id,
      error: errorMessage,
      error_code: errorCode,
      timestamp: Date.now(),
    }, job);
    
    // Re-throw to trigger queue retry
    throw error;
  }
}

export default {
  async queue(batch: MessageBatch<any>, env: Env): Promise<void> {
    console.log(`Processing batch of ${batch.messages.length} messages`);
    
    for (const msg of batch.messages) {
      try {
        const job = IngestJobSchema.parse(msg.body);
        await processDocument(env, job);
        msg.ack();
        console.log(`Successfully processed job for document ${job.document_id}`);
      } catch (error) {
        console.error(`Error processing message:`, error);
        
        // Enhanced error logging
        if (error instanceof ExternalServiceError) {
          console.error(`External service error (${error.name}): ${error.message}`);
        } else if (error instanceof Error) {
          console.error(`Processing error: ${error.message}`);
          if (error.stack) {
            console.error(`Stack trace: ${error.stack}`);
          }
        }
        
        // Retry logic - let Cloudflare handle retries
        // The message will be retried based on queue configuration
        throw error;
      }
    }
  },
};