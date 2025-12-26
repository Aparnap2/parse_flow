import { Hono } from 'hono';

const app = new Hono();

// GET /jobs/:id - Get job status and results
app.get('/:id', async (c) => {
  const jobId = c.req.param('id');
  const userId = c.req.cookie('user_id');

  if (!userId) {
    return c.redirect('/');
  }

  try {
    // Fetch job details from the database
    const job = await c.env.DB.prepare(
      'SELECT id, user_id, status, r2_key, result_json, confidence, created_at, completed_at FROM jobs WHERE id = ? AND user_id = ?'
    ).bind(jobId, userId).first();

    if (!job) {
      return c.json({ error: 'Job not found or unauthorized' }, 404);
    }

    // Return job details
    return c.json({
      id: job.id,
      status: job.status, // queued, review, completed
      created_at: job.created_at,
      completed_at: job.completed_at,
      r2_key: job.r2_key,
      result_json: job.result_json,
      confidence: job.confidence
    });
  } catch (error) {
    console.error('Error fetching job:', error);
    return c.json({ error: 'Failed to fetch job details' }, 500);
  }
});

// GET /jobs - List user's jobs
app.get('/', async (c) => {
  const userId = c.req.cookie('user_id');

  if (!userId) {
    return c.redirect('/');
  }

  try {
    // Fetch user's jobs from the database
    const jobs = await c.env.DB.prepare(
      'SELECT id, user_id, status, r2_key, result_json, confidence, created_at, completed_at FROM jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT 20'
    ).bind(userId).all();

    const jobsList = jobs.results?.map(job => `
      <div class="bg-white p-4 rounded-lg shadow mb-4">
        <div class="flex justify-between">
          <h3 class="font-bold">Job ID: ${job.id}</h3>
          <span class="px-2 py-1 rounded-full text-xs ${getStatusColor(job.status)}">${job.status}</span>
        </div>
        <p class="text-sm text-gray-600">Created: ${new Date(job.created_at).toLocaleString()}</p>
        <p class="text-sm text-gray-600">Confidence: ${(job.confidence || 0).toFixed(2)}</p>
        <div class="mt-2">
          <details>
            <summary class="cursor-pointer text-sm text-gray-700">View Result</summary>
            <pre class="text-xs bg-gray-100 p-2 rounded mt-2">${job.result_json || 'No result yet'}</pre>
          </details>
        </div>
      </div>
    `).join('');

    return c.html(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>My Jobs | Sarah AI</title>
        <script src="https://cdn.tailwindcss.com"></script>
      </head>
      <body class="bg-gray-100">
        <div class="container mx-auto p-8">
          <h1 class="text-3xl font-bold mb-6">My Processing Jobs</h1>
          <div>
            ${jobsList || '<p class="text-gray-600">No jobs yet.</p>'}
          </div>
        </div>
        <script>
          function getStatusColor(status) {
            const colorMap = {
              'queued': 'bg-yellow-100 text-yellow-800',
              'review': 'bg-blue-100 text-blue-800',
              'completed': 'bg-green-100 text-green-800'
            };
            return colorMap[status] || 'bg-gray-100 text-gray-800';
          }
        </script>
      </body>
      </html>
    `);
  } catch (error) {
    console.error('Error fetching jobs:', error);
    return c.html(`
      <div class="container mx-auto p-8">
        <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
          <strong class="font-bold">Error! </strong>
          <span class="block sm:inline">Failed to fetch jobs: ${error.message}</span>
        </div>
      </div>
    `);
  }
});

export default app;

function getStatusColor(status) {
  const colorMap = {
    'queued': 'bg-yellow-100 text-yellow-800',
    'review': 'bg-blue-100 text-blue-800',
    'completed': 'bg-green-100 text-green-800'
  };
  return colorMap[status] || 'bg-gray-100 text-gray-800';
}