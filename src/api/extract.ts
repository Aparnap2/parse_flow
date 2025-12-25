import { Hono } from 'hono';
import { zValidator } from '@hono/zod-validator';
import { z } from 'zod';

const app = new Hono();

// POST /v1/extract - Main extraction endpoint
app.post('/extract', zValidator('json', z.object({
  url: z.string().url().optional(),
  webhook_url: z.string().url().optional(),
  mode: z.enum(['general', 'financial']).default('general')
})), async (c) => {
  const { url, webhook_url, mode } = c.req.valid('json');

  // Get account info from context (set by auth middleware)
  const accountId = c.get('account_id');

  // Create a job record in the database
  const jobId = `job_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  try {
    await c.env.DB.prepare(
      'INSERT INTO jobs (id, account_id, status, mode, webhook_url, created_at) VALUES (?, ?, ?, ?, ?, ?)'
    ).bind(jobId, accountId, 'queued', mode, webhook_url || null, Date.now()).run();

    // In a real implementation, this would also:
    // 1. Queue the job for processing in Cloudflare Queue
    // 2. Possibly download the document from the URL if provided
    // 3. Store document in R2 if needed

    return c.json({
      job_id: jobId,
      status: 'queued',
      message: 'Document queued for processing'
    });
  } catch (error) {
    console.error('Error creating job:', error);
    return c.json({ error: 'Failed to create processing job' }, 500);
  }
});

export default app;