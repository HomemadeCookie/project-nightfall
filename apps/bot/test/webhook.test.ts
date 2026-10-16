import worker from "../src/index";
import type { Env, KV } from "../src/types";

const kv: KV = {
  get: async () => null,
  put: async () => {},
  delete: async () => {},
  list: async () => ({ keys: [], list_complete: true }),
};
const env: Env = { USERS: kv, SITE_URL: "https://site.test", TELEGRAM_TOKEN: "t", WEBHOOK_SECRET: "s3cret" };

const post = (body: string, secret?: string) =>
  new Request("https://bot.test/", {
    method: "POST",
    body,
    headers: secret ? { "x-telegram-bot-api-secret-token": secret } : {},
  });

describe("webhook", () => {
  it("rejects requests that do not carry the secret", async () => {
    expect((await worker.fetch(post("{}"), env)).status).toBe(401);
    expect((await worker.fetch(post("{}", "wrong"), env)).status).toBe(401);
  });

  it("rejects malformed JSON from an authenticated caller", async () => {
    expect((await worker.fetch(post("not json", "s3cret"), env)).status).toBe(400);
  });

  it("acknowledges empty updates so Telegram does not retry", async () => {
    expect((await worker.fetch(post("{}", "s3cret"), env)).status).toBe(200);
  });

  it("answers a plain GET without doing anything", async () => {
    const res = await worker.fetch(new Request("https://bot.test/"), env);
    expect(res.status).toBe(200);
  });

  it("swallows handler errors but still replies 200", async () => {
    const failing = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network down"));
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    const update = JSON.stringify({ message: { chat: { id: 1 }, text: "/advice" } });
    expect((await worker.fetch(post(update, "s3cret"), env)).status).toBe(200);
    failing.mockRestore();
    err.mockRestore();
  });
});
