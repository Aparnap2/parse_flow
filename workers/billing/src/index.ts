export default {
  async fetch(request: Request, env: any) {
    const url = new URL(request.url);

    if (url.pathname === '/create-checkout') {
      const { user_id, plan } = await request.json();

      try {
        // Create a Lemon Squeezy checkout URL
        // This is a simplified approach - in a real implementation you'd use the Lemon Squeezy API
        const checkoutUrl = `${env.LEMONSQUEEZY_STORE_URL}/checkout/buy/${env.LEMONSQUEEZY_PRODUCT_VARIANT_ID}?embed=1&checkout[email]=${await getUserEmail(env, user_id)}`;

        // Return the checkout URL
        return Response.redirect(checkoutUrl, 303);
      } catch (error) {
        console.error('Lemon Squeezy checkout creation failed:', error);
        return new Response('Failed to create checkout session', { status: 500 });
      }
    }

    return new Response('Not Found', { status: 404 });
  }
};

// Helper function to get user email
async function getUserEmail(env: any, userId: string): Promise<string> {
  const user = await env.DB.prepare(
    'SELECT email FROM users WHERE id = ?'
  ).bind(userId).first();

  return user?.email || '';
}

// Function to report usage to Lemon Squeezy
export async function reportUsage(env: any, subscription_item_id: string, quantity: number) {
  const LS_API_KEY = env.LEMONSQUEEZY_API_KEY;

  try {
    const response = await fetch('https://api.lemonsqueezy.com/v1/usage-records', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${LS_API_KEY}`,
        'Content-Type': 'application/vnd.api+json'
      },
      body: JSON.stringify({
        data: {
          type: 'usage-records',
          attributes: {
            quantity: quantity,
            action: 'increment'
          },
          relationships: {
            'subscription-item': {
              data: {
                type: 'subscription-items',
                id: subscription_item_id
              }
            }
          }
        }
      })
    });

    if (!response.ok) {
      console.error('Failed to report usage to Lemon Squeezy:', await response.text());
    } else {
      console.log('Successfully reported usage to Lemon Squeezy');
    }
  } catch (error) {
    console.error('Error reporting usage to Lemon Squeezy:', error);
  }
}