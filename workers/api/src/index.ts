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

async function requireApiKey(c: any, next: any) {
  const raw = c.req.header("Authorization") || "";
  const key = raw.startsWith("Bearer ") ? raw.slice(7) : "";
  if (!key) return c.json({ error: "Missing API key" }, 401);

  const row = await c.env.DB.prepare("SELECT project_id FROM api_keys WHERE key = ? AND revoked_at IS NULL")
    .bind(key)
    .first();

  if (!row) return c.json({ error: "Invalid API key" }, 403);
  c.set("projectId", String(row.project_id));
  return next();
}

// Project management
app.post("/v1/projects", async (c) => {
  const body = await c.req.json();
  const id = crypto.randomUUID();
  const name = body?.name || "Untitled";
  await c.env.DB.prepare("INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)")
    .bind(id, name, Date.now())
    .run();
  return c.json({ id, name });
});

// API key management
app.post("/v1/api-keys", async (c) => {
  const body = await c.req.json();
  const projectId = body?.project_id;
  if (!projectId) return c.json({ error: "project_id required" }, 400);

  const key = "sk_" + crypto.randomUUID().replaceAll("-", "");
  await c.env.DB.prepare("INSERT INTO api_keys (key, project_id, created_at) VALUES (?, ?, ?)")
    .bind(key, projectId, Date.now())
    .run();
  return c.json({ key });
});

// Webhook registration
app.post("/v1/webhooks", requireApiKey, async (c) => {
  const projectId = c.get("projectId");
  const body = await c.req.json();
  const url = body?.url;
  if (!url) return c.json({ error: "url required" }, 400);

  const id = crypto.randomUUID();
  const secret = crypto.randomUUID().replaceAll("-", "");
  await c.env.DB.prepare("INSERT INTO webhooks (id, project_id, url, secret, created_at) VALUES (?, ?, ?, ?, ?)")
    .bind(id, projectId, url, secret, Date.now())
    .run();

  return c.json({ webhook_id: id, secret });
});

// Single document creation
app.post("/v1/documents", requireApiKey, async (c) => {
  const projectId = c.get("projectId");
  const input = CreateDocumentSchema.parse(await c.req.json());

  const existing = await c.env.DB.prepare(
    "SELECT id, status FROM documents WHERE project_id = ? AND sha256 = ? AND status != 'DELETED'"
  ).bind(projectId, input.sha256).first();

  if (existing) {
    return c.json({
      document_id: String(existing.id),
      status: String(existing.status),
      upload_url: `${c.env.BASE_URL}/v1/documents/${existing.id}/upload`,
      deduped: true,
    });
  }

  const docId = crypto.randomUUID();
  const r2Key = `${projectId}/${docId}/${input.source_name}`;

  await c.env.DB.prepare(
    `INSERT INTO documents
     (id, project_id, source_name, content_type, sha256, r2_key, status, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, 'CREATED', ?, ?)`
  ).bind(docId, projectId, input.source_name, input.content_type, input.sha256, r2Key, Date.now(), Date.now()).run();

  return c.json({
    document_id: docId,
    status: "CREATED",
    upload_url: `${c.env.BASE_URL}/v1/documents/${docId}/upload`,
  });
});

// Batch document creation
app.post("/v1/documents/batch", requireApiKey, async (c) => {
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

  return c.json({ documents: out });
});

// Document upload endpoint
app.put("/v1/documents/:id/upload", requireApiKey, async (c) => {
  const projectId = c.get("projectId");
  const docId = c.req.param("id");

  const doc = await c.env.DB.prepare(
    "SELECT r2_key, content_type, status FROM documents WHERE id = ? AND project_id = ? AND status != 'DELETED'"
  ).bind(docId, projectId).first();

  if (!doc) return c.json({ error: "Not found" }, 404);

  const body = await c.req.arrayBuffer();
  if (body.byteLength === 0) return c.json({ error: "Empty body" }, 400);

  await c.env.BUCKET.put(String(doc.r2_key), body, {
    httpMetadata: { contentType: String(doc.content_type) },
  });

  await c.env.DB.prepare("UPDATE documents SET status = 'UPLOADED', updated_at = ? WHERE id = ?")
    .bind(Date.now(), docId).run();

  return c.json({ ok: true, status: "UPLOADED" });
});

