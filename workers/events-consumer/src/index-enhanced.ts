type Env = {
  DB: D1Database;
  EVENTS_QUEUE: Queue;
};

// Enhanced error types
class ExternalServiceError extends Error {
  constructor(service: string, message: string, public statusCode: number = 500) {
    super(`External service error (${service}): ${message}`);
    this.name = 'ExternalServiceError';
  }
}

class DatabaseError extends ExternalServiceError {
  constructor(message: string, statusCode: number = 500) {
    super('D1 Database', message, statusCode);
    this.name = 'DatabaseError';
  }
}

class QueueError extends ExternalServiceError {
  constructor(message: string, statusCode: number = 500) {
    super('Queue System', message, statusCode);
    this.name = 'QueueError';
  }
}

// Enhanced error handling wrapper for external service calls
async function withErrorHandling<T>(
  operation: () => Promise<T>,
  serviceName: string,
  context: string,
  event?: any
): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error(`Error in ${serviceName} during ${context}${event ? ` for event ${event.type}` : ''}:`, errorMessage);
    
    if (error instanceof ExternalServiceError) {
      throw error; // Re-throw our custom errors
    }
    
    // Create appropriate error based on service
    if (serviceName === 'D1 Database') {
      throw new DatabaseError(`Failed to ${context}: ${errorMessage}`);
    } else if (serviceName === 'Queue System') {
      throw new QueueError(`Failed to ${context}: ${errorMessage}`);
    } else {
      throw new ExternalServiceError(serviceName, `Failed to ${context}: ${errorMessage}`);
    }
  }
}

// Enhanced database operations with error handling
async function getProjectById(env: Env, projectId: string, event?: any): Promise<any> {
  return await withErrorHandling(
    async () => {
      const project = await env.DB.prepare(
        "SELECT id, name, created_at FROM projects WHERE id = ?"
      ).bind(projectId).first();
      
      if (!project) {
        throw new Error(`Project ${projectId} not found`);
      }
      
      return project;
    },
    'D1 Database',
    `fetch project ${projectId}`,
    event
  );
}

async function getDocumentById(env: Env, docId: string, projectId: string, event?: any): Promise<any> {
  return await withErrorHandling(
    async () => {
      const doc = await env.DB.prepare(
        "SELECT id, status, source_name, content_type, sha256, created_at, updated_at FROM documents WHERE id = ? AND project_id = ?"
      ).bind(docId, projectId).first();
      
      if (!doc) {
        throw new Error(`Document ${docId} not found in project ${projectId}`);
      }
      
      return doc;
    },
    'D1 Database',
    `fetch document ${docId}`,
    event
  );
}

async function getActiveWebhooks(env: Env, projectId: string, event?: any): Promise<any[]> {
  return await withErrorHandling(
    async () => {
      const webhooks = await env.DB.prepare(
        "SELECT id, url, secret FROM webhooks WHERE project_id = ? AND revoked_at IS NULL"
      ).bind(projectId).all();
      
      return webhooks.results as any[];
    },
    'D1 Database',
    `fetch webhooks for project ${projectId}`,
    event
  );
}

async function logEvent(env: Env, event: any, event?: any): Promise<void> {
  return await withErrorHandling(
    async () => {
      await env.DB.prepare(
        `INSERT INTO events (id, project_id, document_id, type, payload, created_at)
         VALUES (?, ?, ?, ?, ?, ?)`
      ).bind(
        crypto.randomUUID(),
        event.project_id,
        event.document_id,
        event.type,
        JSON.stringify(event),
        Date.now()
      ).run();
    },
    'D1 Database',
    `log event ${event.type}`,
    event
  );
}

// Enhanced webhook operations with comprehensive error handling
async function sendWebhookEvent(env: Env, webhook: any, event: any): Promise<void> {
  return await withErrorHandling(
    async () => {
      const payload = JSON.stringify(event);
      
      // Generate HMAC signature
      let signature: string;
      try {
        const signatureBuffer = await crypto.subtle.sign(
          "HMAC",
          await crypto.subtle.importKey(
            "raw",
            new TextEncoder().encode(webhook.secret),
            { name: "HMAC", hash: "SHA-256" },
            false,
            ["sign"]
          ),
          new TextEncoder().encode(payload)
        );
        signature = Array.from(new Uint8Array(signatureBuffer))
          .map(b => b.toString(16).padStart(2, "0"))
          .join("");
      } catch (cryptoError) {
        throw new Error(`Failed to generate HMAC signature: ${cryptoError instanceof Error ? cryptoError.message : String(cryptoError)}`);
      }

      // Send webhook with timeout and retry logic
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout

      try {
        const res = await fetch(webhook.url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-DocuFlow-Signature": `sha256=${signature}`,
            "X-DocuFlow-Event": event.type,
            "X-DocuFlow-Delivery": crypto.randomUUID(),
          },
          body: payload,
          signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (!res.ok) {
          const errorText = await res.text().catch(() => "No response body");
          throw new Error(`Webhook returned ${res.status}: ${res.statusText}. Response: ${errorText}`);
        }

        console.log(`Webhook ${webhook.id} delivered successfully to ${webhook.url}`);
      } catch (fetchError) {
        clearTimeout(timeoutId);
        
        if (fetchError instanceof Error && fetchError.name === 'AbortError') {
          throw new Error(`Webhook request timed out after 30 seconds`);
        }
        
        throw new Error(`Failed to deliver webhook: ${fetchError instanceof Error ? fetchError.message : String(fetchError)}`);
      }
    },
    'Webhook System',
    `deliver webhook to ${webhook.url}`,
    event
  );
}

