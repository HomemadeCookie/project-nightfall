import { escapeHtml, findRegion, fuelAdvice, regionAdvice } from "./advice";
import { forgetUser, getUser, isLang, recordFeedback, saveUser } from "./store";
import type { Answer, Button, Deps, Lang, Region, TelegramUpdate } from "./types";

const HELP: Record<Lang, string> = {
  en: [
    "<b>Nightfall PH</b>: free weekly guidance on fuel, ports, sea routes, storms and prices.",
    "",
    "/advice: should I stock up this week?",
    "/fuel: next Tuesday's fuel price direction",
    "/region &lt;name&gt;: set your region (e.g. /region Bicol)",
    "/lang en | fil: language",
    "/subscribe | /unsubscribe: daily 7 AM advisory",
    "/forget: delete everything we store about you",
  ].join("\n"),
  fil: [
    "<b>Nightfall PH</b>: libreng lingguhang gabay sa gasolina, pantalan, ruta sa dagat, bagyo at presyo.",
    "",
    "/advice: dapat ba akong mag-imbak ngayong linggo?",
    "/fuel: direksyon ng presyo ng gasolina sa Martes",
    "/region &lt;pangalan&gt;: itakda ang rehiyon (hal. /region Bicol)",
    "/lang en | fil: wika",
    "/subscribe | /unsubscribe: araw-araw na abiso 7 AM",
    "/forget: burahin ang lahat ng datos tungkol sa iyo",
  ].join("\n"),
};

const FEEDBACK: Button[][] = [
  [
    { text: "👍", data: "fb:up" },
    { text: "👎", data: "fb:down" },
  ],
];

async function regions(deps: Deps): Promise<Region[]> {
  const ref = await deps.getJson<{ regions: Region[] }>("data/reference.json");
  return ref?.regions ?? [];
}

async function adviceFor(deps: Deps, chatId: number): Promise<string> {
  const user = await getUser(deps.kv, chatId);
  const [all, rs] = await Promise.all([
    deps.getJson<Answer[]>("answers/retail.stock_up.json"),
    regions(deps),
  ]);
  const answer = all?.find((a) => a.scope.region === user.region);
  return regionAdvice(
    answer,
    rs.find((r) => r.region_code === user.region),
    user.lang,
  );
}

export function parseCommand(text: string): { cmd: string; arg: string } | null {
  const m = /^\/([a-z_]+)(?:@\w+)?(?:\s+([\s\S]*))?$/i.exec(text.trim());
  return m ? { cmd: (m[1] ?? "").toLowerCase(), arg: (m[2] ?? "").trim() } : null;
}

export async function handleMessage(chatId: number, text: string, deps: Deps): Promise<void> {
  const parsed = parseCommand(text);
  const user = await getUser(deps.kv, chatId);
  const lang = user.lang;
  if (!parsed) {
    await deps.send(chatId, HELP[lang]);
    return;
  }
  switch (parsed.cmd) {
    case "start": {
      const rs = await regions(deps);
      const rows: Button[][] = [];
      for (let i = 0; i < rs.length; i += 2) {
        rows.push(rs.slice(i, i + 2).map((r) => ({ text: r.short, data: `r:${r.region_code}` })));
      }
      await deps.send(
        chatId,
        `${HELP[lang]}\n\n${lang === "fil" ? "Piliin ang inyong rehiyon:" : "Pick your region:"}`,
        rows,
      );
      return;
    }
    case "help":
      await deps.send(chatId, HELP[lang]);
      return;
    case "advice":
    case "payo":
      await deps.send(chatId, await adviceFor(deps, chatId), FEEDBACK);
      return;
    case "fuel":
    case "gasolina": {
      const all = (await deps.getJson<Answer[]>("answers/fuel.next_week.json")) ?? [];
      await deps.send(chatId, fuelAdvice(all, lang));
      return;
    }
    case "region": {
      const rs = await regions(deps);
      const found = findRegion(parsed.arg, rs);
      if (!found) {
        const names = rs.map((r) => r.short).join(", ");
        await deps.send(
          chatId,
          escapeHtml(
            lang === "fil"
              ? `Hindi makita ang rehiyon. Subukan: ${names}`
              : `Region not found. Try: ${names}`,
          ),
        );
        return;
      }
      await saveUser(deps.kv, chatId, { region: found.region_code });
      await deps.send(
        chatId,
        escapeHtml(
          lang === "fil"
            ? `Rehiyon: ${found.short}. Gamitin ang /advice.`
            : `Region set to ${found.short}. Try /advice.`,
        ),
      );
      return;
    }
    case "lang": {
      const v = parsed.arg.toLowerCase();
      if (!isLang(v)) {
        await deps.send(chatId, "Use /lang en or /lang fil");
        return;
      }
      await saveUser(deps.kv, chatId, { lang: v });
      await deps.send(chatId, v === "fil" ? "Filipino na ang wika." : "Language set to English.");
      return;
    }
    case "subscribe":
      await saveUser(deps.kv, chatId, { subscribed: true });
      await deps.send(
        chatId,
        lang === "fil"
          ? "Naka-subscribe na. Makakatanggap ng abiso tuwing 7 AM."
          : "Subscribed. You will get the advisory at 7 AM daily.",
      );
      return;
    case "unsubscribe":
      await saveUser(deps.kv, chatId, { subscribed: false });
      await deps.send(chatId, lang === "fil" ? "Naka-unsubscribe na." : "Unsubscribed.");
      return;
    case "forget":
      await forgetUser(deps.kv, chatId);
      await deps.send(chatId, "Done. Your data has been deleted. / Nabura na ang iyong datos.");
      return;
    default:
      await deps.send(chatId, HELP[lang]);
  }
}

export async function handleCallback(
  chatId: number,
  callbackId: string,
  data: string,
  deps: Deps,
): Promise<void> {
  await deps.answerCallback(callbackId);
  if (data.startsWith("r:")) {
    const code = data.slice(2);
    const rs = await regions(deps);
    const found = rs.find((r) => r.region_code === code);
    if (!found) return;
    const user = await saveUser(deps.kv, chatId, { region: code });
    await deps.send(
      chatId,
      escapeHtml(user.lang === "fil" ? `Rehiyon: ${found.short}.` : `Region set to ${found.short}.`),
    );
    await deps.send(chatId, await adviceFor(deps, chatId), FEEDBACK);
  } else if (data === "fb:up" || data === "fb:down") {
    await recordFeedback(deps.kv, data === "fb:up" ? "up" : "down");
    const user = await getUser(deps.kv, chatId);
    await deps.send(chatId, user.lang === "fil" ? "Salamat sa feedback!" : "Thanks for the feedback!");
  }
}

export async function handleUpdate(update: TelegramUpdate, deps: Deps): Promise<void> {
  if (update.message?.text) {
    await handleMessage(update.message.chat.id, update.message.text, deps);
  } else if (update.callback_query?.data && update.callback_query.message) {
    await handleCallback(
      update.callback_query.message.chat.id,
      update.callback_query.id,
      update.callback_query.data,
      deps,
    );
  }
}
