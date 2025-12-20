import { IngestJobSchema, WebhookEventSchema } from "../../../packages/shared/src/types";

type Env = {
  DB: D1Database;
  BUCKET: R2Bucket;
  VECTORIZE: VectorizeIndex;
  AI: Ai;
  ENGINE_URL: string;
  ENGINE_SECRET: string;
  EVENTS_QUEUE: Queue;
};

async function sha256Hex(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data);
  const bytes = new Uint8Array(digest);
  return Array.from(bytes).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function chunkText(md: string, chunkSize = 1400, overlap = 200) {
  const out: { i: number; t: string }[] = [];
  let i = 0;
  let idx = 0;
  while (i < md.length) {
    out.push({ i: idx, t: md.slice(i, i + chunkSize) });
    idx++;
    i += (chunkSize - overlap);
  }
  return out;
}

export default {
  async queue(batch: MessageBatch<any>, env: Env) {
    for (const msg of batch.messages) {
      try {
        const job = IngestJobSchema.parse(msg.body);

        const doc = await env.DB.prepare(
          "SELECT r2_key, source_name, content_type FROM documents WHERE id = ? AND project_id = ? AND status = 'PROCESSING'"
        ).bind(job.document_id, job.project_id).first();
        if (!doc) {
          msg.ack();
          continue;
        }

        const obj = await env.BUCKET.get(String(doc.r2_key));
        if (!obj) throw new Error("R2 object missing");

        const bytes = await obj.arrayBuffer();
        const fileHash = await sha256Hex(bytes);

        // Call Python engine for document parsing
        const engineRes = await fetch(env.ENGINE_URL, {
          method: "POST",
          headers: {
            "x-secret": env.ENGINE_SECRET,
            "content-type": "application/octet-stream",
            "x-filename": String(doc.source_name),
            "x-content-type": String(doc.content_type),
          },
          body: bytes,
        });

        if (!engineRes.ok) throw new Error(`Engine error ${engineRes.status}`);
        const parsed = await engineRes.json();
        const markdown = String(parsed.markdown || "");
        if (!markdown) throw new Error("Engine returned empty markdown");

        // Clean up existing chunks
        await env.DB.prepare("DELETE FROM chunks WHERE document_id = ? AND project_id = ?")
          .bind(job.document_id, job.project_id).run();

        // Chunk the markdown and process embeddings
        const parts = chunkText(markdown);
        const now = Date.now();

        for (const p of parts) {
          const chunkId = crypto.randomUUID();

          // Store chunk in D1
          await env.DB.prepare(
            `INSERT INTO chunks (id, project_id, document_id, chunk_index, content_md, page_start, page_end, created_at)
             VALUES (?, ?, ?, ?, ?, NULL, NULL, ?)`
          ).bind(chunkId, job.project_id, job.document_id, p.i, p.t, now).run();

          // Generate embedding using Workers AI
          const emb = await env.AI.run("@cf/baai/bge-base-en-v1.5", { text: [p.t] });
          const vec = (emb as any).data[0];

          // Upsert to Vectorize with metadata
          await env.VECTORIZE.upsert([{
            id: chunkId,
            values: vec,
            namespace: job.project_id,
            metadata: {
              projectId: job.project_id,
              documentId: job.document_id,
              chunkIndex: p.i,
              sourceName: String(doc.source_name),
              fileSha256: fileHash,
            },
          }]);
        }

        // Update document status
        await env.DB.prepare(
          "UPDATE documents SET status = 'READY', chunk_count = ?, updated_at = ?, error = NULL WHERE id = ? AND project_id = ?"
        ).bind(parts.length, now, job.document_id, job.project_id).run();

        // Send webhook notifications
        const hooks = await env.DB.prepare("SELECT id, url, secret FROM webhooks WHERE project_id = ?")
          .bind(job.project_id).all();

        for (const h of hooks.results as any[]) {
          const evt = WebhookEventSchema.parse({
            project_id: job.project_id,
            webhook_id: h.id,
            type: "document.ready",
            attempt: 0,
            data: {
              document_id: job.document_id,
              source_name: String(doc.source_name),
              chunk_count: parts.length,
            },
          });
          await env.EVENTS_QUEUE.send(evt);
        }

        msg.ack();
      } catch (e) {
        console.error(`Processing failed for document ${job.document_id}:`, e);
        
        // Update document status to FAILED
        try {
          await env.DB.prepare(
            "UPDATE documents SET status = 'FAILED', error = ?, updated_at = ? WHERE id = ? AND project_id = ?"
          ).bind(String(e), Date.now(), job.document_id, job.project_id).run();
        } catch (dbError) {
          console.error("Failed to update document status:", dbError);
        }
        
        const delaySeconds = Math.min(120, Math.pow(2, msg.attempts));
        msg.retry({ delaySeconds });
      }
    }
  },
};