import { AnswerCard } from "../components/AnswerCard";
import { Chip, ConfidenceChip, StatusChip } from "../components/Chips";
import { Icon } from "../components/Icons";
import { StatTile } from "../components/Layout";
import type { BakedAnswer, Bundle } from "../data/types";
import { byQuestion, peso, shortDate, text, tone, verdictLabel } from "../format";
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

const HEADLINE: Record<string, { en: string; fil: string }> = {
  stock_up: { en: "Stock up on a few things", fil: "Mag-imbak ng ilang bagay" },
  wait: { en: "No rush to buy", fil: "Walang pagmamadali" },
  normal: { en: "Restock as normal", fil: "Mag-restock gaya ng dati" },
};

export function StockUp({ answer }: { answer: BakedAnswer }) {
  const { lang } = useLang();
  const items = ((answer.value as { items?: StockItem[] }).items ?? []).filter((i) => i.verdict !== "normal");
  const head = HEADLINE[answer.verdict] ?? HEADLINE.normal;
  return (
    <div className={`hero-result hero-${tone(answer.verdict)}`}>
      <div className="hero-verdict">
        <span className="hero-badge">
          <Icon
            name={answer.verdict === "normal" ? "check" : answer.verdict === "wait" ? "flat" : "up"}
            size={22}
          />
        </span>
        <div>
          <p className="hero-title">{head ? head[lang] : verdictLabel(answer.verdict, lang)}</p>
          <p className="hero-text">{text(answer, lang)}</p>
        </div>
      </div>
      {items.length > 0 ? (
        <ul className="stock-list">
          {items.map((i) => (
            <li key={i.item} className={`stock-item stock-${tone(i.verdict)}`}>
              <span className="stock-icon">
                <Icon name={i.item} size={22} />
              </span>
              <div className="stock-body">
                <div className="stock-head">
                  <strong>{lang === "fil" ? i.label_fil : i.label_en}</strong>
                  <Chip tone={tone(i.verdict)}>{verdictLabel(i.verdict, lang)}</Chip>
                </div>
                <ul className="reasons">
                  {(lang === "fil" ? i.reasons_fil : i.reasons_en).map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="chips hero-meta">
        <ConfidenceChip level={answer.confidence} />
        <StatusChip status={answer.model.status} />
      </div>
    </div>
  );
}

function fuelTile(a: BakedAnswer | undefined, label: string) {
  if (!a) return null;
  const delta = (a.value as { delta_php_per_l?: number }).delta_php_per_l ?? 0;
  const trend = a.verdict === "up" ? "up" : a.verdict === "down" ? "down" : "flat";
  return (
    <StatTile
      label={label}
      icon="fuel"
      tone={tone(a.verdict)}
      trend={trend}
      value={a.verdict === "insufficient_data" ? "—" : `${delta >= 0 ? "+" : "−"}${peso(Math.abs(delta))}/L`}
      sub={a.confidence === "none" ? "No call yet" : "Change next Tuesday"}
      href="#/fuel"
    />
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
  const fuels = byQuestion(answers, "fuel.next_week");
  const ferries = byQuestion(answers, "ferry.suspension");
  const warned = ferries.filter((a) => a.verdict === "watch" || a.verdict === "likely");
  const ferry = worstFerry(answers);
  const ports = byQuestion(answers, "ports.pressure");
  const portsOff = ports.filter((a) => a.verdict === "elevated" || a.verdict === "slack");
  const lanes = byQuestion(answers, "lanes.upstream_disruption");
  const disrupted = lanes.filter((a) => a.verdict !== "normal");
  const stormCount = storms?.storms.length ?? 0;

  return (
    <>
      <section className="hero" aria-labelledby="stock-h">
        <div className="hero-head">
          <div>
            <p className="eyebrow">
              <Icon name="rice" size={16} />
              {lang === "fil" ? "Para sa tindahan" : "For store owners"}
            </p>
            <h2 id="stock-h">{t("stockUp")}</h2>
          </div>
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
        </div>
        {mine ? <StockUp answer={mine} /> : <p className="meta">{t("noData")}</p>}
      </section>

      <section aria-labelledby="week-h">
        <div className="section-head">
          <h2 id="week-h">{lang === "fil" ? "Ngayong linggo" : "This week"}</h2>
          <p className="meta">
            {lang === "fil" ? "Na-update" : "Updated"} {shortDate(bundle.manifest.generated_at)}
          </p>
        </div>
        <div className="stats">
          {fuelTile(
            fuels.find((a) => a.scope.product === "diesel"),
            "Diesel",
          )}
          {fuelTile(
            fuels.find((a) => a.scope.product === "gasoline"),
            lang === "fil" ? "Gasolina" : "Gasoline",
          )}
          {ferries.length > 0 ? (
            <StatTile
              label={t("sea")}
              icon="ship"
              tone={ferry ? tone(ferry.verdict) : "muted"}
              value={`${warned.length} / ${ferries.length}`}
              sub={lang === "fil" ? "ruta ang may babala" : "routes with a warning"}
              href="#/sea"
            />
          ) : null}
          <StatTile
            label={t("storms")}
            icon="storm"
            tone={stormCount > 0 ? "watch" : "ok"}
            value={stormCount > 0 ? String(stormCount) : t("none")}
            sub={stormCount > 0 ? storms?.storms.map((s) => s.name).join(", ") : t("tracked")}
            href="#/storms"
          />
          {ports.length > 0 ? (
            <StatTile
              label={t("ports")}
              icon="port"
              tone={portsOff.length > 0 ? "watch" : "ok"}
              value={`${ports.length - portsOff.length} / ${ports.length}`}
              sub={lang === "fil" ? "pantalang normal" : "key ports normal"}
              href="#/ports"
            />
          ) : null}
          {lanes.length > 0 ? (
            <StatTile
              label={lang === "fil" ? "Mga kipot" : "Straits"}
              icon="globe"
              tone={disrupted.length > 0 ? "alert" : "ok"}
              value={disrupted.length > 0 ? String(disrupted.length) : lang === "fil" ? "Normal" : "Clear"}
              sub={lang === "fil" ? "daloy ng barko" : "shipping lanes into PH"}
              href="#/supply"
            />
          ) : null}
        </div>
        {portsOff.length > 0 || warned.length > 0 ? (
          <div className="grid">
            {warned.slice(0, 2).map((a) => (
              <AnswerCard
                key={a.scope.ferry_route}
                answer={a}
                title={(a.value as { route?: string }).route}
              />
            ))}
            {portsOff.slice(0, 2).map((a) => (
              <AnswerCard
                key={a.scope.port}
                answer={a}
                title={(a.value as { port_name?: string }).port_name}
              />
            ))}
          </div>
        ) : null}
      </section>
    </>
  );
}
