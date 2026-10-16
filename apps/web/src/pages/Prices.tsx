import { AnswerCard } from "../components/AnswerCard";
import { Sparkline } from "../components/Charts";
import type { Bundle } from "../data/types";
import { byQuestion, pct, peso } from "../format";
import { useLang } from "../i18n";

export function Prices({ bundle }: { bundle: Bundle }) {
  const { t, lang } = useLang();
  const answers = byQuestion(bundle.answers, "staples.price_direction");
  return (
    <>
      <h2>{t("prices")}</h2>
      <p className="lede">
        Weekly average retail prices in Metro Manila markets (DA Bantay Presyo). A forecast appears only for
        items where the model has beaten a simple trend in backtests; otherwise you see the price and the
        recent change.
      </p>
      <div className="grid">
        {answers.map((a) => {
          const item = bundle.prices?.[a.scope.item ?? ""];
          const v = a.value as { price_php: number; change_4w: number };
          const label = lang === "fil" ? (item?.label_fil ?? a.scope.item) : (item?.label_en ?? a.scope.item);
          return (
            <AnswerCard key={a.scope.item} answer={a} title={label}>
              <Sparkline
                values={(item?.series ?? []).slice(-52).map((p) => p.price)}
                label={`${label} weekly price, last year`}
              />
              <p className="meta">
                {peso(v.price_php)} / {item?.unit ?? "unit"} · {pct(v.change_4w)} in 4 weeks
              </p>
            </AnswerCard>
          );
        })}
      </div>
    </>
  );
}
