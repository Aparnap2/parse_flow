import { google } from 'googleapis';
import { performAudit } from './audit';

const SCOPES = ['https://www.googleapis.com/auth/spreadsheets'];

async function getSheetsClient(refreshToken: string) {
  const oauth2Client = new google.auth.OAuth2();
  oauth2Client.setCredentials({ refresh_token: refreshToken });
  return google.sheets({ version: 'v4', auth: oauth2Client });
}

export default {
  async queue(batch: any, env: any, ctx: any) {
    const MAX_RETRY_ATTEMPTS = 5; // Maximum number of retry attempts before dead-lettering

    for (const message of batch.messages) {
      try {
        const { jobId, userId, r2Key, isDemo = false, originalSender } = message.body;

        console.log(`Processing job ${jobId} for user ${userId}, attempt ${message.attempts}, isDemo: ${isDemo}`);

        const job = await env.DB.prepare(`
          SELECT j.*, u.google_refresh_token, e.target_sheet_id, e.schema_json
          FROM jobs j
          JOIN users u ON j.user_id = u.id
          LEFT JOIN extractors e ON j.extractor_id = e.id
          WHERE j.id = ?
        `).bind(jobId).first();

        if (!job) {
          console.log(`Job ${jobId} not found, acknowledging message`);
          message.ack();
          continue;
        }

        const result = await env.DB.prepare(
          'SELECT extracted_json FROM jobs WHERE id = ?'
        ).bind(jobId).first();

        if (!result?.extracted_json) {
          console.log(`Job ${jobId} has no extracted_json, acknowledging message`);
          message.ack();
          continue;
        }

        const data = JSON.parse(result.extracted_json);
        console.log(`Starting audit for job ${jobId}`);
        const audit = await performAudit(data, env.DB, userId, job.schema_json);

        console.log(`Audit completed for job ${jobId}, valid: ${audit.valid}`);
        await env.DB.prepare(`
          UPDATE jobs SET
            status = ?, audit_flags = ?, confidence_score = ?, updated_at = ?
          WHERE id = ?
        `).bind(audit.valid ? 'completed' : 'flagged', JSON.stringify(audit.flags), audit.score, Date.now(), jobId).run();

        // Determine where to send the data based on demo vs regular flow
        if (isDemo) {
          // For demo flow, use a public demo sheet
          console.log(`Processing demo job ${jobId}, using public demo sheet`);

          // Use service account credentials for public demo sheet
          const demoSheets = await getSheetsClient(env.DEMO_SHEET_REFRESH_TOKEN);

          // Use a predefined demo spreadsheet ID
          const demoSpreadsheetId = env.DEMO_SPREADSHEET_ID;

          if (demoSpreadsheetId) {
            const values = [
              data.date || '',
              data.vendor || '',
              data.total || '',
              audit.valid ? '✅ Clean' : `⚠️ ${audit.flags[0] || 'Review'}`,
              data.line_items?.length || 0,
              job.r2_visualization_url || ''
            ];

            await demoSheets.spreadsheets.values.append({
              spreadsheetId: demoSpreadsheetId,
              range: 'A:Z',
              valueInputOption: 'RAW',
              resource: { values: [values] }
            });
            console.log(`Successfully appended to demo Google Sheets for job ${jobId}`);
          } else {
            console.log(`No DEMO_SPREADSHEET_ID configured, skipping demo sheet append for job ${jobId}`);
          }
        } else if (job.target_sheet_id) {
          // Regular flow
          console.log(`Appending to Google Sheets for job ${jobId}`);
          const sheets = await getSheetsClient(job.google_refresh_token);
          const values = [
            data.date || '',
            data.vendor || '',
            data.total || '',
            audit.valid ? '✅ Clean' : `⚠️ ${audit.flags[0] || 'Review'}`,
            data.line_items?.length || 0,
            job.r2_visualization_url || ''
          ];

          await sheets.spreadsheets.values.append({
            spreadsheetId: job.target_sheet_id,
            range: 'A:Z',
            valueInputOption: 'RAW',
            resource: { values: [values] }
          });
          console.log(`Successfully appended to Google Sheets for job ${jobId}`);
        } else {
          console.log(`No target_sheet_id for job ${jobId}, skipping Google Sheets append`);
        }

        if (audit.valid) {
          console.log(`Inserting historical record for job ${jobId}`);
          await env.DB.prepare(`
            INSERT INTO historical_invoices
            (id, user_id, vendor_name, invoice_number, total_amount, invoice_date, created_at, job_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
          `).bind(
            crypto.randomUUID(),
            userId,
            data.vendor,
            data.invoice_number,
            data.total,
            data.date,
            Date.now(),
            jobId
          ).run();
          console.log(`Successfully inserted historical record for job ${jobId}`);
        }

        // For demo flow, send an email back to the original sender
        if (isDemo && originalSender && env.EMAIL_SERVICE_URL) {
          try {
            const demoSpreadsheetUrl = `https://docs.google.com/spreadsheets/d/${env.DEMO_SPREADSHEET_ID}`;
            await fetch(env.EMAIL_SERVICE_URL, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                to: originalSender,
                subject: 'Your invoice has been processed!',
                body: `Hello! Your invoice was processed successfully and added to our demo sheet. You can view it here: ${demoSpreadsheetUrl}`
              })
            });
            console.log(`Demo notification email sent to ${originalSender}`);
          } catch (emailError) {
            console.error(`Failed to send demo notification email:`, emailError);
          }
        }

        message.ack();
        console.log(`Successfully processed job ${jobId}`);

      } catch (error) {
        console.error(`Sync failed for job ${jobId}, user ${userId}, attempt ${message.attempts}:`, error);

        // Check if we've exceeded max retry attempts
        if (message.attempts >= MAX_RETRY_ATTEMPTS) {
          console.error(`Max retry attempts (${MAX_RETRY_ATTEMPTS}) reached for job ${jobId}. Moving to dead letter.`);

          try {
            // Update job status to 'failed' in the database
            await env.DB.prepare(`
              UPDATE jobs SET
                status = ?, error = ?, updated_at = ?
              WHERE id = ?
            `).bind('failed', `Max retries exceeded: ${error.message || 'Unknown error'}`, Date.now(), message.body.jobId).run();
          } catch (updateError) {
            console.error(`Failed to update job status to 'failed' for job ${message.body.jobId}:`, updateError);
          }

          // Acknowledge the message to prevent further retries
          message.ack();
        } else {
          // Retry with exponential backoff, capped at 300 seconds (5 minutes)
          const delay = Math.min(300, Math.pow(2, message.attempts));
          console.log(`Retrying job ${message.body.jobId} in ${delay} seconds`);
          message.retry(delay);
        }
      }
    }
  }
};