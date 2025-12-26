import PostalMime from 'postal-mime';

export default {
  async email(message: any, env: any, ctx: any) {
    try {
      // Rate limiting to prevent infinite loops
      const ip = message.headers.get("x-real-ip") || "unknown";
      const { success } = await env.MY_RATE_LIMITER.limit({ key: ip });
      if (!success) {
        console.log("Rate limit exceeded for", ip);
        return; // Drop silently to save costs
      }

      const raw = await new Response(message.raw as ReadableStream).arrayBuffer();
      const parser = new PostalMime();
      const email = await parser.parse(raw as ArrayBuffer);

      const attachment = email.attachments?.find((a: any) =>
        a.contentType?.startsWith('application/pdf')
      );

      if (!attachment) {
        console.log('No PDF attachment, skipping');
        // Send an "Oops" email to the sender
        try {
          await sendOopsEmail(message.from, "No PDF attachment found in your email. Please attach a PDF file.");
        } catch (emailError) {
          console.error('Failed to send oops email:', emailError);
        }
        return;
      }

      const recipient = message.to[0].address;

      // Find user based on the inbox alias (recipient email)
      const user = await env.DB.prepare(
        'SELECT id FROM users WHERE inbox_alias = ?'
      ).bind(recipient).first();

      if (!user) {
        console.log(`No user found for inbox alias: ${recipient}`);
        return;
      }

      // Find the user's default blueprint
      const blueprint = await env.DB.prepare(
        'SELECT id, schema_json FROM blueprints WHERE user_id = ? LIMIT 1'
      ).bind(user.id).first();

      if (!blueprint) {
        console.log(`No blueprint found for user: ${user.id}`);
        // Send an email to the user asking them to create a blueprint
        try {
          await sendOopsEmail(message.from, "You need to create an extraction blueprint before I can process your documents. Please log in to your dashboard and create a blueprint.");
        } catch (emailError) {
          console.error('Failed to send blueprint request email:', emailError);
        }
        return;
      }

      // Store document in R2 with user-specific path
      const r2Key = `uploads/${user.id}/${Date.now()}.pdf`;
      await env.R2.put(r2Key, attachment.content, {
        httpMetadata: { contentType: attachment.contentType }
      });

      const jobId = crypto.randomUUID();

      // Insert initial job record using the Sarah AI schema
      await env.DB.prepare(`
        INSERT INTO jobs (id, user_id, r2_key, status, created_at)
        VALUES (?, ?, ?, 'queued', ?)
      `).bind(jobId, user.id, r2Key, Date.now()).run();

      // Send job to queue for processing
      await env.JOBS_QUEUE.send({
        jobId,
        userId: user.id,
        r2Key,
        blueprintId: blueprint.id,
        schema_json: blueprint.schema_json
      });

      console.log(`Job queued: ${jobId} for user: ${user.id} with blueprint: ${blueprint.id}`);

    } catch (error) {
      console.error('Email processing failed:', error);
      // Send an "Oops" email to the sender if possible
      try {
        await sendOopsEmail(message.from, "I had trouble reading the PDF you sent. Is it password protected or corrupted?");
      } catch (emailError) {
        console.error('Failed to send oops email:', emailError);
      }
    }
  }
};

// Helper function to send "Oops" emails
async function sendOopsEmail(to: string, message: string) {
  // This is a placeholder - in a real implementation you would use an email service
  console.log(`Would send email to: ${to} with message: ${message}`);
}