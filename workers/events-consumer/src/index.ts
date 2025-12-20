import { WebhookEventSchema } from "../../../packages/shared/src/types";

type Env = {
  DB: D1Database;
};

export default {
  async queue(batch: MessageBatch<any>, env: Env) {
    for (const msg of batch.messages) {
      try {
        const evt = WebhookEventSchema.parse(msg.body);

        const row = await env.DB.prepare(
          "SELECT url, secret FROM webhooks WHERE id = ? AND project_id = ?"
        ).bind(evt.webhook_id, evt.project_id).first();

        if (!row) {
          msg.ack();
          continue;
        }

        const body = JSON.stringify({
          type: evt.type,
          data: evt.data,
          project_id: evt.project_id,
        });

        // Generate HMAC signature
        const encoder = new TextEncoder();
        const keyData = encoder.encode(row.secret as string);
        const key = await crypto.subtle.importKey(
          "raw",
          keyData,
          { name: "HMAC", hash: "SHA-256" },
          false,
          ["sign"]
        );
        const sigBuf = await crypto.subtle.sign("HMAC", key, encoder.encode(body));
        const sigBytes = Array.from(new Uint8Array(sigBuf));
        const signature = sigBytes.map((b) => b.toString(16).padStart(2, "0")).join("");

        // Send webhook with signature
        const res = await fetch(row.url as string, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-DocuFlow-Signature": signature,
          },
          body,
        });

        if (!res.ok && res.status >= 500) {
          throw new Error(`Webhook ${res.status}`);
        }

        msg.ack();
      } catch (e) {
        const delaySeconds = Math.min(600, Math.pow(2, msg.attempts));
        msg.retry({ delaySeconds });
      }
    }
  },
};