// Document completion and processing
app.post("/v1/documents/:id/complete", requireApiKey, async (c) => {
  const projectId = c.get("projectId");
  const docId = c.req.param("id");

  const doc = await c.env.DB.prepare(
    "SELECT status FROM documents WHERE id = ? AND project_id = ? AND status != 'DELETED'"
  ).bind(docId, projectId).first();

  if (!doc) return c.json({ error: "Not found" }, 404);
  if (String(doc.status) !== "UPLOADED") return c.json({ error: "Upload required first" }, 400);

  await c.env.DB.prepare("UPDATE documents SET status = 'PROCESSING', updated_at = ? WHERE id = ?")
    .bind(Date.now(), docId).run();

  const job = IngestJobSchema.parse({ project_id: projectId, document_id: docId });
  await c.env.INGEST_QUEUE.send(job);

  return c.json({ ok: true, status: "PROCESSING" });
});

// Get document status
app.get("/v1/documents/:id", requireApiKey, async (c) => {
  const projectId = c.get("projectId");
  const docId = c.req.param("id");

  const doc = await c.env.DB.prepare(
    "SELECT id, status, chunk_count, error, source_name, content_type, sha256, created_at, updated_at FROM documents WHERE id = ? AND project_id = ?"
  ).bind(docId, projectId).first();

  if (!doc) return c.json({ error: "Not found" }, 404);
  
  // Add upload URL if document is in CREATED or UPLOADED status
  const status = String(doc.status);
  const response: any = { ...doc };
  
  if (status === 'CREATED' || status === 'UPLOADED') {
    response.upload_url = `${c.env.BASE_URL}/v1/documents/${docId}/upload`;
  }
  
  return c.json(response);
});

// Delete document
app.delete("/v1/documents/:id", requireApiKey, async (c) => {
  const projectId = c.get("projectId");
  const docId = c.req.param("id");

  const doc = await c.env.DB.prepare("SELECT r2_key FROM documents WHERE id = ? AND project_id = ? AND status != 'DELETED'")
    .bind(docId, projectId).first();
  if (!doc) return c.json({ error: "Not found" }, 404);

  await c.env.DB.prepare("DELETE FROM chunks WHERE document_id = ? AND project_id = ?").bind(docId, projectId).run();
  await c.env.DB.prepare("UPDATE documents SET status = 'DELETED', updated_at = ? WHERE id = ?").bind(Date.now(), docId).run();
  await c.env.BUCKET.delete(String(doc.r2_key));

  return c.json({ ok: true });
});

// Query endpoint with embeddings
app.post("/v1/query", requireApiKey, async (c) => {
  const projectId = c.get("projectId");
  const input = QuerySchema.parse(await c.req.json());

  // Generate embedding using Workers AI
  const emb = await c.env.AI.run("@cf/baai/bge-base-en-v1.5", { text: [input.query] });
  const queryVector = (emb as any).data[0];

  const filter: any = {};
  if (input.document_id) filter.documentId = input.document_id;

  // Query Vectorize with metadata filtering
  let results;
  try {
    results = await c.env.VECTORIZE.query(queryVector, {
      topK: input.top_k,
      namespace: projectId,
      returnMetadata: "all",
      filter,
    });
  } catch (error) {
    console.error("Vectorize query failed:", error);
    return c.json({
      mode: input.mode,
      chunks: [],
      citations: [],
      error: "Vector search failed. Please try again."
    }, 500);
  }

  const ids = results.matches.map((m: any) => m.id);
  if (ids.length === 0) return c.json({ mode: input.mode, chunks: [], citations: [] });

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
    // Limit context to avoid token overflow
    const maxContextLength = 4000;
    const truncatedContext = context.length > maxContextLength
      ? context.substring(0, maxContextLength) + "..."
      : context;
    
    try {
      const resp = await c.env.AI.run("@cf/qwen/qwen-3-3b", {
        messages: [
          { role: "system", content: `Answer using only the provided context. If the answer is not in the context, say "I don't have enough information to answer that question."

Context:
${truncatedContext}` },
          { role: "user", content: input.query },
        ],
      });
      return c.json({ mode: input.mode, answer: (resp as any).response, chunks, citations });
    } catch (error) {
      console.error("Answer generation failed:", error);
      return c.json({
        mode: input.mode,
        answer: "I encountered an error generating the answer. Please try again.",
        chunks,
        citations,
        error: "AI model request failed"
      }, 500);
    }
  }

  return c.json({ mode: input.mode, chunks, citations });
});

export default app;