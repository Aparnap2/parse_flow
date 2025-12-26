export default {
  async queue(batch: any, env: any, ctx: any) {
    const MAX_RETRY_ATTEMPTS = 5; // Maximum number of retry attempts before dead-lettering

    for (const message of batch.messages) {
      try {
        const { jobId, userId, r2Key, blueprintId, schema_json } = message.body;

        console.log(`Processing job ${jobId} for user ${userId}, attempt ${message.attempts}, blueprint: ${blueprintId}`);

        // Fetch job details from the database
        const job = await env.DB.prepare(`
          SELECT id, user_id, status, r2_key, result_json, confidence, created_at, completed_at
          FROM jobs
          WHERE id = ?
        `).bind(jobId).first();

        if (!job) {
          console.log(`Job ${jobId} not found, acknowledging message`);
          message.ack();
          continue;
        }

        // Call the processing engine to handle the document with the user's schema
        const engineResponse = await fetch(env.ENGINE_URL, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-secret': env.ENGINE_SECRET
          },
          body: JSON.stringify({
            r2_key: r2Key,
            job_id: jobId,
            schema_json: schema_json // Pass the user-defined schema
          })
        });

        if (!engineResponse.ok) {
          console.error(`Engine processing failed: ${engineResponse.status} ${engineResponse.statusText}`);
          // Update job status to failed
          await env.DB.prepare(`
            UPDATE jobs SET status = ?, completed_at = ?
            WHERE id = ?
          `).bind('failed', Date.now(), jobId).run();

          message.ack();
          continue;
        }

        const result = await engineResponse.json();

        // Determine the status based on confidence level
        // If confidence is low, set status to 'review' for HITL
        let status = 'completed';
        if (result.confidence < 0.8) { // Threshold for requiring review
          status = 'review';
        }

        // Update job with the processing results
        await env.DB.prepare(`
          UPDATE jobs
          SET status = ?, result_json = ?, confidence = ?, completed_at = ?
          WHERE id = ?
        `).bind(
          status,
          JSON.stringify(result.result),
          result.confidence,
          Date.now(),
          jobId
        ).run();

        // Send completion notification to the main API
        try {
          await fetch(`${env.API_URL}/webhook/internal/complete`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'x-internal-secret': env.WORKER_API_SECRET
            },
            body: JSON.stringify({
              job_id: jobId,
              status: status,
              result: result.result,
              confidence: result.confidence
            })
          });
          console.log(`Internal callback sent for job ${jobId}`);
        } catch (callbackError) {
          console.error(`Failed to send internal callback for job ${jobId}:`, callbackError);
        }

        message.ack();
        console.log(`Successfully processed job ${jobId}`);

      } catch (error) {
        console.error(`Sync failed for job ${jobId}, user ${userId}, attempt ${message.attempts}:`, error);

        // Check if we've exceeded max retry attempts
        if (message.attempts >= MAX_RETRY_ATTEMPTS) {
          console.error(`Max retry attempts (${MAX_RETRY_ATTEMPTS}) reached for job ${jobId}. Moving to dead letter.`);

          try {
            // Update job status to 'failed' in the database
            await env.DB.prepare(`
              UPDATE jobs SET
                status = ?, completed_at = ?
              WHERE id = ?
            `).bind('failed', Date.now(), message.body.jobId).run();
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