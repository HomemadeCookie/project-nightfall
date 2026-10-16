import { type Tone, tone, verdictLabel } from "../format";
import { useLang } from "../i18n";

export function Chip({
  tone: t,
  children,
  title,
}: { tone: Tone; children: React.ReactNode; title?: string }) {
  return (
    <span className={`chip chip-${t}`} title={title}>
      {children}
    </span>
  );
}

export function VerdictChip({ verdict }: { verdict: string }) {
  const { lang } = useLang();
  return <Chip tone={tone(verdict)}>{verdictLabel(verdict, lang)}</Chip>;
}

const STATUS_TONE: Record<string, Tone> = {
  validated: "ok",
  experimental: "watch",
  unvalidated: "muted",
  planned: "muted",
};

export function StatusChip({ status }: { status: string }) {
  return (
    <Chip
      tone={STATUS_TONE[status] ?? "muted"}
      title="How well this model has been tested against real outcomes"
    >
      {status}
    </Chip>
  );
}

export function ConfidenceChip({ level }: { level: string }) {
  const { t } = useLang();
  const t2: Tone = level === "high" ? "ok" : level === "medium" ? "watch" : "muted";
  return (
    <Chip tone={t2}>
      {t("confidence")}: {level}
    </Chip>
  );
}
