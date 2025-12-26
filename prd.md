This is the **Final, Canonical PRD & Technical Spec** for **Sarah AI (v7.0)**.
 It is architected for **Extreme Configurable Data Entry** (The "CSV Factory") using a lean, high-performance stack: **Hono (SSR)**, **Cloudflare Workers**, **D1/Drizzle**, and **Modal (Python AI)**.

------

# 🚀 Sarah AI — The Configurable Digital Intern

| Metadata       | Details                                                      |
| :------------- | :----------------------------------------------------------- |
| **Mission**    | Turn messy emails (PDFs) into perfect, user-defined CSVs/Sheets. |
| **Core Value** | "Hiring" an AI Intern that follows *your* specific SOPs.     |
| **Tech Stack** | **Hono** (Frontend/API), **Drizzle** (ORM), **D1** (DB), **R2** (Storage), **Modal** (AI). |
| **Auth**       | **Google OAuth** (via Arctic or simple OAuth flow).          |

------

## 1. User Stories & SOP Mapping

## Feature A: "The Blueprint Builder" (Customization)

**User Story:** As an Agency Owner, I want to define *exactly* which columns are in the CSV (e.g., "Vendor", "Tax Code") and add custom math (e.g., `Total * 0.20`) so I don't have to edit the file manually.

| Step  | SOP (User Action)                                | Technical Implementation                                     |
| :---- | :----------------------------------------------- | :----------------------------------------------------------- |
| **1** | User logs into Dashboard → "New Blueprint".      | **Hono Route:** `GET /blueprints/new` renders a dynamic form. |
| **2** | User adds columns: Name, Type, Instruction.      | **UI:** JavaScript adds rows to a `<table>`. Form submits JSON array. |
| **3** | User defines "Calculated Field" (`Total * 0.2`). | **Backend:** Saved to D1 as a JSON Schema string.            |
| **4** | User saves Blueprint as "Xero Import".           | **D1:** `INSERT INTO blueprints ...`                         |

## Feature B: "The Email Ingest" (Trigger)

**User Story:** I want to forward an invoice to `sarah@...` and have it processed using my "Xero Import" blueprint automatically.

| Step  | SOP (User Action)                          | Technical Implementation                                     |
| :---- | :----------------------------------------- | :----------------------------------------------------------- |
| **1** | User forwards email to `[uuid]@sarah.ai`.  | **Cloudflare Email Worker:** Parses MIME, extracts PDF.      |
| **2** | System identifies User via "From" address. | **D1:** `SELECT * FROM users WHERE email_alias = ?`.         |
| **3** | System saves PDF to R2.                    | **R2:** `PUT /uploads/{job_id}.pdf`.                         |
| **4** | System dispatches AI Job.                  | **Queue:** `env.JOBS_QUEUE.send({ blueprint_id, file_key })`. |

## Feature C: "The AI Processor" (Python/Modal)

**User Story:** I need the AI to extract data *exactly* according to my Blueprint instructions, handling weird formats.

| Step  | SOP (User Action) | Technical Implementation                                   |
| :---- | :---------------- | :--------------------------------------------------------- |
| **1** | (Automatic)       | **Modal Worker:** Pulls job. Downloads PDF from R2.        |
| **2** | (Automatic)       | **DeepSeek/Docling:** Extracts text based on User Schema.  |
| **3** | (Automatic)       | **Python:** Runs math formulas (`mathjs` equivalent).      |
| **4** | (Automatic)       | **Callback:** POSTs JSON result back to Cloudflare Worker. |

## Feature D: "The HITL Dashboard" (Review)

**User Story:** I want to review low-confidence data and see a visual report of my spend before syncing.

| Step  | SOP (User Action)                             | Technical Implementation                                  |
| :---- | :-------------------------------------------- | :-------------------------------------------------------- |
| **1** | User gets "Review Needed" email. Clicks link. | **Hono SSR:** Renders Split View (PDF Left, Form Right).  |
| **2** | User corrects "Total" field.                  | **UI:** `input` field updates local state.                |
| **3** | User sees "Spend Chart" updates instantly.    | **Chart.js:** Renders simple Bar Chart of extracted data. |
| **4** | User clicks "Approve".                        | **Worker:** Pushes to Google Sheets API + Generates CSV.  |

------

## 2. Data Models (Drizzle ORM)

