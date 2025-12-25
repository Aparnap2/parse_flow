This is the **Final, Canonical Product Requirements Document (PRD)** for **ParseFlow.ai**.

It consolidates every architectural decision, "missing manual" fix, and operational constraint we have defined. It is ready for immediate implementation.

------

# 🚀 ParseFlow.ai — Master Build Specification

| Metadata       | Details                                                      |
| :------------- | :----------------------------------------------------------- |
| **Version**    | 1.0 (Final Build-Ready)                                      |
| **Mission**    | Developer-first document intelligence API (PDF → Markdown/JSON). |
| **Core Stack** | Hono (API/UI), Cloudflare Workers, D1, R2, Queues, Modal (GPU). |
| **Key AI**     | Docling (Primary) + **DeepSeek-OCR** (High-Accuracy Fallback). |

------

## 1. System Architecture & Design

## High-Level Data Flow

1. **Ingestion:** Client requests presigned URL → Uploads directly to R2.
2. **Dispatch:** Client calls API → Worker creates Job (D1) → Enqueues message.
3. **Compute:** Modal (GPU) pulls message via HTTP → Runs DeepSeek-OCR/Docling.
4. **Delivery:** Modal uploads JSON to R2 → Calls Worker Callback → Worker fires Webhook.
5. **Lifecycle:** R2 policies auto-delete inputs (24h) and results (72h).

## The Stack (Hono-First)

- **API & Frontend:** Hono (running on Cloudflare Workers). Frontend is Server-Side Rendered (SSR) JSX.
- **Database:** Cloudflare D1 (SQLite).
- **Storage:** Cloudflare R2 (S3-compatible).
- **Queue:** Cloudflare Queues (Standard, pull-based).
- **GPU:** Modal (Python 3.10 + vLLM).

------

## 2. Data Modelling (D1 Schema)

Run `npx wrangler d1 migrations create parseflow-db init` and use this SQL:

```
sql-- Accounts & Billing
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
```

------

## 3. Feature-by-Feature Implementation Map

## Feature A: Ingestion (Presigned "Direct-to-Cloud")

- **User Story:** "I want to upload a 50MB PDF without hitting API timeouts."
- **SOP:** Client gets a temporary upload URL, PUTs the file, then starts the job.
- **Technical Implementation:**
  - Use **AWS SDK v3** (not standard CF bindings) to generate presigned URLs.
  - Client-side or SDK-side hashing (SHA256) recommended.

## Feature B: The Processing Pipeline (Queue + GPU)

- **User Story:** "I want high accuracy for tables, even if it takes 30 seconds."
- **SOP:** Worker pushes job to Queue. Modal polls Queue, runs AI, returns result.
- **Technical Implementation:**
  - **Cloudflare Queue:** Stores `{ job_id, input_key, mode }`.
  - **Modal:** Runs `vLLM` with `deepseek-ai/DeepSeek-OCR`.
  - **Fallback Logic:** Default to Docling. If `mode='financial'` or `trust_score < 0.85`, run DeepSeek-OCR on specific pages.

## Feature C: Webhooks & Delivery

- **User Story:** "Notify my backend when the parse is done."
- **SOP:** Modal hits internal callback → Worker updates DB → Worker POSTs to user webhook.
- **Technical Implementation:**
  - **Security:** Internal callback protected by `x-internal-secret`.
  - **Payload:** Webhook sends `{ job_id, status, result_url }`. The actual JSON is in R2.

## Feature D: Billing (Stripe)

- **User Story:** "I buy credits and they appear instantly."
- **Technical Implementation:**
  - Stripe Webhook listens for `checkout.session.completed`.
  - **Critical Fix:** Must use `Stripe.createSubtleCryptoProvider()` in Workers.

------

## 4. File Structure

```
text/
├── wrangler.toml              # CF Config (Secrets, D1, Queues, R2)
├── package.json
├── migrations/                # D1 SQL files
├── src/
│   ├── index.tsx              # Hono Entry (CORS, Routing)
│   ├── api/
│   │   ├── extract.ts         # POST /v1/extract, /v1/uploads/init
│   │   ├── jobs.ts            # GET /v1/jobs/:id
│   │   └── webhooks.ts        # POST /stripe, POST /internal/callback
│   ├── lib/
│   │   ├── r2.ts              # AWS SDK Client generator
│   │   └── auth.ts            # API Key validation
│   └── views/                 # Hono JSX (Dashboard, Login)
└── modal/
    └── gpu_worker.py          # Python: DeepSeek-OCR + Docling
```

------

## 5. Copy-Paste Code Reference

## `src/lib/r2.ts` (The Presigned URL Fix)

*Standard R2 bindings cannot sign URLs. This wrapper is required.*

```
typescriptimport { S3Client, PutObjectCommand } from '@aws-sdk/client-s3'
import { getSignedUrl } from '@aws-sdk/s3-request-presigner'

export const createS3Client = (env: any) => new S3Client({
  region: 'auto',
  endpoint: `https://${env.CF_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId: env.R2_ACCESS_KEY_ID,     // Set via wrangler secret
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
  },
})

