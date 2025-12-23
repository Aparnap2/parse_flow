import PostalMime from 'postal-mime';

export default {
  async email(message: any, env: any, ctx: any) {
    try {
      const raw = await new Response(message.raw as ReadableStream).arrayBuffer();
      const parser = new PostalMime();
      const email = await parser.parse(raw as ArrayBuffer);
      
      const attachment = email.attachments?.find((a: any) => 
        a.contentType?.startsWith('application/pdf')
      );
      
      if (!attachment) {
        console.log('No PDF attachment, skipping');
        return;
      }

      const recipient = message.to[0].address;

      // Check if this is the demo email address
      const isDemo = recipient === 'demo@structurize.ai';
      let user, userId;

      if (isDemo) {
        // For demo flow, create or get a dedicated demo user
        const demoUser = await env.DB.prepare(
          'SELECT id FROM users WHERE structurize_email = ?'
        ).bind('demo@structurize.ai').first();

        if (demoUser) {
          userId = demoUser.id;
        } else {
          // Create a demo user if it doesn't exist
          userId = crypto.randomUUID();
          await env.DB.prepare(`
            INSERT INTO users (id, email, structurize_email, google_refresh_token, plan, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
          `).bind(
            userId,
            'demo@structurize.ai',
            'demo@structurize.ai',
            '', // Empty refresh token for demo
            'starter', // Default plan
            Date.now()
          ).run();
        }
      } else {
        // Regular user lookup
        const userResult = await env.DB.prepare(
          'SELECT id FROM users WHERE structurize_email = ?'
        ).bind(recipient).first();

        if (!userResult) {
          console.log('Unknown user:', recipient);
          return;
        }
        userId = userResult.id;
      }

      const r2Key = `inbox/${userId}/${Date.now()}.pdf`;
      await env.INBOX_BUCKET.put(r2Key, attachment.content, {
        httpMetadata: { contentType: attachment.contentType }
      });

      const jobId = crypto.randomUUID();

      // Insert initial job record
      await env.DB.prepare(`
        INSERT INTO jobs (id, user_id, r2_key, status, created_at, updated_at)
        VALUES (?, ?, ?, 'processing', ?, ?)
      `).bind(jobId, userId, r2Key, Date.now(), Date.now()).run();

      // Call the engine to process the document
      const engineResponse = await fetch(env.ENGINE_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-secret': env.ENGINE_SECRET
        },
        body: JSON.stringify({
          r2_key: r2Key,
          job_id: jobId
        })
      });

      if (!engineResponse.ok) {
        console.error(`Engine processing failed: ${engineResponse.status} ${engineResponse.statusText}`);
        // Update job status to failed
        await env.DB.prepare(`
          UPDATE jobs SET status = ?, error = ?, updated_at = ?
          WHERE id = ?
        `).bind('failed', `Engine error: ${engineResponse.status}`, Date.now(), jobId).run();
        return;
      }

      const structuredData = await engineResponse.json();

      // Update job with extracted data
      await env.DB.prepare(`
        UPDATE jobs SET extracted_json = ?, status = ?, updated_at = ?
        WHERE id = ?
      `).bind(JSON.stringify(structuredData), 'pending', Date.now(), jobId).run();

      await env.JOBS_QUEUE.send({ jobId, userId, r2Key, isDemo, originalSender: message.from });
      
      console.log(`Job queued: ${jobId}`);
      
    } catch (error) {
      console.error('Email processing failed:', error);
    }
  }
};