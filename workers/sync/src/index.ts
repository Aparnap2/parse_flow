export default {
  async queue(batch: any, env: any, ctx: any) {
    const MAX_RETRY_ATTEMPTS = 5; // Maximum number of retry attempts before dead-lettering

    for (const message of batch.messages) {
      try {
        const { jobId, accountId, r2Key, mode = 'general', webhook_url } = message.body;

        console.log(`Processing job ${jobId} for account ${accountId}, attempt ${message.attempts}, mode: ${mode}`);

        // Fetch job details from the database
        const job = await env.DB.prepare(`
          SELECT id, account_id, status, mode, input_key, output_key, webhook_url, trust_score, error_message, created_at, completed_at
          FROM jobs
          WHERE id = ?
        `).bind(jobId).first();

        if (!job) {
          console.log(`Job ${jobId} not found, acknowledging message`);
          message.ack();
          continue;
        }

        // Call the processing engine to handle the document
        const engineResponse = await fetch(env.ENGINE_URL, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-secret': env.ENGINE_SECRET
          },
          body: JSON.stringify({
            r2_key: r2Key,
            job_id: jobId,
            mode: mode
          })
        });

        if (!engineResponse.ok) {
          console.error(`Engine processing failed: ${engineResponse.status} ${engineResponse.statusText}`);
          // Update job status to failed
          await env.DB.prepare(`
            UPDATE jobs SET status = ?, error_message = ?, completed_at = ?
            WHERE id = ?
          `).bind('failed', `Engine error: ${engineResponse.status}`, Date.now(), jobId).run();
          
          // If we have a webhook URL, notify the user of the failure
          if (webhook_url) {
            try {
              await fetch(webhook_url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  id: jobId,
                  status: 'failed',
                  error: `Engine error: ${engineResponse.status}`
                })
              });
            } catch (webhookError) {
              console.error(`Failed to send webhook notification:`, webhookError);
            }
          }
          
          message.ack();
          continue;
        }

        const result = await engineResponse.json();
        
        // Update job with the processing results
        await env.DB.prepare(`
          UPDATE jobs 
          SET status = ?, output_key = ?, trust_score = ?, completed_at = ?
          WHERE id = ?
        `).bind(
          result.status || 'completed',
          result.output_key,
          result.trust_score,
          Date.now(),
          jobId
        ).run();

        // If the job has a webhook URL, send the result
        if (webhook_url) {
          try {
            await fetch(webhook_url, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                id: jobId,
                status: result.status || 'completed',
                result_url: `${env.R2_PUBLIC_URL}/${result.output_key}`,
                trust_score: result.trust_score
              })
            });
            console.log(`Webhook sent for job ${jobId}`);
          } catch (webhookError) {
            console.error(`Failed to send webhook for job ${jobId}:`, webhookError);
            // Don't fail the job if webhook sending fails, just log the error
          }
        }

        message.ack();
        console.log(`Successfully processed job ${jobId}`);

      } catch (error) {
        console.error(`Sync failed for job ${jobId}, account ${accountId}, attempt ${message.attempts}:`, error);

        // Check if we've exceeded max retry attempts
        if (message.attempts >= MAX_RETRY_ATTEMPTS) {
          console.error(`Max retry attempts (${MAX_RETRY_ATTEMPTS}) reached for job ${jobId}. Moving to dead letter.`);

          try {
            // Update job status to 'failed' in the database
            await env.DB.prepare(`
              UPDATE jobs SET
                status = ?, error_message = ?, completed_at = ?
              WHERE id = ?
            `).bind('failed', `Max retries exceeded: ${error.message || 'Unknown error'}`, Date.now(), message.body.jobId).run();
          } catch (updateError) {
            console.error(`Failed to update job status to 'failed' for job ${message.body.jobId}:`, updateError);
          }

          // Acknowledge the message to prevent further retries
          message.ack();
        } else {
          // Retry with exponential backoff, capped at 300 seconds (5 minutes)
          const delay = Math.min(300, Math.pow(2, message.attempts));
          console.log(`Retrying job ${message.body.jobId} in ${delay} seconds`);
          message.retry(delay);
        }
      }
    }
  }
};