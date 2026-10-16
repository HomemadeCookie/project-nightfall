import { regionAdvice } from "./advice";
import { handleUpdate } from "./commands";
import { subscribers } from "./store";
import { answerCallbackQuery, sendMessage } from "./telegram";
import type { Answer, Deps, Env, Region, TelegramUpdate } from "./types";

function depsFor(env: Env): Deps {
  const base = env.SITE_URL.replace(/\/$/, "");
  return {
    kv: env.USERS,
    async getJson<T>(path: string): Promise<T | null> {
      try {
        const res = await fetch(`${base}/${path}`, {
          cf: { cacheTtl: 600, cacheEverything: true },
        } as RequestInit);
        return res.ok ? ((await res.json()) as T) : null;
      } catch {
        return null;
      }
    },
    send: (chatId, html, buttons) => sendMessage(env.TELEGRAM_TOKEN, chatId, html, buttons),
    answerCallback: (id) => answerCallbackQuery(env.TELEGRAM_TOKEN, id),
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("nightfall-bot", { status: 200 });
    if (request.headers.get("x-telegram-bot-api-secret-token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 401 });
    }
    let update: TelegramUpdate;
    try {
      update = (await request.json()) as TelegramUpdate;
    } catch {
      return new Response("bad request", { status: 400 });
    }
    try {
      await handleUpdate(update, depsFor(env));
    } catch (err) {
      console.error("update failed", err); // answer 200 anyway so Telegram does not retry forever
    }
    return new Response("ok");
  },

  /** Morning push to subscribers. Sends one message each, paced under Telegram's ~30 msg/s limit. */
  async scheduled(_event: unknown, env: Env): Promise<void> {
    const deps = depsFor(env);
    const [all, ref] = await Promise.all([
      deps.getJson<Answer[]>("answers/retail.stock_up.json"),
      deps.getJson<{ regions: Region[] }>("data/reference.json"),
    ]);
    for (const { chatId, user } of await subscribers(env.USERS)) {
      const answer = all?.find((a) => a.scope.region === user.region);
      const region = ref?.regions.find((r) => r.region_code === user.region);
      await deps.send(chatId, regionAdvice(answer, region, user.lang));
      await new Promise((r) => setTimeout(r, 40));
    }
  },
};