export const generatePresignedPut = async (env: any, key: string, contentType: string) => {
  const client = createS3Client(env)
  const cmd = new PutObjectCommand({ 
    Bucket: 'parseflow-storage', // Your bucket name
    Key: key, 
    ContentType: contentType 
  })
  return getSignedUrl(client, cmd, { expiresIn: 900 }) // 15 mins
}
```

## `src/api/webhooks.ts` (Stripe + Internal Callback)

```
typescriptimport { Hono } from 'hono'
import Stripe from 'stripe'

const app = new Hono<{ Bindings: Bindings }>()

// 1. Internal Callback (From Modal)
app.post('/internal/complete', async (c) => {
  const secret = c.req.header('x-internal-secret')
  if (secret !== c.env.WORKER_API_SECRET) return c.text('Unauthorized', 401)

  const { job_id, status, metrics } = await c.req.json()
  
  // Update D1
  await c.env.DB.prepare(
    'UPDATE jobs SET status = ?, completed_at = ? WHERE id = ?'
  ).bind(status, Date.now(), job_id).run()

  // Trigger User Webhook (Fire & Forget)
  const job = await c.env.DB.prepare('SELECT webhook_url FROM jobs WHERE id = ?').bind(job_id).first()
  if (job?.webhook_url) {
    c.executionCtx.waitUntil(fetch(job.webhook_url, { 
      method: 'POST', 
      body: JSON.stringify({ id: job_id, status }) 
    }))
  }
  return c.json({ ok: true })
})

// 2. Stripe Webhook (WebCrypto Fix)
app.post('/stripe', async (c) => {
  const sig = c.req.header('stripe-signature')
  const body = await c.req.text()
  
  const stripe = new Stripe(c.env.STRIPE_SECRET_KEY, {
    apiVersion: '2023-10-16',
    httpClient: Stripe.createFetchHttpClient(),
  })
  
  try {
    const event = await stripe.webhooks.constructEventAsync(
      body, sig!, c.env.STRIPE_WEBHOOK_SECRET, undefined, Stripe.createSubtleCryptoProvider()
    )
    if (event.type === 'checkout.session.completed') {
        // Add credits logic here
    }
  } catch (err) {
    return c.text(`Webhook Error`, 400)
  }
  return c.json({ received: true })
})

export default app
```

## `modal/gpu_worker.py` (DeepSeek-OCR Logic)

*Uses vLLM for max throughput. Note the specialized prompt.*

```
pythonimport modal
import os

# Image Definition: vLLM is critical for DeepSeek-OCR
image = (
    modal.Image.debian_slim()
    .pip_install("vllm>=0.6.3", "transformers", "numpy", "Pillow", "requests")
)

app = modal.App("parseflow-worker", image=image)

@app.cls(gpu="A10G", container_idle_timeout=300)
class DeepSeekProcessor:
    @modal.enter()
    def load_model(self):
        from vllm import LLM
        # Use the OCR-SPECIALIZED model (not Janus-Pro)
        self.llm = LLM(
            model="deepseek-ai/DeepSeek-OCR",
            trust_remote_code=True,
            enforce_eager=True
        )

    @modal.method()
    def process(self, r2_url, mode="general"):
        from vllm import SamplingParams
        
        # PROMPT: "grounding" enables bounding box / layout awareness
        prompt_text = "<image>\n<|grounding|>Convert the document to markdown." if mode == "financial" else "<image>\nConvert the document to markdown."
        
        sampling_params = SamplingParams(max_tokens=4096, temperature=0.1)
        
        # In production, you download r2_url to local bytes first
        # This is simplified vLLM usage:
        outputs = self.llm.generate(
            {"prompt": prompt_text, "multi_modal_data": {"image": r2_url}},
            sampling_params
        )
        return outputs[0].outputs[0].text

# Queue Consumer (HTTP Pull Emulation or Direct Call)
@app.function(schedule=modal.Period(seconds=5), secrets=[modal.Secret.from_name("parseflow-secrets")])
def poll_queue():
    import requests
    # 1. Pull from Cloudflare Queue via API
    # 2. Map to self.process.remote()
    # 3. Post back to WORKER_CALLBACK_URL with header x-internal-secret
    pass
```

------

## 6. Operational & Security Checklist (Do Not Skip)

1. **Secrets Management:**
   - Run `wrangler secret put R2_ACCESS_KEY_ID` (and Secret Key).
   - Run `wrangler secret put WORKER_API_SECRET` (Shared with Modal).
   - Run `wrangler secret put STRIPE_SECRET_KEY`.
2. **CORS:** Ensure `app.use('*', cors())` is in `src/index.tsx`.
3. **Retention:** Go to Cloudflare R2 Dashboard → Settings → Add Lifecycle Rule:
   - Prefix `uploads/`: expire 1 day.
   - Prefix `results/`: expire 3 days.
4. **Local Dev:**
   - Use `wrangler dev --remote` to test Queues/D1 interaction realistically.
   - For UI, just use standard Hono JSX; no `npm run build` needed for frontend.
5. **Environment Variables:**
   - `CF_ACCOUNT_ID` must be in `wrangler.toml` (vars) for the AWS Client to work.





