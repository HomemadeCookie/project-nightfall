import type { BakedAnswer } from "./data/types";

export type Tone = "ok" | "watch" | "alert" | "muted";

const TONES: Record<string, Tone> = {
  normal: "ok",
  flat: "ok",
  low: "ok",
  clear: "ok",
  watch: "watch",
  elevated: "watch",
  slack: "watch",
  near: "watch",
  above_normal: "watch",
  below_normal: "watch",
  surge: "watch",
  up: "watch",
  down: "watch",
  wait: "watch",
  likely: "alert",
  disrupted: "alert",
  direct_exposure: "alert",
  stock_up: "alert",
  no_call: "muted",
  insufficient_data: "muted",
  collecting_data: "muted",
};

export function tone(verdict: string): Tone {
  return TONES[verdict] ?? "muted";
}

export function humanize(verdict: string): string {
  const s = verdict.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const FIL_VERDICT: Record<string, string> = {
  normal: "Normal",
  flat: "Hindi gumagalaw",
  low: "Mababa",
  clear: "Malinaw",
  watch: "Subaybayan",
  elevated: "Mataas",
  slack: "Tahimik",
  near: "Malapit",
  above_normal: "Higit sa normal",
  below_normal: "Mas mababa sa normal",
  surge: "Biglang taas",
  up: "Tataas",
  down: "Bababa",
  wait: "Maghintay",
  likely: "Malamang",
  disrupted: "Naantala",
  direct_exposure: "Tatamaan",
  stock_up: "Mag-imbak",
  no_call: "Walang hula",
  insufficient_data: "Kulang ang datos",
  collecting_data: "Nangongolekta pa",
};

export function verdictLabel(verdict: string, lang: "en" | "fil"): string {
  return lang === "fil" ? (FIL_VERDICT[verdict] ?? humanize(verdict)) : humanize(verdict);
}

export function text(a: Pick<BakedAnswer, "text">, lang: "en" | "fil"): string {
  return (lang === "fil" && a.text.fil) || a.text.en;
}

export function peso(n: number, digits = 2): string {
  return `₱${n.toLocaleString("en-PH", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

export function pct(n: number, digits = 1): string {
  const v = n * 100;
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

/** "2026-10-09" -> "Oct 9". Parsed as a plain date so the viewer's timezone cannot shift it. */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function ageLabel(iso: string, now: Date = new Date()): string {
  const hours = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 36e5));
  if (hours < 1) return "just now";
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export const byQuestion = (answers: BakedAnswer[], id: string): BakedAnswer[] =>
  answers.filter((a) => a.question_id === id);

export const scopeOf = (a: BakedAnswer, key: string): string | undefined => a.scope[key];
