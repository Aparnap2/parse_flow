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

      // For ParseFlow, we need to identify the account based on the email or other means
      // For now, we'll use a simplified approach - in a real system this would be more sophisticated
      let accountId;

      // Check if this is a demo email address
      const isDemo = recipient === 'demo@parseflow.ai';

      if (isDemo) {
        // For demo, we might use a special demo account
        // In a real implementation, you'd have proper account identification
        accountId = 'demo_account_id'; // This is a placeholder
      } else {
        // In a real system, you would identify the account based on:
        // 1. The email domain (if using account-specific domains)
        // 2. A lookup table mapping emails to accounts
        // 3. API key passed in email headers
        // For now, we'll use a placeholder approach
        accountId = `account_for_${recipient.replace(/[^a-zA-Z0-9]/g, '_')}`;
      }

      // Store document in R2 with account-specific path
      const r2Key = `uploads/${accountId}/${Date.now()}.pdf`;
      await env.R2.put(r2Key, attachment.content, {
        httpMetadata: { contentType: attachment.contentType }
      });

      const jobId = crypto.randomUUID();

      // Insert initial job record using the ParseFlow schema
      await env.DB.prepare(`
        INSERT INTO jobs (id, account_id, input_key, status, created_at)
        VALUES (?, ?, ?, 'queued', ?)
      `).bind(jobId, accountId, r2Key, Date.now()).run();

      // Send job to queue for processing
      await env.JOBS_QUEUE.send({
        jobId,
        accountId,
        r2Key,
        mode: 'general', // Default processing mode
        webhook_url: null // No webhook for email-triggered jobs by default
      });

      console.log(`Job queued: ${jobId} for account: ${accountId}`);

    } catch (error) {
      console.error('Email processing failed:', error);
    }
  }
};