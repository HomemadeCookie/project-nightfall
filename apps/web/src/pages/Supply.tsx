import { AnswerCard } from "../components/AnswerCard";
import { Sparkline } from "../components/Charts";
import { VerdictChip } from "../components/Chips";
import type { Bundle } from "../data/types";
import { byQuestion, pct, text } from "../format";
import { useLang } from "../i18n";

export function Supply({ bundle }: { bundle: Bundle }) {
  const { t, lang } = useLang();
  const arrivals = byQuestion(bundle.answers, "staples.arrivals").filter((a) => a.scope.port === "PH");
  const lanes = byQuestion(bundle.answers, "lanes.upstream_disruption");
  const air = byQuestion(bundle.answers, "aircargo.activity");
  return (
    <>
      <h2>{t("supply")}</h2>
      <h3>Cargo arriving in the Philippines</h3>
      <div className="grid">
        {arrivals.map((a) => (
          <AnswerCard key={a.scope.vessel_class} answer={a} title={(a.value as { group: string }).group} />
        ))}
      </div>
      <h3>Key straits</h3>
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Strait</th>
            <th scope="col">Status</th>
            <th scope="col">vs 12-week norm</th>
            <th scope="col">Trend</th>
          </tr>
        </thead>
        <tbody>
          {lanes.map((a) => {
            const v = a.value as { name: string; pct_vs_baseline: number };
            return (
              <tr key={a.scope.chokepoint}>
                <th scope="row">{v.name}</th>
                <td>
                  <VerdictChip verdict={a.verdict} />
                </td>
                <td>{pct(v.pct_vs_baseline, 0)}</td>
                <td className="spark-cell">
                  <Sparkline
                    values={(bundle.chokepoints?.[a.scope.chokepoint ?? ""]?.series ?? []).map(
                      (s) => s.transits,
                    )}
                    label={`${v.name} weekly transits`}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {air.length > 0 ? (
        <>
          <h3>Air cargo</h3>
          <ul className="plain">
            {air.map((a) => (
              <li key={a.scope.airport}>
                <VerdictChip verdict={a.verdict} /> {text(a, lang)}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  );
}
