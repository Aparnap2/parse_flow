import { Hono } from 'hono';
import { html } from 'hono/html';

const app = new Hono();

app.get('/', (c) => c.html(html`
<!DOCTYPE html>
<html>
<head>
  <script src="https://cdn.tailwindcss.com"></script>
  <title>ParseFlow.ai - Document Intelligence API</title>
</head>
<body class="bg-gradient-to-br from-indigo-50 to-blue-50 min-h-screen">
  <nav class="bg-white shadow-sm border-b">
    <div class="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
      <h1 class="text-2xl font-bold">ParseFlow.ai</h1>
      <div class="flex gap-4">
        <a href="/dashboard" class="bg-indigo-600 text-white px-6 py-2 rounded-lg">Dashboard</a>
        <a href="/docs" class="text-gray-600 hover:text-indigo-600 px-6 py-2 rounded-lg">API Docs</a>
      </div>
    </div>
  </nav>
  <div class="max-w-4xl mx-auto py-16 px-4 text-center">
    <h1 class="text-5xl font-bold text-gray-900 mb-6">Developer-First Document Intelligence</h1>
    <p class="text-xl text-gray-600 mb-12">PDF → Markdown/JSON API with intelligent OCR</p>
    <div class="bg-white p-8 rounded-2xl shadow-xl max-w-3xl mx-auto">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div class="text-left">
          <h2 class="text-2xl font-bold mb-4">Get Started in Seconds</h2>
          <div class="space-y-4">
            <div>
              <h3 class="font-medium text-gray-700">1. Get an API Key</h3>
              <p class="text-gray-600 text-sm">Generate your key in the dashboard</p>
            </div>
            <div>
              <h3 class="font-medium text-gray-700">2. Upload Your Document</h3>
              <pre class="bg-gray-100 p-2 rounded text-xs overflow-x-auto">curl -X POST \\
  -H "Authorization: Bearer pf_live_..." \\
  -H "Content-Type: application/json" \\
  -d '{"webhook_url": "https://your-app.com/webhook"}' \\
  https://api.parseflow.ai/v1/uploads/init</pre>
            </div>
            <div>
              <h3 class="font-medium text-gray-700">3. Receive Processed Data</h3>
              <p class="text-gray-600 text-sm">Via webhook or polling</p>
            </div>
          </div>
        </div>
        <div class="bg-indigo-50 p-6 rounded-xl">
          <h3 class="font-bold text-lg mb-4">Features</h3>
          <ul class="space-y-2 text-left text-gray-700">
            <li class="flex items-start">
              <span class="text-green-500 mr-2">✓</span>
              <span>High-accuracy OCR with DeepSeek-OCR</span>
            </li>
            <li class="flex items-start">
              <span class="text-green-500 mr-2">✓</span>
              <span>Layout preservation</span>
            </li>
            <li class="flex items-start">
              <span class="text-green-500 mr-2">✓</span>
              <span>Table and figure extraction</span>
            </li>
            <li class="flex items-start">
              <span class="text-green-500 mr-2">✓</span>
              <span>Webhook delivery</span>
            </li>
            <li class="flex items-start">
              <span class="text-green-500 mr-2">✓</span>
              <span>Financial document mode</span>
            </li>
          </ul>
        </div>
      </div>
      <div class="mt-8">
        <a href="/dashboard" class="bg-indigo-600 text-white px-8 py-3 rounded-xl font-bold inline-block">Get Started</a>
      </div>
    </div>
  </div>
</body>
</html>
`));

