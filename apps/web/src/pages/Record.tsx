import { StatusChip } from "../components/Chips";
import { PageHeader } from "../components/Layout";
import type { Bundle } from "../data/types";
import { useLang } from "../i18n";

interface PortRow {
  n_origins?: number;
  mae_naive?: number;
  mae_blend4?: number;
  model?: string;
  ship_forecast?: boolean;
  reason?: string;
}
interface ItemRow {
  n_origins?: number;
  ba_model?: number;
  ba_persistence?: number;
  ba_majority?: number;
  ship?: boolean;
  reason?: string;
}

export function Record({ bundle }: { bundle: Bundle }) {
  const { t } = useLang();
  const ports = (bundle.reports["ports.pressure"] as { ports?: Record<string, PortRow> } | undefined)?.ports;
  const items = (bundle.reports["staples.price_direction"] as { items?: Record<string, ItemRow> } | undefined)
    ?.items;
  return (
    <>
      <PageHeader
        eyebrow="Honesty"
        icon="check"
        title={t("record")}
        lede={
          <>
            Nothing here is presented as more reliable than it is. Each question lists how it is tested and
            the bar it must clear before it publishes a forecast. Status comes from backtest reports, not from
            the code.
          </>
        }
      />
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Question</th>
            <th scope="col">Status</th>
            <th scope="col">Ships when</th>
          </tr>
        </thead>
        <tbody>
          {bundle.manifest.questions.map((q) => (
            <tr key={q.id}>
              <th scope="row">
                {q.id}
                <div className="meta">{q.ask.en}</div>
              </th>
              <td>
                <StatusChip status={q.model_status} />
                {q.report_summary ? <div className="meta">{q.report_summary}</div> : null}
                {q.error ? <div className="meta error">Error while running</div> : null}
              </td>
              <td>{q.ship_when}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {ports ? (
        <section>
          <h3>Port-call forecast vs "repeat last week" (weekly MAE, calls)</h3>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Port</th>
                <th scope="col">Origins</th>
                <th scope="col">Naive</th>
                <th scope="col">4-week mean</th>
                <th scope="col">Forecast published</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(ports).map(([id, r]) => (
                <tr key={id}>
                  <th scope="row">{id}</th>
                  <td>{r.n_origins ?? "-"}</td>
                  <td>{r.mae_naive ?? "-"}</td>
                  <td>{r.mae_blend4 ?? "-"}</td>
                  <td>{r.ship_forecast ? "yes" : (r.reason ?? "no")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {items ? (
        <section>
          <h3>Price direction vs baselines (balanced accuracy, walk-forward)</h3>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Item</th>
                <th scope="col">Origins</th>
                <th scope="col">Model</th>
                <th scope="col">Trend</th>
                <th scope="col">Majority</th>
                <th scope="col">Forecast published</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(items).map(([id, r]) => (
                <tr key={id}>
                  <th scope="row">{id}</th>
                  <td>{r.n_origins ?? "-"}</td>
                  <td>{r.ba_model ?? "-"}</td>
                  <td>{r.ba_persistence ?? "-"}</td>
                  <td>{r.ba_majority ?? "-"}</td>
                  <td>{r.ship ? "yes" : (r.reason ?? "no")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
    </>
  );
}
