import { AnswerCard } from "../components/AnswerCard";
import { Sparkline } from "../components/Charts";
import { PageHeader } from "../components/Layout";
import type { Bundle } from "../data/types";
import { byQuestion } from "../format";
import { useLang } from "../i18n";

export function Ports({ bundle }: { bundle: Bundle }) {
  const { t } = useLang();
  const answers = byQuestion(bundle.answers, "ports.pressure");
  return (
    <>
      <PageHeader
        eyebrow="Shipping"
        icon="port"
        title={t("ports")}
        lede={
          <>
            Is each key port busier or quieter than normal? Based on vessel calls; wait times appear when AIS
            data is available.
          </>
        }
      />
      <div className="grid">
        {answers.map((a) => {
          const series = bundle.ports?.[a.scope.port ?? ""]?.series ?? [];
          const v = a.value as {
            calls_7d: number;
            baseline_mean: number;
            port_name: string;
            ais?: { median_wait_h: number } | null;
          };
          return (
            <AnswerCard key={a.scope.port} answer={a} title={v.port_name}>
              <Sparkline
                values={series.slice(-60).map((s) => s.calls)}
                label={`Daily vessel calls at ${v.port_name}, last 60 days`}
              />
              <p className="meta">
                {v.calls_7d} calls in 7 days · typical {Math.round(v.baseline_mean)}
                {v.ais ? ` · median anchorage wait ${v.ais.median_wait_h} h` : ""}
              </p>
            </AnswerCard>
          );
        })}
      </div>
    </>
  );
}
