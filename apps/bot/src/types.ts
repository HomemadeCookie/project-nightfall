export type Lang = "en" | "fil";

export interface Env {
  USERS: KV;
  SITE_URL: string;
  TELEGRAM_TOKEN: string;
  WEBHOOK_SECRET: string;
}

/** The slice of Workers KV we use, so tests can fake it. */
export interface KV {
  get(key: string): Promise<string | null>;
  put(key: string, value: string): Promise<void>;
  delete(key: string): Promise<void>;
  list(opts: { prefix: string; cursor?: string }): Promise<{
    keys: { name: string }[];
    list_complete: boolean;
    cursor?: string;
  }>;
}

export interface User {
  region: string;
  lang: Lang;
  subscribed: boolean;
}

export interface Region {
  region_code: string;
  name: string;
  short: string;
}

export interface StockItem {
  item: string;
  label_en: string;
  label_fil: string;
  verdict: string;
  reasons_en: string[];
  reasons_fil: string[];
}

export interface Answer {
  question_id: string;
  scope: Record<string, string>;
  verdict: string;
  confidence: string;
  data_through?: string | null;
  text: { en: string; fil?: string | null };
  value: Record<string, unknown>;
  caveats?: string[];
}

export interface TelegramUpdate {
  message?: { chat: { id: number }; text?: string };
  callback_query?: { id: string; data?: string; message?: { chat: { id: number } } };
}

export interface Button {
  text: string;
  data: string;
}

export interface Deps {
  kv: KV;
  getJson<T>(path: string): Promise<T | null>;
  send(chatId: number, html: string, buttons?: Button[][]): Promise<void>;
  answerCallback(id: string): Promise<void>;
}
