import Stripe from 'stripe';

export default {
  async fetch(request: Request, env: any) {
    const url = new URL(request.url);

    if (url.pathname === '/create-checkout') {
      const { account_id, plan } = await request.json();

      // Create a Stripe instance
      const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
        apiVersion: '2023-10-16',
        httpClient: Stripe.createFetchHttpClient(),
      });

      try {
        // Create a Stripe Checkout session
        const session = await stripe.checkout.sessions.create({
          mode: 'subscription',
          customer_email: await getAccountEmail(env, account_id), // Get email for the account
          line_items: [{
            price: plan === 'pro' ? env.STRIPE_PRO_PRICE_ID : env.STRIPE_STARTER_PRICE_ID,
            quantity: 1,
          }],
          success_url: `${env.APP_URL}/dashboard?session_id={CHECKOUT_SESSION_ID}`,
          cancel_url: `${env.APP_URL}/dashboard`,
          metadata: {
            account_id: account_id
          }
        });

        // Return the checkout URL
        return Response.redirect(session.url!, 303);
      } catch (error) {
        console.error('Stripe checkout session creation failed:', error);
        return new Response('Failed to create checkout session', { status: 500 });
      }
    }

    if (url.pathname === '/webhook') {
      const sig = request.headers.get('stripe-signature');
      const body = await request.text();

      let event;

      try {
        // Verify webhook signature using Stripe's method
        const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
          apiVersion: '2023-10-16',
          httpClient: Stripe.createFetchHttpClient(),
        });

        event = await stripe.webhooks.constructEventAsync(
          body,
          sig!,
          env.STRIPE_WEBHOOK_SECRET,
          undefined,
          Stripe.createSubtleCryptoProvider()
        );
      } catch (err) {
        console.error('Webhook signature verification failed:', err);
        return new Response(`Webhook Error: ${err.message}`, { status: 400 });
      }

      // Handle the event
      switch (event.type) {
        case 'checkout.session.completed':
          const session = event.data.object;
          const accountId = session.metadata?.account_id;

          if (accountId) {
            // Add credits to the account after successful checkout
            await addCreditsToAccount(env, accountId, session.metadata?.credits || 100);
            console.log(`Added credits to account ${accountId} after checkout`);
          }
          break;

        case 'customer.subscription.created':
        case 'customer.subscription.updated':
        case 'customer.subscription.deleted':
          // Handle subscription changes
          const subscription = event.data.object;
          const subAccountId = subscription.metadata?.account_id;

          if (subAccountId) {
            // Update account subscription status
            const status = subscription.status;
            await updateAccountSubscription(env, subAccountId, status, subscription.id);
            console.log(`Updated subscription for account ${subAccountId}, status: ${status}`);
          }
          break;

        default:
          console.log(`Unhandled event type: ${event.type}`);
      }

      return new Response('OK', { status: 200 });
    }

    return new Response('Not Found', { status: 404 });
  }
};

// Helper function to get account email
async function getAccountEmail(env: any, accountId: string): Promise<string> {
  const account = await env.DB.prepare(
    'SELECT email FROM accounts WHERE id = ?'
  ).bind(accountId).first();

  return account?.email || '';
}

// Helper function to add credits to account
async function addCreditsToAccount(env: any, accountId: string, credits: number) {
  // In a real implementation, you would add credits based on the plan/tier
  // For now, we'll just add a fixed amount
  const creditAmount = credits || 100; // Default to 100 credits

  await env.DB.prepare(`
    UPDATE accounts
    SET credits_balance = credits_balance + ?
    WHERE id = ?
  `).bind(creditAmount, accountId).run();
}

// Helper function to update account subscription
async function updateAccountSubscription(env: any, accountId: string, status: string, subscriptionId: string) {
  // Update account with subscription info
  await env.DB.prepare(`
    UPDATE accounts
    SET stripe_customer_id = ?,
        updated_at = ?
    WHERE id = ?
  `).bind(subscriptionId, Date.now(), accountId).run();
}