```
typescript// src/db/schema.ts
import { sqliteTable, text, integer, real } from 'drizzle-orm/sqlite-core';

export const users = sqliteTable('users', {
  id: text('id').primaryKey(),
  email: text('email').notNull().unique(),
  google_id: text('google_id').unique(), // For OAuth
  inbox_alias: text('inbox_alias').unique(), // 'uuid@sarah.ai'
  created_at: integer('created_at', { mode: 'timestamp' })
});

export const blueprints = sqliteTable('blueprints', {
  id: text('id').primaryKey(),
  user_id: text('user_id').references(() => users.id),
  name: text('name'), // "Xero Import"
  schema_json: text('schema_json'), // JSON: [{ name: "Total", type: "currency", instruction: "..." }]
  target_sheet_id: text('target_sheet_id') // Optional: Google Sheet ID
});

export const jobs = sqliteTable('jobs', {
  id: text('id').primaryKey(),
  user_id: text('user_id'),
  status: text('status'), // 'queued', 'review', 'completed'
  r2_key: text('r2_key'),
  result_json: text('result_json'), // Extracted Data
  confidence: real('confidence'),
  created_at: integer('created_at', { mode: 'timestamp' })
});
```

------

## 3. Code Snippets (Copy-Paste Ready)

## A. Backend: Hono + Drizzle + Auth (`src/index.tsx`)

*Supports Google OAuth and standard Hono routing.*

```
typescriptimport { Hono } from 'hono'
import { drizzle } from 'drizzle-orm/d1'
import { googleAuth } from '@hono/oauth-providers/google'
import { users } from './db/schema' // Your Drizzle schema

type Bindings = {
  DB: D1Database
  GOOGLE_CLIENT_ID: string
  GOOGLE_CLIENT_SECRET: string
  JWT_SECRET: string
}

const app = new Hono<{ Bindings: Bindings }>()

// 1. Auth Middleware & Routes
app.use('/auth/google', googleAuth({
  scope: ['profile', 'email'],
}))

app.get('/auth/google/callback', async (c) => {
  const user = c.get('user') // From googleAuth middleware
  const db = drizzle(c.env.DB)
  
  // Upsert User
  await db.insert(users).values({
    id: crypto.randomUUID(),
    email: user.email,
    google_id: user.id
  }).onConflictDoUpdate({ target: users.email, set: { google_id: user.id } }).run()
  
  return c.redirect('/dashboard')
})

// 2. Blueprint Builder (JSX View)
app.get('/blueprints/new', (c) => {
  return c.html(
    <html>
      <head>
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://unpkg.com/htmx.org"></script> 
      </head>
      <body class="p-8">
        <h1 class="text-2xl mb-4">Create Extraction Blueprint</h1>
        <form hx-post="/blueprints" hx-target="#response">
          <div id="fields-container">
            <div class="flex gap-2 mb-2">
              <input name="field_name[]" placeholder="Column Name (e.g. Total)" class="border p-2" />
              <input name="instruction[]" placeholder="AI Instruction (e.g. Include Tax)" class="border p-2 w-96" />
              <select name="type[]" class="border p-2">
                 <option value="text">Text</option>
                 <option value="currency">Currency</option>
              </select>
            </div>
          </div>
          <button type="button" onclick="addField()" class="bg-gray-200 p-2">+ Add Column</button>
          <button type="submit" class="bg-blue-600 text-white p-2 rounded">Save Blueprint</button>
        </form>
        <script>
          // Simple JS to add rows
          function addField() {
            const div = document.querySelector('#fields-container > div').cloneNode(true);
            div.querySelectorAll('input').forEach(i => i.value = '');
            document.getElementById('fields-container').appendChild(div);
          }
        </script>
      </body>
    </html>
  )
})

export default app
```

## B. AI Service: Modal (Python) (`modal/extractor.py`)

*Parses PDF based on dynamic schema.*

```
pythonimport modal

app = modal.App("sarah-extractor")
image = modal.Image.debian_slim().pip_install("docling", "pandas")

@app.function(image=image)
def process_document(pdf_url: str, schema_json: list):
    import pandas as pd
    # Pseudo-code for LLM extraction
    # In production, use Instructor or Outlines for strict JSON schema
    
    print(f"Processing {pdf_url} with schema {schema_json}")
    
    # Simulating LLM Output
    extracted_data = {"Vendor": "Home Depot", "Total": 105.50}
    
    # Run Custom Math (Calculated Fields)
    # Example: If schema has 'Tax_Rate', calculate it
    for field in schema_json:
        if field.get('formula'):
            # Safe eval logic here
            pass
            
    return extracted_data

@app.function()
def webhook_handler(data: dict):
    # This receives the job from Cloudflare
    result = process_document.remote(data['url'], data['schema'])
    
    # Post back to Hono
    import requests
    requests.post(f"{data['callback_url']}", json=result)
```

