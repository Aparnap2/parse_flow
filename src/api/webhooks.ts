import { Hono } from 'hono';

const app = new Hono<{ Bindings: Bindings }>();

// 1. Internal Callback (From Modal)
app.post('/internal/complete', async (c) => {
  const secret = c.req.header('x-internal-secret');
  if (secret !== c.env.WORKER_API_SECRET) return c.text('Unauthorized', 401);

  const { job_id, status, result, confidence } = await c.req.json();

  // Update D1
  await c.env.DB.prepare(
    'UPDATE jobs SET status = ?, result_json = ?, confidence = ?, completed_at = ? WHERE id = ?'
  ).bind(status, JSON.stringify(result), confidence, Date.now(), job_id).run();

  return c.json({ ok: true });
});

// 2. Lemon Squeezy Webhook
app.post('/lemonsqueezy', async (c) => {
  const signature = c.req.header('X-Signature');
  const payload = await c.req.text();

  // In a real implementation, you would verify the Lemon Squeezy signature
  // For now, we'll skip verification for development purposes
  // const secret = c.env.LEMONSQUEEZY_WEBHOOK_SECRET;
  // const expectedSignature = crypto.createHmac('sha256', secret).update(payload).digest('hex');
  // if (!crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expectedSignature))) {
  //   return c.text('Invalid signature', 400);
  // }

  try {
    const event = JSON.parse(payload);
    const eventType = event.meta.event_name;

    if (eventType === 'subscription_created' || eventType === 'subscription_updated') {
      const userEmail = event.data.attributes.user_email;
      const subscriptionId = event.data.id;
      const status = event.data.attributes.status;

      // Find the user in our database
      const user = await c.env.DB.prepare(
        'SELECT id FROM users WHERE email = ?'
      ).bind(userEmail).first();

      if (user) {
        // Update user's subscription status
        await c.env.DB.prepare(`
          UPDATE users
          SET ls_subscription_id = ?
          WHERE id = ?
        `).bind(subscriptionId, user.id).run();
      }
    } else if (eventType === 'subscription_cancelled') {
      const userEmail = event.data.attributes.user_email;
      const subscriptionId = event.data.id;

      // Find the user in our database
      const user = await c.env.DB.prepare(
        'SELECT id FROM users WHERE email = ?'
      ).bind(userEmail).first();

      if (user) {
        // Update user's subscription status
        await c.env.DB.prepare(`
          UPDATE users
          SET ls_subscription_id = NULL
          WHERE id = ?
        `).bind(user.id).run();
      }
    }

    console.log(`Lemon Squeezy event processed: ${eventType}`);
  } catch (err) {
    console.error('Lemon Squeezy webhook error:', err);
    return c.text(`Webhook Error: ${err.message}`, 400);
  }

  return c.json({ received: true });
});

export default app;