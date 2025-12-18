import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { logger } from 'hono/logger';
import { zValidator } from '@hono/zod-validator';
import { z } from 'zod';
import { auth } from './lib/auth';
import { withAuth, requireAuth } from './middleware/auth';
import { db } from '@docuflow/database';
import { QueueJobSchema, EngineCallbackSchema } from '@docuflow/shared';
import { DiscordNotifier } from './utils/discord-notifier';
import { HubSpotIntegration } from './utils/hubspot-integration';

// Create the main Hono app
const app = new Hono();

// Global middleware
app.use(logger());

// Add CORS middleware as specified in PRD
app.use('/api/*', cors({
  origin: [process.env.FRONTEND_URL || 'http://localhost:3000', 'https://your-domain.com'],
  allowMethods: ['POST', 'GET', 'OPTIONS'],
  allowHeaders: ['Content-Type', 'x-secret', 'authorization'],
  exposeHeaders: ['Content-Length'],
  maxAge: 600,
  credentials: true,
}));

// Environment validation middleware
app.use(async (c, next) => {
  // Validate critical environment variables
  if (!c.env.DATABASE_URL || !c.env.WEBHOOK_SECRET || !c.env.INTERNAL_SECRET) {
    console.error('Missing required environment variables');
    return c.text('Server Misconfigured', 500);
  }
  await next();
});

// Rate limiting middleware (would use Cloudflare's built-in rate limiting in production)
app.use(async (c, next) => {
  // In a real implementation, this would integrate with Cloudflare's rate limiting
  // using the RATE_LIMITER binding
  const ip = c.req.header('CF-Connecting-IP') || 'unknown';
  // const { success } = await c.env.RATE_LIMITER.limit({ key: ip });
  // if (!success) {
  //   return c.text('Rate Limit Exceeded', 429);
  // }
  await next();
});

// Internal API routes (for workers - requires internal secret)
const internalRoutes = new Hono<{ Bindings: { INTERNAL_SECRET: string } }>();

// Internal document ingestion route - used by email worker
internalRoutes.post('/internal/ingest', async (c) => {
  // Verify internal secret
  const secret = c.req.header('x-secret');
  if (secret !== c.env.INTERNAL_SECRET) {
    return c.text('Unauthorized', 401);
  }

  try {
    const body = await c.req.json();
    const { r2Key, originalName, sender } = body;

    // 1. Find or Create User by Sender Email (Auto-Registration for Email Ingest)
    // In a real app, you might queue this or reject unknown emails.
    // For MVP, we attach to a specific "System User" or try to find the user.
    // Ideally, look up user by email:
    const user = await db.sudo(tx => tx.user.findUnique({ where: { email: sender.address } }));
    
    if (!user) {
        return c.json({ error: "User not found" }, 404);
    }

    // 2. Create Document
    const doc = await db.sudo(tx => tx.document.create({
      data: {
        userId: user.id,
        r2Key,
        originalName,
        status: 'QUEUED'
      }
    }));

    return c.json({
      docId: doc.id,
      workspaceId: user.id // For compatibility, return userId as workspaceId
    });
  } catch (error) {
    console.error('Error creating document record:', error);
    return c.json({ error: 'Failed to create document record' }, 500);
  }
});

app.route('/api', internalRoutes);

// Document proxy route (secure file access for Python engine)
const proxyRoutes = new Hono<{ Bindings: { DOCS_BUCKET: R2Bucket; WEBHOOK_SECRET: string } }>();

proxyRoutes.get('/proxy/:docId', async (c) => {
  // Verify secret from Python engine
  const secret = c.req.header('x-secret');
  if (secret !== c.env.WEBHOOK_SECRET) {
    return c.text('Unauthorized', 401);
  }

  const docId = c.req.param('docId');

  try {
    // Use sudo to bypass RLS for system access
    const doc = await db.sudo(tx => tx.document.findUnique({
      where: { id: docId }
    }));
    
    if (!doc) {
      return c.text('Not Found', 404);
    }

    const obj = await c.env.DOCS_BUCKET.get(doc.r2Key);
    if (!obj) {
      return c.text('File Missing', 404);
    }

    return new Response(obj.body, { 
      headers: { 
        'Content-Type': obj.httpMetadata?.contentType || 'application/octet-stream',
        'Content-Disposition': obj.httpMetadata?.contentDisposition || 'inline'
      } 
    });
  } catch (error) {
    console.error('Error in proxy route:', error);
    return c.text('Internal Server Error', 500);
  }
});

app.route('/api', proxyRoutes);

// Webhook route for Python engine callbacks
const webhookRoutes = new Hono<{ Bindings: { WEBHOOK_SECRET: string } }>();