// Enhanced event processing with comprehensive error handling
async function processEvent(env: Env, event: any): Promise<void> {
  console.log(`Processing event: ${event.type} for project ${event.project_id}, document ${event.document_id}`);
  
  try {
    // Validate event structure
    if (!event.type || !event.project_id || !event.document_id) {
      throw new Error("Invalid event structure: missing required fields");
    }

    // Log the event first (so we have a record even if processing fails)
    await logEvent(env, event, event);

    // Get project and document details for enrichment
    let project: any;
    let document: any;
    
    try {
      project = await getProjectById(env, event.project_id, event);
    } catch (projectError) {
      console.error(`Failed to fetch project details: ${projectError instanceof Error ? projectError.message : String(projectError)}`);
      // Continue without project details
    }

    try {
      document = await getDocumentById(env, event.document_id, event.project_id, event);
    } catch (documentError) {
      console.error(`Failed to fetch document details: ${documentError instanceof Error ? documentError.message : String(documentError)}`);
      // Continue without document details
    }

    // Enrich event with additional context
    const enrichedEvent = {
      ...event,
      project: project ? {
        id: project.id,
        name: project.name,
      } : undefined,
      document: document ? {
        id: document.id,
        status: document.status,
        source_name: document.source_name,
        content_type: document.content_type,
      } : undefined,
    };

    // Get active webhooks for the project
    const webhooks = await getActiveWebhooks(env, event.project_id, event);
    
    if (webhooks.length === 0) {
      console.log(`No active webhooks for project ${event.project_id}`);
      return;
    }

    console.log(`Found ${webhooks.length} active webhooks for project ${event.project_id}`);

    // Send webhook events with comprehensive error handling
    const webhookPromises = webhooks.map(async (webhook) => {
      try {
        await sendWebhookEvent(env, webhook, enrichedEvent);
        return { webhookId: webhook.id, success: true };
      } catch (webhookError) {
        console.error(`Failed to deliver webhook ${webhook.id}:`, webhookError);
        return { 
          webhookId: webhook.id, 
          success: false, 
          error: webhookError instanceof Error ? webhookError.message : String(webhookError)
        };
      }
    });

    const results = await Promise.allSettled(webhookPromises);
    
    // Log webhook delivery results
    const successful = results.filter(r => r.status === 'fulfilled' && r.value.success).length;
    const failed = results.filter(r => r.status === 'fulfilled' && !r.value.success).length;
    const errored = results.filter(r => r.status === 'rejected').length;
    
    console.log(`Webhook delivery completed: ${successful} successful, ${failed} failed, ${errored} errored`);
    
    // Log failed webhook details for debugging
    results.forEach((result, index) => {
      if (result.status === 'fulfilled' && !result.value.success) {
        console.error(`Webhook ${webhooks[index].id} failed: ${result.value.error}`);
      } else if (result.status === 'rejected') {
        console.error(`Webhook ${webhooks[index].id} errored: ${result.reason}`);
      }
    });

  } catch (error) {
    console.error(`Error processing event ${event.type}:`, error);
    
    let errorMessage = "Unknown error during event processing";
    if (error instanceof ExternalServiceError) {
      errorMessage = error.message;
    } else if (error instanceof Error) {
      errorMessage = error.message;
    }
    
    // Log the error but don't re-throw - we don't want to block other events
    // The event has already been logged, so we have a record of the failure
    console.error(`Event processing failed but will not be retried: ${errorMessage}`);
  }
}

export default {
  async queue(batch: MessageBatch<any>, env: Env): Promise<void> {
    console.log(`Processing events batch of ${batch.messages.length} messages`);
    
    for (const msg of batch.messages) {
      try {
        const event = msg.body;
        
        // Basic event validation
        if (!event || typeof event !== 'object') {
          console.error("Invalid message format: not an object");
          msg.ack(); // Acknowledge to prevent infinite retries
          continue;
        }
        
        await processEvent(env, event);
        msg.ack();
        console.log(`Successfully processed event: ${event.type}`);
      } catch (error) {
        console.error(`Error processing message:`, error);
        
        // Enhanced error logging
        if (error instanceof ExternalServiceError) {
          console.error(`External service error (${error.name}): ${error.message}`);
        } else if (error instanceof Error) {
          console.error(`Processing error: ${error.message}`);
          if (error.stack) {
            console.error(`Stack trace: ${error.stack}`);
          }
        }
        
        // Don't re-throw - acknowledge the message to prevent infinite retries
        // The event processing function already handles logging and error reporting
        msg.ack();
      }
    }
    
    console.log(`Completed processing events batch`);
  },
};