import type { Answer, Lang, Region, StockItem } from "./types";

export const escapeHtml = (s: string): string =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const T = {
  header: { en: "This week for", fil: "Ngayong linggo para sa" },
  nothing: { en: "Nothing unusual. Restock as normal.", fil: "Walang kakaiba. Mag-restock gaya ng dati." },
  fuel: { en: "Fuel next Tuesday", fil: "Gasolina sa Martes" },
  data: { en: "Data through", fil: "Datos hanggang" },
  disclaimer: {
    en: "Guidance, not a guarantee. Follow PAGASA and Coast Guard advisories.",
    fil: "Gabay lang ito, hindi garantiya. Sundin ang abiso ng PAGASA at Coast Guard.",
  },
  noData: { en: "No data yet. Please try again later.", fil: "Wala pang datos. Subukan ulit mamaya." },
} as const;

const VERDICT: Record<string, { en: string; fil: string }> = {
  stock_up: { en: "Stock up", fil: "Mag-imbak" },
  wait: { en: "Hold off", fil: "Maghintay" },
  up: { en: "Going up", fil: "Tataas" },
  down: { en: "Going down", fil: "Bababa" },
  flat: { en: "About the same", fil: "Halos pareho" },
};

const pick = (s: { en: string; fil?: string | null }, lang: Lang): string =>
  (lang === "fil" && s.fil) || s.en;

export function regionAdvice(answer: Answer | undefined, region: Region | undefined, lang: Lang): string {
  if (!answer) return escapeHtml(T.noData[lang]);
  const items = ((answer.value as { items?: StockItem[] }).items ?? []).filter((i) => i.verdict !== "normal");
  const name = region?.short ?? answer.scope.region ?? "";
  const lines = [`<b>${T.header[lang]} ${escapeHtml(name)}</b>`, "", escapeHtml(pick(answer.text, lang))];
  if (items.length === 0) {
    lines.push("", escapeHtml(T.nothing[lang]));
  }
  for (const i of items) {
    const label = lang === "fil" ? i.label_fil : i.label_en;
    const reasons = lang === "fil" ? i.reasons_fil : i.reasons_en;
    lines.push(
      "",
      `• <b>${escapeHtml(label)}</b>: ${(VERDICT[i.verdict] ?? { en: i.verdict, fil: i.verdict })[lang]}`,
    );
    for (const r of reasons.slice(0, 2)) lines.push(`  ${escapeHtml(r)}`);
  }
  if (answer.data_through) lines.push("", `<i>${T.data[lang]} ${escapeHtml(answer.data_through)}</i>`);
  lines.push(`<i>${escapeHtml(T.disclaimer[lang])}</i>`);
  return lines.join("\n");
}

export function fuelAdvice(answers: Answer[], lang: Lang): string {
  if (answers.length === 0) return escapeHtml(T.noData[lang]);
  const lines = [`<b>${T.fuel[lang]}</b>`, ""];
  for (const a of answers) {
    const v = VERDICT[a.verdict];
    lines.push(`• ${escapeHtml(pick(a.text, lang))}${v ? ` (${v[lang]})` : ""}`);
  }
  lines.push("", `<i>${escapeHtml(T.disclaimer[lang])}</i>`);
  return lines.join("\n");
}

/** Match free text ("bicol", "ncr", "metro manila", "7") to a region. */
export function findRegion(query: string, regions: Region[]): Region | undefined {
  const q = query
    .trim()
    .toLowerCase()
    .replace(/^region\s+/, "");
  if (!q) return undefined;
  return (
    regions.find((r) => r.region_code.toLowerCase() === q) ??
    regions.find((r) => r.short.toLowerCase() === q || r.name.toLowerCase() === q) ??
    regions.find((r) => r.short.toLowerCase().includes(q) || r.name.toLowerCase().includes(q))
  );
}
