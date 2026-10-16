import { AnswerCard } from "../components/AnswerCard";
import { Chip, VerdictChip } from "../components/Chips";
import type { BakedAnswer, Bundle } from "../data/types";
import { byQuestion, shortDate, text, tone, verdictLabel } from "../format";
import { useLang } from "../i18n";

interface StockItem {
  item: string;
  label_en: string;
  label_fil: string;
  verdict: string;
  reasons_en: string[];
  reasons_fil: string[];
}

export function regionAnswer(answers: BakedAnswer[], region: string): BakedAnswer | undefined {
  return byQuestion(answers, "retail.stock_up").find((a) => a.scope.region === region);
}

export function worstFerry(answers: BakedAnswer[]): BakedAnswer | undefined {
  const rank: Record<string, number> = { likely: 3, watch: 2, low: 1 };
  return [...byQuestion(answers, "ferry.suspension")].sort(
    (a, b) => (rank[b.verdict] ?? 0) - (rank[a.verdict] ?? 0),
  )[0];
}

export function StockUp({ answer }: { answer: BakedAnswer }) {
  const { lang } = useLang();
  const items = ((answer.value as { items?: StockItem[] }).items ?? []).filter((i) => i.verdict !== "normal");
  return (
    <AnswerCard answer={answer}>
      {items.length > 0 ? (
        <ul className="stock-list">
          {items.map((i) => (
            <li key={i.item}>
              <div className="stock-head">
                <strong>{lang === "fil" ? i.label_fil : i.label_en}</strong>
                <Chip tone={tone(i.verdict)}>{verdictLabel(i.verdict, lang)}</Chip>
              </div>
              <ul className="reasons">
                {(lang === "fil" ? i.reasons_fil : i.reasons_en).map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      ) : null}
    </AnswerCard>
  );
}

export function Home({
  bundle,
  region,
  setRegion,
}: { bundle: Bundle; region: string; setRegion: (r: string) => void }) {
  const { t, lang } = useLang();
  const { answers, reference, storms } = bundle;
  const mine = regionAnswer(answers, region);
  const diesel = byQuestion(answers, "fuel.next_week").find((a) => a.scope.product === "diesel");
  const gasoline = byQuestion(answers, "fuel.next_week").find((a) => a.scope.product === "gasoline");
  const ferry = worstFerry(answers);
  const portsOff = byQuestion(answers, "ports.pressure").filter(
    (a) => a.verdict === "elevated" || a.verdict === "slack",
  );
  const disrupted = byQuestion(answers, "lanes.upstream_disruption").filter((a) => a.verdict !== "normal");

  return (
    <>
      <section aria-labelledby="stock-h">
        <h2 id="stock-h">{t("stockUp")}</h2>
        <label className="field">
          <span>{t("region")}</span>
          <select value={region} onChange={(e) => setRegion(e.target.value)}>
            {(reference?.regions ?? []).map((r) => (
              <option key={r.region_code} value={r.region_code}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        {mine ? <StockUp answer={mine} /> : <p className="meta">{t("noData")}</p>}
      </section>

      <section aria-labelledby="week-h">
        <h2 id="week-h">{lang === "fil" ? "Ngayong linggo" : "This week"}</h2>
        <div className="grid">
          {diesel ? <AnswerCard answer={diesel} title={`${t("fuel")} · diesel`} /> : null}
          {gasoline ? <AnswerCard answer={gasoline} title={`${t("fuel")} · gasoline`} /> : null}
          {ferry ? (
            <AnswerCard answer={ferry} title={t("sea")}>
              <p className="meta">
                {byQuestion(answers, "ferry.suspension").filter((a) => a.verdict !== "low").length} /{" "}
                {byQuestion(answers, "ferry.suspension").length}{" "}
                {lang === "fil" ? "ruta ang may babala" : "routes with a warning"}
              </p>
            </AnswerCard>
          ) : null}
          <article className="card">
            <header className="card-head">
              <h3>{t("storms")}</h3>
            </header>
            <p className="answer-text">
              {t("tracked")}:{" "}
              <strong>
                {storms?.storms.length ? storms.storms.map((s) => s.name).join(", ") : t("none")}
              </strong>
            </p>
          </article>
          {portsOff.length > 0 ? (
            <article className="card">
              <header className="card-head">
                <h3>{t("ports")}</h3>
              </header>
              <ul className="plain">
                {portsOff.map((a) => (
                  <li key={a.scope.port}>
                    <VerdictChip verdict={a.verdict} /> {text(a, lang)}
                  </li>
                ))}
              </ul>
            </article>
          ) : null}
          {disrupted.length > 0 ? (
            <article className="card">
              <header className="card-head">
                <h3>{t("supply")}</h3>
              </header>
              <ul className="plain">
                {disrupted.map((a) => (
                  <li key={a.scope.chokepoint}>
                    <VerdictChip verdict={a.verdict} /> {text(a, lang)}
                  </li>
                ))}
              </ul>
            </article>
          ) : null}
        </div>
        <p className="meta">
          {lang === "fil" ? "Na-update" : "Updated"} {shortDate(bundle.manifest.generated_at)}
        </p>
      </section>
    </>
  );
}
