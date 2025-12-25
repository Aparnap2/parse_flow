import { Hono } from 'hono';
import Stripe from 'stripe';

const app = new Hono<{ Bindings: Bindings }>();

// 1. Internal Callback (From Modal)
app.post('/internal/complete', async (c) => {
  const secret = c.req.header('x-internal-secret');
  if (secret !== c.env.WORKER_API_SECRET) return c.text('Unauthorized', 401);

  const { job_id, status, metrics } = await c.req.json();

  // Update D1
  await c.env.DB.prepare(
    'UPDATE jobs SET status = ?, completed_at = ? WHERE id = ?'
  ).bind(status, Date.now(), job_id).run();

  // Trigger User Webhook (Fire & Forget)
  const job = await c.env.DB.prepare('SELECT webhook_url FROM jobs WHERE id = ?').bind(job_id).first();
  if (job?.webhook_url) {
    c.executionCtx.waitUntil(fetch(job.webhook_url, {
      method: 'POST',
      body: JSON.stringify({ id: job_id, status })
    }));
  }
  return c.json({ ok: true });
});

// 2. Stripe Webhook (WebCrypto Fix)
app.post('/stripe', async (c) => {
  const sig = c.req.header('stripe-signature');
  const body = await c.req.text();

  const stripe = new Stripe(c.env.STRIPE_SECRET_KEY, {
    apiVersion: '2023-10-16',
    httpClient: Stripe.createFetchHttpClient(),
  });

  try {
    const event = await stripe.webhooks.constructEventAsync(
      body, sig!, c.env.STRIPE_WEBHOOK_SECRET, undefined, Stripe.createSubtleCryptoProvider()
    );
    if (event.type === 'checkout.session.completed') {
        // Add credits logic here
        // In a real implementation, this would update the account's credit balance
        console.log('Checkout session completed:', event.data.object);
    }
  } catch (err) {
    return c.text(`Webhook Error`, 400);
  }
  return c.json({ received: true });
});

export default app;