app.get('/dashboard', async (c) => {
  // Extract account ID from the authentication context (e.g., from a JWT token in cookies or headers)
  // For now, we'll use a mock account ID - in a real implementation this would come from proper auth
  const authHeader = c.req.header('Authorization');
  const accountId = authHeader?.startsWith('Bearer ') ? authHeader.substring(7) : null;

  // In a real implementation, you would validate the JWT token here
  // const token = authHeader?.replace('Bearer ', '');
  // const decoded = jwt.verify(token, c.env.JWT_SECRET);
  // const accountId = decoded.accountId;

  if (!accountId) {
    return c.redirect('/'); // Redirect to login page if not authenticated
  }

  // Query the database for the account and their jobs
  const account = await c.env.DB.prepare(
    'SELECT email, credits_balance FROM accounts WHERE id = ?'
  ).bind(accountId).first();

  if (!account) {
    return c.text('Account not found', 404);
  }

  // Get recent jobs for the account
  const jobs = await c.env.DB.prepare(`
    SELECT j.id, j.input_key, j.status, j.mode, j.created_at, j.completed_at, j.trust_score
    FROM jobs j
    WHERE j.account_id = ?
    ORDER BY j.created_at DESC
    LIMIT 10
  `).bind(accountId).all();

  // Format jobs for display
  const jobRows = jobs.results?.map((job: any) => {
    const fileName = job.input_key ? job.input_key.split('/').pop() || job.input_key : 'N/A';
    let statusDisplay = '⏳ Queued';
    let statusClass = 'text-yellow-600';

    if (job.status === 'processing') {
      statusDisplay = '🔄 Processing';
      statusClass = 'text-blue-600';
    } else if (job.status === 'completed') {
      statusDisplay = '✅ Completed';
      statusClass = 'text-green-600';
    } else if (job.status === 'failed') {
      statusDisplay = '❌ Failed';
      statusClass = 'text-red-600';
    }

    const createdAt = new Date(job.created_at).toLocaleString();
    const trustScore = job.trust_score ? `${(job.trust_score * 100).toFixed(1)}%` : 'N/A';

    return `
      <div class="flex justify-between p-4 bg-gray-50 rounded-xl">
        <div>
          <span class="font-medium">${fileName}</span>
          <div class="text-sm text-gray-500">${createdAt} • Mode: ${job.mode || 'general'}</div>
        </div>
        <div class="flex items-center gap-4">
          <span class="${statusClass} font-bold">${statusDisplay}</span>
          <span class="text-gray-600 text-sm">Trust: ${trustScore}</span>
        </div>
      </div>
    `;
  }).join('') || '';

  return c.html(html`
<!DOCTYPE html>
<html>
<head>
  <script src="https://cdn.tailwindcss.com"></script>
  <title>ParseFlow.ai Dashboard</title>
</head>
<body class="bg-gray-50 min-h-screen">
  <div class="flex">
    <div class="w-64 bg-white border-r p-6">
      <h2 class="text-2xl font-bold mb-8">ParseFlow.ai</h2>
      <a href="/" class="block p-3 text-gray-600 hover:bg-gray-100 rounded-xl mb-2">Home</a>
      <a href="/dashboard" class="block p-3 bg-indigo-50 text-indigo-700 rounded-xl font-bold mb-2">Dashboard</a>
      <a href="/docs" class="block p-3 text-gray-600 hover:bg-gray-100 rounded-xl mb-2">API Docs</a>
    </div>
    <div class="ml-64 p-8 flex-1">
      <div class="flex justify-between mb-8">
        <h1 class="text-3xl font-bold">Dashboard</h1>
        <div class="flex gap-4 items-center">
          <div class="bg-indigo-100 text-indigo-800 px-4 py-2 rounded-xl text-sm font-bold">
            Credits: ${account.credits_balance}
          </div>
          <code class="bg-white border px-4 py-2 rounded-xl text-sm font-mono">${account.email}</code>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div class="bg-white rounded-2xl shadow-sm border p-6">
          <h2 class="text-xl font-bold mb-2">API Keys</h2>
          <p class="text-gray-600">Manage your API credentials</p>
          <button class="mt-4 bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm">Generate Key</button>
        </div>
        <div class="bg-white rounded-2xl shadow-sm border p-6">
          <h2 class="text-xl font-bold mb-2">Usage</h2>
          <p class="text-gray-600">Track your API usage</p>
          <div class="mt-4 text-2xl font-bold">0 / ${account.credits_balance} credits</div>
        </div>
        <div class="bg-white rounded-2xl shadow-sm border p-6">
          <h2 class="text-xl font-bold mb-2">Billing</h2>
          <p class="text-gray-600">Manage your subscription</p>
          <button class="mt-4 bg-gray-100 text-gray-800 px-4 py-2 rounded-lg text-sm">Upgrade Plan</button>
        </div>
      </div>

      <div id="jobs" class="bg-white rounded-2xl shadow-sm border p-6">
        <div class="flex justify-between mb-4">
          <h2 class="text-xl font-bold">Recent Jobs</h2>
          <button class="bg-indigo-600 text-white px-4 py-2 rounded-lg">New Job</button>
        </div>
        <div class="space-y-3">
          ${jobRows || '<div class="text-center text-gray-500 py-8">No jobs found</div>'}
        </div>
      </div>
    </div>
  </div>
</body>
</html>
`));
});

