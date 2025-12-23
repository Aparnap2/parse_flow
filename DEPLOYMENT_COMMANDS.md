# Structurize Deployment Commands

## 1. Cloudflare Setup
```bash
# Create D1 Database
wrangler d1 create structurize-db

# Create R2 Bucket
wrangler r2 bucket create structurize-inbox

# Create Queue
wrangler queues create structurize-jobs

# Execute Database Schema
wrangler d1 execute structurize-db --file=db/schema.sql
```

## 2. Set Secrets
```bash
# Email Worker
wrangler secret put ENGINE_URL --name structurize-email
wrangler secret put ENGINE_SECRET --name structurize-email
wrangler secret put R2_PUBLIC_URL --name structurize-email

# Sync Worker
wrangler secret put ENGINE_SECRET --name structurize-sync
wrangler secret put DEMO_SHEET_REFRESH_TOKEN --name structurize-sync
wrangler secret put DEMO_SPREADSHEET_ID --name structurize-sync
wrangler secret put EMAIL_SERVICE_URL --name structurize-sync

# Billing Worker
wrangler secret put LEMONSQUEEZY_SECRET --name structurize-billing
wrangler secret put LEMON_STARTER_PRODUCT_ID --name structurize-billing
wrangler secret put LEMON_PRO_PRODUCT_ID --name structurize-billing
wrangler secret put LEMONSQEEZY_STORE_ID --name structurize-billing

# Pages
wrangler secret put JWT_SECRET --name structurize-dashboard
```

## 3. Deploy Workers
```bash
# Deploy Email Worker
cd workers/email && wrangler deploy

# Deploy Sync Worker
cd workers/sync && wrangler deploy

# Deploy Billing Worker
cd workers/billing && wrangler deploy

# Deploy Pages
cd pages && wrangler deploy
```

## 4. Configure Email Routing
In Cloudflare Dashboard:
- Email → Routing → *@structurize.ai → structurize-email worker

## 5. Deploy Engine to Render
```bash
# Push engine to GitHub
git add engine/
git commit -m "Add hybrid LangExtract+Docling engine"
git push

# Deploy on Render.com
# Connect GitHub repo
# Use Dockerfile
# Set environment variables:
#   - ENGINE_SECRET
#   - R2_ACCESS_KEY
#   - R2_SECRET_KEY
#   - R2_ENDPOINT
#   - R2_PUBLIC_URL
#   - LANGEXTRACT_API_KEY
#   - LANGEXTRACT_MODEL_ID (optional, default: gemini-2.5-flash)
#   - LANGEXTRACT_PASSES (optional, default: 2)
#   - LANGEXTRACT_MAX_WORKERS (optional, default: 4)
```

## 6. Test End-to-End
```bash
# Send test email with PDF attachment to user123@structurize.ai
# Check job appears in dashboard
# Verify data appears in Google Sheets
# Check audit flags work correctly