## C. Email Ingest: Cloudflare Worker (`src/email.ts`)

*The "Ear" of Sarah.*

```
typescriptimport PostalMime from 'postal-mime';

export default {
  async email(message, env, ctx) {
    const parser = new PostalMime();
    const email = await parser.parse(message.raw);
    
    // 1. Get Attachment
    const attachment = email.attachments.find(a => a.mimeType === 'application/pdf');
    if (!attachment) return; // Reply "No PDF found"
    
    // 2. Upload to R2
    const key = `uploads/${crypto.randomUUID()}.pdf`;
    await env.R2.put(key, attachment.content);
    
    // 3. Queue Job
    // Find User Blueprint based on "To" address or "Subject"
    await env.JOBS_QUEUE.send({
      r2_key: key,
      user_email: message.from
    });
  }
}
```

------

## 4. Final Architecture Checklist

1. **Frontend:** Hono returning server-rendered JSX (HTMX for interactivity). **Fast, Simple, No Build Step.**
2. **Database:** Drizzle + Cloudflare D1 (SQLite). **Cheap & Relational.**
3. **AI Compute:** Modal (Python) for the heavy lifting, called via HTTP.
4. **Integration:** Google Sheets API (via a Service Account JSON stored in Cloudflare Secrets).

Yes, there are **three critical "Cold Start" problems** you are forgetting. These are the things that kill bootstrapped SaaS apps *after* the code is written but *before* the first check clears.

## 1. The "Empty Inbox" Trust Gap (Privacy Policy)

Agencies will NOT forward client invoices to you if you don't have a legally sound **Privacy Policy**.

