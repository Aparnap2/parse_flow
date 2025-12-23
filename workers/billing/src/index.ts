export default {
  async fetch(request: Request, env: any) {
    const url = new URL(request.url);
    
    if (url.pathname === '/create-checkout') {
      const { userId, plan } = await request.json();
      
      const productId = plan === 'pro' ? env.LEMON_PRO_PRODUCT_ID : env.LEMON_STARTER_PRODUCT_ID;

      const checkout = await fetch('https://api.lemonsqueezy.com/v1/checkouts', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${env.LEMONSQEEZY_SECRET}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          store_id: env.LEMONSQEEZY_STORE_ID, // Assuming this exists as an env var
          product_id: productId,
          customer_email: userId,
          custom_data: { userId }
        })
      });
      
      const checkoutData = await checkout.json();
      return Response.redirect(checkoutData.data.attributes.url, 302);
    }
    
    if (url.pathname === '/webhook') {
      const sig = request.headers.get('x-lemon-squeezy-signature');
      const body = await request.text();

      // Verify webhook signature
      if (!sig) {
        console.error('Missing signature header');
        return new Response('Unauthorized', { status: 401 });
      }

      // Calculate HMAC of the request body using the secret
      const encoder = new TextEncoder();
      const keyBuffer = encoder.encode(env.LEMONSQEEZY_SECRET);
      const key = await crypto.subtle.importKey(
        'raw',
        keyBuffer,
        { name: 'HMAC', hash: 'SHA256' },
        false,
        ['sign']
      );
      const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(body));
      const expectedSig = Array.from(new Uint8Array(signature))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');

      if (sig !== expectedSig) {
        console.error('Invalid signature');
        return new Response('Unauthorized', { status: 401 });
      }

      const webhookEvent = JSON.parse(body);

      // Only handle specific event types
      const validEvents = ['subscription_created', 'subscription_updated', 'subscription_cancelled'];
      if (!validEvents.includes(webhookEvent.type)) {
        console.log(`Unhandled event type: ${webhookEvent.type}`);
        return new Response('OK');
      }

      // Verify custom_data exists and contains userId
      if (!webhookEvent.data.custom_data || !webhookEvent.data.custom_data.userId) {
        console.error('Missing userId in custom_data');
        return new Response('Bad Request', { status: 400 });
      }

      const userId = webhookEvent.data.custom_data.userId;

      // Determine plan based on product ID
      const productId = webhookEvent.data.attributes.product_id;
      let plan = null;

      if (productId === env.LEMON_STARTER_PRODUCT_ID) {
        plan = 'starter';
      } else if (productId === env.LEMON_PRO_PRODUCT_ID) {
        plan = 'pro';
      } else {
        console.error(`Unknown product ID: ${productId}`);
        return new Response('OK'); // Don't fail for unknown products, just log
      }

      // Update user plan based on subscription status
      let newPlan = plan;
      if (webhookEvent.type === 'subscription_cancelled') {
        // For cancelled subscriptions, downgrade to starter
        newPlan = 'starter';
      }

      await env.DB.prepare(
        `UPDATE users SET plan = ? WHERE id = ?`
      ).bind(newPlan, userId).run();

      console.log(`Updated user ${userId} plan to ${newPlan} for event ${webhookEvent.type}`);

      return new Response('OK');
    }
    
    return new Response('Not Found', { status: 404 });
  }
};