# ParseFlow.ai - Document Intelligence API

Welcome to ParseFlow.ai, a developer-first document intelligence API that converts PDFs to Markdown/JSON with intelligent OCR capabilities.

## 🚀 Overview

ParseFlow.ai is a comprehensive document processing platform built with:
- **Hono** for API/UI (running on Cloudflare Workers)
- **Cloudflare D1** for database storage
- **Cloudflare R2** for document storage
- **Cloudflare Queues** for job processing
- **Modal** for GPU-powered OCR processing
- **Stripe** for billing

## ✨ Features

- **High-accuracy OCR**: Powered by Docling (primary) and DeepSeek-OCR (fallback)
- **Layout preservation**: Maintains document structure and formatting
- **Table and figure extraction**: Accurate parsing of complex elements
- **Webhook delivery**: Real-time notifications when processing completes
- **Financial document mode**: Specialized processing for financial documents
- **API-first design**: Easy integration with your applications
- **Scalable architecture**: Built to handle high-volume processing

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   API Layer     │    │  Processing      │    │   Storage &     │
│   (Hono/CF)     │    │  Engine (Modal)  │    │   Queues (CF)   │
│                 │    │                  │    │                 │
│ • /v1/extract   │───▶│ • Docling        │    │ • D1 (SQLite)   │
│ • /v1/uploads   │    │ • DeepSeek-OCR   │◀───│ • R2 (S3)       │
│ • /v1/jobs      │    │ • vLLM           │    │ • Queues        │
│ • Webhooks      │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🛠️ Setup

### Prerequisites

- Node.js 18+
- pnpm
- Python 3.10+
- Cloudflare account
- Modal account

### Installation

1. Install Node.js dependencies:
```bash
pnpm install
```

2. Install Python dependencies:
```bash
cd engine
source venv/bin/activate  # On Windows: engine\venv\Scripts\activate
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
# For Cloudflare Workers
wrangler secret put R2_ACCESS_KEY_ID
wrangler secret put R2_SECRET_ACCESS_KEY
wrangler secret put WORKER_API_SECRET
wrangler secret put STRIPE_SECRET_KEY
wrangler secret put STRIPE_WEBHOOK_SECRET
```

4. Deploy to Cloudflare:
```bash
# Deploy the main API
cd pages && wrangler deploy

# Deploy workers
cd ../workers/email && wrangler deploy
cd ../sync && wrangler deploy
cd ../billing && wrangler deploy
```

### Environment Variables

Create a `.dev.vars` file with the following:

```bash
# Cloudflare
CF_ACCOUNT_ID=your_account_id
R2_PUBLIC_URL=your_r2_public_url

# API Secrets
ENGINE_SECRET=your_engine_secret
WORKER_API_SECRET=your_worker_api_secret

# Stripe
STRIPE_SECRET_KEY=your_stripe_secret_key
STRIPE_WEBHOOK_SECRET=your_stripe_webhook_secret
STRIPE_STARTER_PRICE_ID=your_starter_price_id
STRIPE_PRO_PRICE_ID=your_pro_price_id
APP_URL=your_app_url

# R2
R2_ACCESS_KEY_ID=your_r2_access_key
R2_SECRET_ACCESS_KEY=your_r2_secret_key
```

## 📡 API Usage

### Authentication

All API requests require an API key in the Authorization header:

```
Authorization: Bearer pf_live_...
```

### Upload & Process Document

First, get a presigned URL to upload your document directly to our storage:

```
POST /v1/uploads/init
```

```json
{
  "content_type": "application/pdf",
  "file_name": "document.pdf"
}
```

Then upload your file to the returned presigned URL, and optionally create a processing job:

```
POST /v1/extract
```

```json
{
  "url": "https://your-storage.com/file.pdf",  // Optional, if you host the file
  "webhook_url": "https://your-app.com/webhook",
  "mode": "general"  // or "financial" for high-accuracy financial document processing
}
```

### Check Job Status

```
GET /v1/jobs/{job_id}
```

### Webhook Delivery

When processing is complete, we'll send a POST request to your webhook URL with the job result:

```json
{
  "id": "job_123...",
  "status": "completed",
  "result_url": "https://storage-url-to-result",
  "trust_score": 0.95
}
```

## 🧪 Testing

Run the test suite:

```bash
pnpm test
# or
npx vitest
```

## 🚀 Deployment

The system is designed for deployment on Cloudflare Workers:

1. Set up your D1 database:
```bash
wrangler d1 create parseflow-db
wrangler d1 execute parseflow-db --file=db/schema.sql
```

2. Set up your R2 bucket:
```bash
wrangler r2 bucket create parseflow-storage
```

3. Deploy the application:
```bash
# Deploy the main application
cd pages && wrangler deploy

# Deploy the workers
cd ../workers/email && wrangler deploy
cd ../sync && wrangler deploy
cd ../billing && wrangler deploy
```

## 🔄 Transformation Summary

This project was transformed from FreightStructurize (a freight auditing system) to ParseFlow.ai (a general document intelligence API) as specified in the PRD. Key changes include:

- **Database**: Migrated from freight-specific schema to ParseFlow schema with accounts, api_keys, and jobs
- **API**: Implemented full REST API with authentication, upload endpoints, and job management
- **Processing**: Updated from freight-specific extraction to general document processing with Docling and DeepSeek-OCR
- **Frontend**: Redesigned from freight dashboard to general API management UI
- **Billing**: Migrated from Lemon Squeezy to Stripe integration

## 📁 Project Structure

```
parseflow/
├── db/                    # Database schemas
├── engine/               # Python processing engine
├── modal/                # Modal GPU workers
├── pages/                # Frontend (Cloudflare Pages)
├── src/                  # API layer (Hono)
├── workers/              # Cloudflare Workers
│   ├── email/            # Email processing worker
│   ├── sync/             # Job processing worker
│   └── billing/          # Stripe billing worker
├── README.md
├── package.json
└── prd.md               # Original PRD
```

## 📄 License

This project is licensed under the MIT License.