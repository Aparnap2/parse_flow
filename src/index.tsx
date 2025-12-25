import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { validateApiKey } from './lib/auth';

// Import API routes
import extractApi from './api/extract';
import uploadsApi from './api/uploads';
import jobsApi from './api/jobs';
import webhooksApi from './api/webhooks';

const app = new Hono();

// Enable CORS for all routes
app.use('*', cors());

// Health check endpoint
app.get('/health', (c) => {
  return c.json({ status: 'ok', timestamp: Date.now() });
});

// Main API endpoint
app.get('/', (c) => {
  return c.json({
    message: 'Welcome to ParseFlow.ai API',
    version: '1.0',
    endpoints: [
      'POST /v1/extract',
      'POST /v1/uploads/init',
      'GET /v1/jobs/:id',
      'POST /webhook/stripe',
      'POST /webhook/internal/complete'
    ]
  });
});

// API routes with authentication
app.route('/v1/extract', extractApi);
app.route('/v1/uploads', uploadsApi);
app.route('/v1/jobs', jobsApi);
app.route('/webhook', webhooksApi);

// Apply authentication middleware to protected routes
app.use('/v1/*', validateApiKey);

export default app;