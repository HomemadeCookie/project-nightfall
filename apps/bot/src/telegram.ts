import type { Button } from "./types";

export async function sendMessage(
  token: string,
  chatId: number,
  html: string,
  buttons?: Button[][],
): Promise<void> {
  const body: Record<string, unknown> = {
    chat_id: chatId,
    text: html,
    parse_mode: "HTML",
    disable_web_page_preview: true,
  };
  if (buttons?.length) {
    body.reply_markup = {
      inline_keyboard: buttons.map((row) => row.map((b) => ({ text: b.text, callback_data: b.data }))),
    };
  }
  const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok && res.status !== 403) throw new Error(`Telegram sendMessage: HTTP ${res.status}`); // 403 = user blocked the bot
}

export async function answerCallbackQuery(token: string, id: string): Promise<void> {
  await fetch(`https://api.telegram.org/bot${token}/answerCallbackQuery`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ callback_query_id: id }),
  });
}