// API documentation page
app.get('/docs', (c) => c.html(html`
<!DOCTYPE html>
<html>
<head>
  <script src="https://cdn.tailwindcss.com"></script>
  <title>ParseFlow.ai API Documentation</title>
</head>
<body class="bg-gray-50 min-h-screen">
  <nav class="bg-white shadow-sm border-b">
    <div class="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
      <h1 class="text-2xl font-bold">ParseFlow.ai</h1>
      <div class="flex gap-4">
        <a href="/" class="text-gray-600 hover:text-indigo-600 px-6 py-2 rounded-lg">Home</a>
        <a href="/dashboard" class="text-gray-600 hover:text-indigo-600 px-6 py-2 rounded-lg">Dashboard</a>
        <a href="/docs" class="bg-indigo-100 text-indigo-700 px-6 py-2 rounded-lg">API Docs</a>
      </div>
    </div>
  </nav>

  <div class="max-w-4xl mx-auto py-12 px-4">
    <h1 class="text-4xl font-bold text-gray-900 mb-8">API Documentation</h1>

    <div class="mb-12">
      <h2 class="text-2xl font-bold mb-4">Authentication</h2>
      <p class="mb-4">All API requests require an API key in the Authorization header:</p>
      <pre class="bg-gray-800 text-gray-100 p-4 rounded-lg overflow-x-auto">Authorization: Bearer pf_live_...</pre>
    </div>

    <div class="mb-12">
      <h2 class="text-2xl font-bold mb-4">Upload & Process Document</h2>
      <p class="mb-4">First, get a presigned URL to upload your document directly to our storage:</p>
      <pre class="bg-gray-800 text-gray-100 p-4 rounded-lg overflow-x-auto">POST /v1/uploads/init</pre>
      <pre class="bg-gray-100 p-4 rounded-lg my-4 overflow-x-auto">{
  "content_type": "application/pdf",
  "file_name": "document.pdf"
}</pre>
      <p class="mb-4 mt-4">Then upload your file to the returned presigned URL, and optionally create a processing job:</p>
      <pre class="bg-gray-800 text-gray-100 p-4 rounded-lg overflow-x-auto">POST /v1/extract</pre>
      <pre class="bg-gray-100 p-4 rounded-lg my-4 overflow-x-auto">{
  "url": "https://your-storage.com/file.pdf",  // Optional, if you host the file
  "webhook_url": "https://your-app.com/webhook",
  "mode": "general"  // or "financial" for high-accuracy financial document processing
}</pre>
    </div>

    <div class="mb-12">
      <h2 class="text-2xl font-bold mb-4">Check Job Status</h2>
      <pre class="bg-gray-800 text-gray-100 p-4 rounded-lg overflow-x-auto">GET /v1/jobs/{job_id}</pre>
    </div>

    <div class="mb-12">
      <h2 class="text-2xl font-bold mb-4">Webhook Delivery</h2>
      <p class="mb-4">When processing is complete, we'll send a POST request to your webhook URL with the job result:</p>
      <pre class="bg-gray-100 p-4 rounded-lg my-4 overflow-x-auto">{
  "id": "job_123...",
  "status": "completed",
  "result_url": "https://storage-url-to-result"
}</pre>
    </div>
  </div>
</body>
</html>
`));

export default app;