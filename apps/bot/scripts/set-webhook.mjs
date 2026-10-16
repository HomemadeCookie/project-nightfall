// Point Telegram at the deployed Worker:  TELEGRAM_TOKEN=... WEBHOOK_SECRET=... WORKER_URL=https://... npm run set-webhook
const { TELEGRAM_TOKEN, WEBHOOK_SECRET, WORKER_URL } = process.env;
if (!TELEGRAM_TOKEN || !WEBHOOK_SECRET || !WORKER_URL) {
  console.error("Set TELEGRAM_TOKEN, WEBHOOK_SECRET and WORKER_URL");
  process.exit(2);
}
const res = await fetch(`https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ url: WORKER_URL, secret_token: WEBHOOK_SECRET, allowed_updates: ["message", "callback_query"] }),
});
console.log(await res.json());
