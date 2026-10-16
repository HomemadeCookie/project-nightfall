import { AnswerCard } from "../components/AnswerCard";
import { LineChart } from "../components/Charts";
import { PageHeader } from "../components/Layout";
import type { Bundle } from "../data/types";
import { byQuestion, peso } from "../format";
import { useLang } from "../i18n";

export function Fuel({ bundle }: { bundle: Bundle }) {
  const { t } = useLang();
  const answers = byQuestion(bundle.answers, "fuel.next_week");
  const fuel = bundle.fuel;
  return (
    <>
      <PageHeader
        eyebrow="Energy"
        icon="fuel"
        title={t("fuel")}
        lede={
          <>
            Will pump prices rise or fall next Tuesday? Estimated from this week's spot-market costs and the
            peso.
          </>
        }
      />
      <div className="grid">
        {answers.map((a) => (
          <AnswerCard
            key={a.scope.product}
            answer={a}
            title={a.scope.product === "diesel" ? "Diesel" : "Gasoline"}
          />
        ))}
      </div>
      {fuel ? (
        <section>
          <h3>Weekly spot cost (₱ per litre)</h3>
          <LineChart
            label="Weekly average spot cost in pesos per litre"
            format={(n) => peso(n, 0)}
            series={[
              {
                name: "Diesel",
                tone: "a",
                points: fuel.diesel.map((w) => ({ x: w.week_start, y: w.php_per_l })),
              },
              {
                name: "Gasoline",
                tone: "b",
                points: fuel.gasoline.map((w) => ({ x: w.week_start, y: w.php_per_l })),
              },
            ]}
          />
          <p className="meta">
            This is the cost of the fuel, not the pump price: taxes, freight and margins sit on top. Only the
            weekly change is used.
          </p>
        </section>
      ) : null}
    </>
  );
}
