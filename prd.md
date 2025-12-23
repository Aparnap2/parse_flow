Structurize (The Data Clerk)
Status: LOCKED
Role: Back-Office Data Administrator
Mission: Turn chaotic documents into pristine data rows. Zero manual entry.

1. Product Vision
Structurize is an invisible AI employee that monitors a dedicated email address, extracts data from any PDF/CSV attachment, validates it against business rules, and syncs it to a database (Google Sheets/Notion).
Promise: "Forward the email. We file the data."

2. Target Audience (ICP)
Primary: Operations Managers, Solo Founders, Freelance Bookkeepers.

Pain: Manual data entry from invoices, receipts, and resumes.

Trigger: End-of-month reconciliation or high-volume hiring.

3. Vertical Agentic Workflow (E2E)
Ingest: Receives email → Identifies attachment type (Invoice vs Resume).

Extract (The Brain): OCR (Docling) + LLM (Llama 3) extracts key fields based on Schema.

Validate (The Guard):

Math Check: Sum(LineItems) == Total?

Duplicate Check: Vendor + InvoiceNumber exists in DB?

Anomaly Check: Total > 1.5 * Avg(Vendor)?

Normalize: Formats dates (YYYY-MM-DD), currency (USD), and categories (Tax Code).

Action: Appends row to Google Sheet.

Report: Emails user if validation fails ("Math Error: $5 discrepancy").

4. Technical Architecture
Ingestion: Cloudflare Email Workers + R2 (Storage).

Engine: Render Docker (Docling + Llama 3 on Groq).

Database: Cloudflare D1 (Jobs, Users, Historical Data).

Sync: Google Sheets API / Notion API.

Frontend: Hono + Cloudflare Pages (Dashboard).

5. Data Model (D1)
sql
TABLE users (id, email, structurize_email, plan, google_token);
TABLE extractors (id, user_id, name, schema_json, target_sheet_id);
TABLE jobs (id, user_id, status, extracted_data, audit_flags, confidence_score);
TABLE history (user_id, vendor, total, date); -- For anomaly detection
6. PLG Hook (Free Tool)
"The Magic Forwarder"

User forwards 1 email to demo@structurize.ai.

We reply instantly with a link to a public Google Sheet containing their extracted data.

No signup required. Instant "Aha!" moment.