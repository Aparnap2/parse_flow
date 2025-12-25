import { Context, Next } from 'hono';

// Middleware to validate API key
export const validateApiKey = async (c: Context, next: Next) => {
  const authHeader = c.req.header('Authorization');

  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return c.json({ error: 'Missing or invalid Authorization header' }, 401);
  }

  const apiKey = authHeader.substring(7); // Remove 'Bearer ' prefix

  // Query the database to validate the API key
  const keyResult = await c.env.DB.prepare(
    'SELECT key, account_id, revoked, created_at FROM api_keys WHERE key = ? AND revoked = 0'
  ).bind(apiKey).first();

  if (!keyResult) {
    return c.json({ error: 'Invalid or revoked API key' }, 401);
  }

  // Check if the key is not revoked
  if (keyResult.revoked) {
    return c.json({ error: 'API key has been revoked' }, 401);
  }

  // Verify the key belongs to a valid account
  const accountResult = await c.env.DB.prepare(
    'SELECT id, email, credits_balance FROM accounts WHERE id = ?'
  ).bind(keyResult.account_id).first();

  if (!accountResult) {
    return c.json({ error: 'Associated account not found' }, 401);
  }

  // Check account credits/usage limits
  if (accountResult.credits_balance <= 0) {
    return c.json({ error: 'Insufficient credits' }, 402); // Payment Required
  }

  // Add account info to context for use in downstream handlers
  c.set('account_id', accountResult.id);
  c.set('api_key', apiKey);
  c.set('account_info', {
    id: accountResult.id,
    email: accountResult.email,
    credits_balance: accountResult.credits_balance
  });

  await next();
};