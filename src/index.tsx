import { Hono } from 'hono';
import { drizzle } from 'drizzle-orm/d1';
import { googleAuth } from '@hono/oauth-providers/google';
import { users } from './db/schema';
import { cors } from 'hono/cors';

type Bindings = {
  DB: D1Database
  GOOGLE_CLIENT_ID: string
  GOOGLE_CLIENT_SECRET: string
  JWT_SECRET: string
}

const app = new Hono<{ Bindings: Bindings }>();

// Enable CORS for all routes
app.use('*', cors());

// Health check endpoint
app.get('/health', (c) => {
  return c.json({ status: 'ok', timestamp: Date.now() });
});

// Main API endpoint
app.get('/', (c) => {
  return c.html(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>Sarah AI - Configurable Digital Intern</title>
      <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-100">
      <div class="container mx-auto p-8">
        <h1 class="text-3xl font-bold mb-6">Sarah AI - The Configurable Digital Intern</h1>
        <p class="text-lg mb-6">Turn messy emails (PDFs) into perfect, user-defined CSVs/Sheets.</p>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="bg-white p-6 rounded-lg shadow">
            <h2 class="text-xl font-bold mb-4">Authentication</h2>
            <a href="/auth/google" class="bg-red-500 hover:bg-red-600 text-white py-2 px-4 rounded">Sign in with Google</a>
          </div>
          <div class="bg-white p-6 rounded-lg shadow">
            <h2 class="text-xl font-bold mb-4">Blueprint Builder</h2>
            <a href="/blueprints/new" class="bg-blue-500 hover:bg-blue-600 text-white py-2 px-4 rounded">Create New Blueprint</a>
          </div>
        </div>
      </div>
    </body>
    </html>
  `);
});

// 1. Auth Middleware & Routes
app.use('/auth/google', googleAuth({
  scope: ['profile', 'email'],
}));

app.get('/auth/google/callback', async (c) => {
  const user = c.get('user') as { email: string; id: string }; // From googleAuth middleware
  const db = drizzle(c.env.DB);

  // Upsert User
  const [dbUser] = await db.insert(users).values({
    id: crypto.randomUUID(),
    email: user.email,
    google_id: user.id
  }).onConflictDoUpdate({
    target: users.email,
    set: { google_id: user.id }
  }).returning();

  // Set a simple session cookie (in a real app, you'd use proper JWT)
  c.header('Set-Cookie', `user_id=${dbUser.id}; Path=/; HttpOnly; SameSite=Strict`);

  return c.redirect('/dashboard');
});

// Import API routes
import blueprintsApi from './api/blueprints';
import jobsApi from './api/jobs';
import webhooksApi from './api/webhooks';

// API routes with authentication
app.route('/blueprints', blueprintsApi);
app.route('/jobs', jobsApi);
app.route('/webhook', webhooksApi);

export default app;