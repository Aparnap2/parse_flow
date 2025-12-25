# QWEN Development Plan: Transform FreightStructurize to ParseFlow.ai

## Project Overview
- **Current System**: FreightStructurize (Freight auditing system for 3PLs and Freight Brokers)
- **Target System**: ParseFlow.ai (Developer-first document intelligence API - PDF → Markdown/JSON)
- **PRD Reference**: `/home/aparna/Desktop/docuflow/prd.md`
- **Mission**: Transform existing system to a general document intelligence API with specialized OCR capabilities

## Architecture Comparison

### Current Architecture (FreightStructurize)
- Email Workers (Cloudflare) → Python Engine → Sync Workers → Google Sheets/TMS
- PostgreSQL database
- LangExtract + Docling for extraction
- Freight-specific auditing logic

### Target Architecture (ParseFlow.ai - per PRD)
- Hono API/UI (Cloudflare Workers) → Cloudflare D1, R2, Queues → Modal GPU Workers
- Docling (Primary) + DeepSeek-OCR (High-Accuracy Fallback)
- Presigned URL uploads
- Webhook delivery system
- Stripe billing

## Development Tasks

### 1. Database Schema Migration
**Current**: PostgreSQL with freight-specific schema
**Target**: Cloudflare D1 with ParseFlow schema

**Files to modify/create**:
- `/home/aparna/Desktop/docuflow/db/freight_schema.sql` → Keep as reference
- `/home/aparna/Desktop/docuflow/db/parseflow_schema.sql` → New ParseFlow schema (CREATED)
- `/home/aparna/Desktop/docuflow/db/schema.sql` → Update with ParseFlow schema

**Target Schema** (from PRD):
```sql
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
```

### 2. API Layer Implementation
**Current**: Email-triggered processing
**Target**: REST API with presigned URL uploads

**Files created**:
- `/home/aparna/Desktop/docuflow/src/index.tsx` - Hono entry point (CREATED)
- `/home/aparna/Desktop/docuflow/src/api/extract.ts` - POST /v1/extract (CREATED)
- `/home/aparna/Desktop/docuflow/src/api/uploads.ts` - POST /v1/uploads/init (CREATED)
- `/home/aparna/Desktop/docuflow/src/api/jobs.ts` - GET /v1/jobs/:id (CREATED)
- `/home/aparna/Desktop/docuflow/src/api/webhooks.ts` - POST /stripe, POST /internal/callback (CREATED)
- `/home/aparna/Desktop/docuflow/src/lib/r2.ts` - AWS SDK Client generator (CREATED)
- `/home/aparna/Desktop/docuflow/src/lib/auth.ts` - API Key validation (CREATED)

### 3. Processing Engine Migration
**Current**: Python FastAPI engine with LangExtract + Docling
**Target**: Modal GPU workers with Docling + DeepSeek-OCR

**Files created/modified**:
- `/home/aparna/Desktop/docuflow/engine/main.py` → Updated for ParseFlow API (MODIFIED)
- `/home/aparna/Desktop/docuflow/modal/gpu_worker.py` → New Modal worker (CREATED)

### 4. Frontend Migration
**Current**: Basic Hono dashboard
**Target**: Server-Side Rendered JSX frontend

**Files modified**:
- `/home/aparna/Desktop/docuflow/pages/src/index.tsx` → Updated for ParseFlow UI (MODIFIED)

### 5. Queue System Implementation
**Current**: Cloudflare Queues (partially implemented)
**Target**: Full Cloudflare Queue + Modal integration

**Files modified**:
- `/home/aparna/Desktop/docuflow/workers/email/src/index.ts` → Updated for ParseFlow schema (MODIFIED)
- `/home/aparna/Desktop/docuflow/workers/sync/src/index.ts` → Updated for ParseFlow schema (MODIFIED)

### 6. Billing System Migration
**Current**: Lemon Squeezy billing
**Target**: Stripe billing

**Files modified**:
- `/home/aparna/Desktop/docuflow/workers/billing/src/index.ts` → Updated for Stripe (MODIFIED)
- `/home/aparna/Desktop/docuflow/workers/billing/package.json` → Added Stripe dependency (CREATED)

## Code Snippets from Context7 and DDG

### R2 Presigned URL Implementation (from PRD and implemented):
```typescript
// src/lib/r2.ts
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3'
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

The R2 presigned URL functionality has been implemented and integrated into the uploads API endpoint at `/v1/uploads/init`.

### Webhook Implementation (from PRD):
```typescript
// src/api/webhooks.ts
import { Hono } from 'hono'
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

### Modal GPU Worker (from PRD):
```python
# modal/gpu_worker.py
import modal
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

## Development Plan

### Phase 1: Setup and Database Migration
1. Set up new project structure matching PRD
2. Migrate database schema from freight to ParseFlow
3. Implement basic API authentication

### Phase 2: API Implementation
1. Implement presigned URL generation
2. Create job creation and management endpoints
3. Implement webhook endpoints

### Phase 3: Processing Engine
1. Migrate processing engine to support ParseFlow requirements
2. Implement DeepSeek-OCR fallback logic
3. Integrate with Modal for GPU processing

### Phase 4: Frontend and Billing
1. Update dashboard for ParseFlow functionality
2. Migrate billing from Lemon Squeezy to Stripe

### Phase 5: Testing and Deployment
1. Write comprehensive tests
2. Deploy to Cloudflare Workers
3. Verify end-to-end functionality

## Testing Strategy (TDD)

### Unit Tests
- API endpoint tests
- Database schema validation
- Authentication tests
- R2 upload/download tests

### Integration Tests
- End-to-end document processing
- Webhook delivery verification
- Queue processing tests

### System Tests
- Full workflow validation
- Performance benchmarks
- Error handling scenarios

## Environment Setup Commands
```bash
# Install dependencies
pip install -r engine/requirements.txt
pnpm install

# Set up virtual environment
python -m venv engine/venv
source engine/venv/bin/activate  # On Windows: engine\venv\Scripts\activate
pip install -r engine/requirements.txt

# Start the engine
cd engine
uvicorn main:app --reload

# Deploy to Cloudflare
cd pages && wrangler deploy
cd ../workers/email && wrangler deploy
cd ../sync && wrangler deploy
cd ../billing && wrangler deploy
```