webhookRoutes.post('/webhook/engine', async (c) => {
  // Verify webhook secret
  const secret = c.req.header('x-secret');
  if (secret !== c.env.WEBHOOK_SECRET) {
    return c.text('Unauthorized', 401);
  }

  try {
    const body = await c.req.json();
    
    // Validate the payload against PRD schema
    const validatedPayload = EngineCallbackSchema.safeParse(body);
    if (!validatedPayload.success) {
      console.error('Invalid webhook payload:', validatedPayload.error.errors);
      return c.json({ error: 'Invalid payload', details: validatedPayload.error.errors }, 400);
    }

    const payload = validatedPayload.data;
    const docId = c.req.query('docId'); // Passed in URL as per PRD

    if (!docId) {
      return c.json({ error: 'Missing docId in query' }, 400);
    }

    // Update document status in the database using sudo for system update
    await db.sudo(tx => tx.document.update({
      where: { id: docId },
      data: {
        status: payload.status,
        vendor: payload.data?.vendor_name,
        total: payload.data?.total_amount,
        date: payload.data?.invoice_date,
        invoiceNumber: payload.data?.invoice_number,
        currency: payload.data?.currency,
        driveFileId: payload.drive_file_id,
        error: payload.error
      }
    }));

    // Send Discord notification about document processing result
    const discord = new DiscordNotifier();
    await discord.sendGeneralNotification(
      `Document ${docId} processing ${payload.status.toLowerCase()}`,
      `Document ${payload.status}`
    );

    // Track in HubSpot
    const hubspot = new HubSpotIntegration();
    await hubspot.trackContactEvent(
      'system', // For MVP, using system as placeholder
      'document_processed',
      {
        document_id: docId,
        status: payload.status,
        timestamp: new Date().toISOString()
      }
    );

    return c.json({ ok: true });
  } catch (error) {
    console.error('Error processing webhook:', error);
    return c.json({ error: 'Webhook processing failed' }, 500);
  }
});

app.route('/api', webhookRoutes);

// Main dashboard route (with Better Auth)
app.get('/dashboard', async (c) => {
  // Get session from Better Auth
  const session = await auth.api.getSession({
    headers: c.req.raw.headers,
  });

  if (!session) {
    return c.redirect('/api/auth/signin');
  }

  // Get user's documents using RLS (filter by userId)
  const userId = session.user.id;
  const docs = await db.withRLS(userId, (tx) =>
    tx.document.findMany({
      where: { userId }, // additional safety
      orderBy: { createdAt: 'desc' },
      take: 50,
      select: {
        id: true,
        status: true,
        originalName: true,
        vendor: true,
        total: true,
        date: true,
        invoiceNumber: true,
        currency: true,
        driveFileId: true,
        error: true,
        createdAt: true
      }
    })
  );

  // Render dashboard HTML
  return c.html(
    <html>
      <head>
        <title>DocuFlow Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <meta http-equiv="refresh" content="10" /> {/* Simple polling for MVP */}
      </head>
      <body class="p-8 bg-gray-50">
        <div class="flex justify-between items-center mb-8">
          <h1 class="text-2xl font-bold">DocuFlow Dashboard</h1>
          <div>
            <span class="mr-4">Welcome, {session.user.name || session.user.email}</span>
            <a href="/api/auth/signout" class="text-blue-600 hover:underline">Sign Out</a>
          </div>
        </div>
        
        <div class="bg-white shadow rounded p-4">
          <h2 class="text-xl font-semibold mb-4">Your Documents</h2>
          <table class="w-full text-left">
            <thead>
              <tr class="border-b">
                <th class="p-2">Status</th>
                <th class="p-2">Vendor</th>
                <th class="p-2">Amount</th>
                <th class="p-2">Date</th>
                <th class="p-2">File</th>
                <th class="p-2">Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {docs.map(d => (
                <tr class="border-b hover:bg-gray-50">
                  <td class="p-2">
                    <span class={`px-2 py-1 rounded text-xs ${
                      d.status === 'COMPLETED' ? 'bg-green-100 text-green-800' : 
                      d.status === 'FAILED' ? 'bg-red-100 text-red-800' : 
                      'bg-yellow-100 text-yellow-800'
                    }`}>
                      {d.status}
                    </span>
                  </td>
                  <td class="p-2">{d.vendor || '-'}</td>
                  <td class="p-2">{d.total ? `$${d.total.toFixed(2)}` : '-'}</td>
                  <td class="p-2">{d.date || '-'}</td>
                  <td class="p-2">
                    {d.driveFileId ? (
                      <a href={`https://drive.google.com/open?id=${d.driveFileId}`} 
                         target="_blank" 
                         class="text-blue-600 underline">
                        View in Drive
                      </a>
                    ) : d.originalName}
                  </td>
                  <td class="p-2">{new Date(d.createdAt).toLocaleDateString()}</td>
                </tr>
              ))}
              {docs.length === 0 && (
                <tr>
                  <td colSpan={6} class="p-4 text-center text-gray-500">
                    No documents yet. Send an email with a PDF attachment to process.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        
        <div class="mt-8 bg-blue-50 p-4 rounded">
          <h3 class="font-semibold">How to Use:</h3>
          <ul class="list-disc pl-5 mt-2 space-y-1">
            <li>Send an email with a PDF, JPG, or PNG attachment to your designated email address</li>
            <li>Your documents will appear here once processed</li>
            <li>Processed documents are available in Google Drive</li>
          </ul>
        </div>
      </body>
    </html>
  );
});

// Mount Better Auth API routes
app.on(["POST", "GET"], "/api/auth/**", (c) => {
  return auth.handler(c.req.raw);
});

// Health check endpoint
app.get('/health', (c) => {
  return c.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Root route
app.get('/', (c) => {
  return c.html(
    <html>
      <head>
        <title>DocuFlow - Document Processing Service</title>
        <script src="https://cdn.tailwindcss.com"></script>
      </head>
      <body class="p-8 bg-gray-50">
        <div class="max-w-2xl mx-auto text-center">
          <h1 class="text-3xl font-bold mb-6">DocuFlow</h1>
          <p class="text-lg mb-8">AI-powered document processing service</p>
          <div class="space-y-4">
            <a href="/api/auth/signin" class="inline-block bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700">
              Sign In with Google
            </a>
            <p class="text-gray-600">or</p>
            <a href="/dashboard" class="inline-block text-blue-600 hover:underline">
              Go to Dashboard
            </a>
          </div>
        </div>
      </body>
    </html>
  );
});

export default app;