- **The Risk:** You are processing PII (Names, Addresses, Bank Details). If you use a generic "Lorem Ipsum" policy, they will run.
- **The Fix:** You need a "Data Processing Agreement" (DPA) that explicitly states:
  - "We do not train our models on your data." (Use DeepSeek/Modal's zero-retention mode).
  - "We delete source PDFs after 24 hours."
  - "We are SOC-2 Compliant" (Lie? No. Say: "We use SOC-2 compliant infrastructure via Cloudflare/AWS").
- **Action:** Add a `/legal/dpa` page to your footer Day 1.[cookie-script+1](https://cookie-script.com/guides/saas-privacy-policy)

## 2. The "Infinite Loop" Bill (Rate Limiting)

- **The Risk:** A user sets up an auto-forward rule that creates a loop (Sarah replies -> User auto-replies -> Sarah replies...).
- **The Cost:** You pay Modal/DeepSeek for 10,000 worthless executions in 1 hour. You go bankrupt overnight.
- **The Fix:** Implement **Rate Limiting** in your Cloudflare Worker.
  - *Rule:* Max 50 emails / hour / user.
  - *Tech:* Use `env.RateLimiter` (Cloudflare) or a simple KV counter. If they hit 51, silently drop the email or queue it for later.[developers.cloudflare+1](https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/)

## 3. The "Silent Fail" (Error Visibility)

- **The Problem:** DeepSeek *will* fail on some encrypted PDFs.

- **The Bad UX:** User forwards email -> Silence. They assume your product is broken and churn.

- **The Fix:** **"The 'Oops' Email."**

  - If the AI fails (timeout, encrypted PDF, unreadable), catch the error.

  - Send an automated reply:

    > *"Hi! I tried to read 'invoice.pdf' but it seems to be password protected (or corrupt). Can you unlock it and send it again?"*

  - **Why:** A failure with a reply is "Service." A failure with silence is "Bug."[aisera](https://aisera.com/blog/ai-mistakes/)

## Final "Copy-Paste" Additions

**A. Rate Limiter (add to `email.ts`):**

```
typescript// Prevent loops/spam
const ip = message.headers.get("x-real-ip") || "unknown";
const { success } = await env.MY_RATE_LIMITER.limit({ key: ip });
if (!success) {
  console.log("Rate limit exceeded for", ip);
  return; // Drop silently to save costs
}
```

**B. Error Handler (add to `email.ts`):**

```
typescripttry {
  // ... AI processing ...
} catch (e) {
  await sendEmail({
    to: message.from,
    subject: "I couldn't read that file 😔",
    body: "I had trouble reading the PDF you sent. Is it password protected?"
  });
}
```

Yes, **Lemon Squeezy** is excellent for this. They handle global tax (Merchant of Record), which saves you a massive headache.

Here is the exact **Usage-Based Billing Architecture** for Sarah AI.

------

## 1. The Pricing Model

You are selling a **Hybrid Plan**:

- **Base Fee:** $49/mo (Includes 500 pages + 100MB).
- **Overage (Usage):**
  - $0.05 per extra page.
  - $0.02 per extra MB.

## 2. Implementation Guide (Lemon Squeezy API)

## Step A: Product Setup (In Lemon Dashboard)

1. Create a Subscription Product: "Sarah Pro".
2. Enable **"Usage-based billing"**.
3. Set Aggregation: **"Sum of usage during period"**. (This is critical. It means "add up all the pages they used this month").
4. Create 2 Usage Meter Units:
   - `pages_processed` (Unit Price: $0.05).
   - `storage_mb` (Unit Price: $0.02).

## Step B: The "Meter" Middleware (Code)

You need to report usage *every time* Sarah processes a file.

**Add this to your `modal/extractor.py` (or Hono Worker):**

```
pythonimport requests

def report_usage(subscription_item_id, pages_count, pdf_size_mb):
    """
    Tells Lemon Squeezy to add usage to the customer's bill.
    """
    LS_API_KEY = "your_api_key"
    
    # 1. Report Pages
    requests.post(
        "https://api.lemonsqueezy.com/v1/usage-records",
        headers={
            "Authorization": f"Bearer {LS_API_KEY}",
            "Content-Type": "application/vnd.api+json"
        },
        json={
            "data": {
                "type": "usage-records",
                "attributes": {
                    "quantity": pages_count,
                    "action": "increment" 
                },
                "relationships": {
                    "subscription-item": {
                        "data": {
                            "type": "subscription-items",
                            "id": str(subscription_item_id) # Need to store this in D1 users table!
                        }
                    }
                }
            }
        }
    )
    # 2. Report Storage (Repeat logic for storage_mb)
```

## Step C: Database Schema Update (Drizzle)

You must store the `subscription_item_id` to report usage against it.

```
typescript// src/db/schema.ts
export const users = sqliteTable('users', {
  id: text('id').primaryKey(),
  email: text('email').notNull(),
  // Lemon Squeezy Fields
  ls_customer_id: text('ls_customer_id'),
  ls_subscription_id: text('ls_subscription_id'),
  ls_pages_item_id: text('ls_pages_item_id'), // Store this to report Page Usage
  ls_storage_item_id: text('ls_storage_item_id') // Store this to report Storage Usage
});
```

## Step D: Handling Webhooks (Sync)

When a user buys a plan, Lemon Squeezy sends a `subscription_created` webhook. You need to catch it to save the IDs.

```
typescript// src/webhooks.ts (Hono Route)
app.post('/webhooks/ls', async (c) => {
  const payload = await c.req.json();
  const event = payload.meta.event_name;
  
  if (event === 'subscription_created') {
    const userId = payload.meta.custom_data.user_id; // Pass this during checkout!
    const items = payload.data.relationships['subscription-items'].data;
    
    // You need to fetch the items to know which ID corresponds to "Pages" vs "Storage"
    // Then update D1:
    await db.update(users).set({
      ls_subscription_id: payload.data.id,
      ls_pages_item_id: items[0].id, // (Logic to identify which item is which)
    }).where(eq(users.id, userId));
  }
  return c.text('OK');
});
```

## 3. Critical "Gotcha" (The ID Trap)

- **The Problem:** Lemon Squeezy creates a unique `subscription_item_id` for *every* metric for *every* user.
- **The Fix:** When you receive the `subscription_created` webhook, you must call the LS API to get the "Subscription Items" list.
  - Loop through them.
  - Check the `variant_name` (e.g., "Page Overage").
  - Save that specific ID to your DB column `ls_pages_item_id`.

## Final Verdict

This architecture allows you to charge exactly for what they use.

- **User Uploads 10 page PDF.**
- **System:** `report_usage(user.ls_pages_item_id, 10)`.
- **Lemon Squeezy:** Adds $0.50 to their next invoice automatically.

**You are ready to code.**

