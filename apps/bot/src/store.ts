import type { KV, Lang, User } from "./types";

const DEFAULT: User = { region: "NCR", lang: "en", subscribed: false };
const key = (chatId: number) => `u:${chatId}`;

export async function getUser(kv: KV, chatId: number): Promise<User> {
  const raw = await kv.get(key(chatId));
  if (!raw) return { ...DEFAULT };
  try {
    return { ...DEFAULT, ...(JSON.parse(raw) as Partial<User>) };
  } catch {
    return { ...DEFAULT };
  }
}

export async function saveUser(kv: KV, chatId: number, patch: Partial<User>): Promise<User> {
  const next = { ...(await getUser(kv, chatId)), ...patch };
  await kv.put(key(chatId), JSON.stringify(next));
  return next;
}

export async function forgetUser(kv: KV, chatId: number): Promise<void> {
  await kv.delete(key(chatId));
}

export async function subscribers(kv: KV): Promise<{ chatId: number; user: User }[]> {
  const out: { chatId: number; user: User }[] = [];
  let cursor: string | undefined;
  do {
    const page = await kv.list({ prefix: "u:", cursor });
    for (const k of page.keys) {
      const chatId = Number(k.name.slice(2));
      const user = await getUser(kv, chatId);
      if (user.subscribed) out.push({ chatId, user });
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return out;
}

/** Aggregate thumbs up/down on advice; only counters are kept, not who voted. */
export async function recordFeedback(kv: KV, vote: "up" | "down"): Promise<void> {
  const k = `fb:${vote}`;
  const n = Number((await kv.get(k)) ?? 0);
  await kv.put(k, String(n + 1));
}

export const isLang = (v: string): v is Lang => v === "en" || v === "fil";
