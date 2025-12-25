import { Hono } from 'hono';
import { zValidator } from '@hono/zod-validator';
import { z } from 'zod';
import { generatePresignedPut } from '../lib/r2';

const app = new Hono();

// POST /v1/uploads/init - Get presigned URL for direct upload to R2
app.post('/init', zValidator('json', z.object({
  content_type: z.string().default('application/pdf'),
  file_name: z.string()
})), async (c) => {
  const { content_type, file_name } = c.req.valid('json');

  // Get account info from context (set by auth middleware)
  const accountId = c.get('account_id');

  // Generate a unique upload ID
  const uploadId = `upload_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  const key = `uploads/${accountId}/${uploadId}/${file_name}`;

  try {
    // Generate presigned URL using the R2 library
    const presignedUrl = await generatePresignedPut(c.env, key, content_type);

    // Create a job record to track this upload
    const jobId = `job_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    await c.env.DB.prepare(
      'INSERT INTO jobs (id, account_id, status, input_key, created_at) VALUES (?, ?, ?, ?, ?)'
    ).bind(jobId, accountId, 'queued', key, Date.now()).run();

    return c.json({
      job_id: jobId,
      upload_id: uploadId,
      key: key,
      presigned_url: presignedUrl,
      expires_at: Date.now() + 900000 // 15 minutes from now
    });
  } catch (error) {
    console.error('Error generating presigned URL:', error);
    return c.json({ error: 'Failed to generate upload URL' }, 500);
  }
});

export default app;