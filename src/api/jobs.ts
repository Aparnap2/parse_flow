import { Hono } from 'hono';

const app = new Hono();

// GET /v1/jobs/:id - Get job status and results
app.get('/:id', async (c) => {
  const jobId = c.req.param('id');

  // Get account info from context (set by auth middleware)
  const accountId = c.get('account_id');

  try {
    // Fetch job details from the database
    const job = await c.env.DB.prepare(
      'SELECT id, account_id, status, mode, input_key, output_key, webhook_url, trust_score, error_message, created_at, completed_at FROM jobs WHERE id = ? AND account_id = ?'
    ).bind(jobId, accountId).first();

    if (!job) {
      return c.json({ error: 'Job not found or unauthorized' }, 404);
    }

    // Return job details
    return c.json({
      id: job.id,
      status: job.status, // queued, processing, completed, failed
      mode: job.mode,
      created_at: job.created_at,
      completed_at: job.completed_at,
      input_key: job.input_key,
      output_key: job.output_key,
      trust_score: job.trust_score,
      webhook_url: job.webhook_url,
      error_message: job.error_message
      // result_url would be generated with a signed URL in a real implementation
    });
  } catch (error) {
    console.error('Error fetching job:', error);
    return c.json({ error: 'Failed to fetch job details' }, 500);
  }
});

export default app;