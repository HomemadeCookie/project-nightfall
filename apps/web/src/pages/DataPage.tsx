import { Chip } from "../components/Chips";
import type { Bundle } from "../data/types";
import { ageLabel, shortDate } from "../format";
import { useLang } from "../i18n";

export function DataPage({ bundle }: { bundle: Bundle }) {
  const { t } = useLang();
  const m = bundle.manifest;
  return (
    <>
      <h2>{t("data")}</h2>
      <p className="lede">
        {m.mode === "research"
          ? "This is a research preview. Sources marked “research only” are not cleared for commercial use, so answers built on them are not licensed for resale."
          : "Commercial mode: only answers whose every input source is cleared are published."}
      </p>
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Source</th>
            <th scope="col">Freshness</th>
            <th scope="col">Licence</th>
            <th scope="col">Commercial use</th>
          </tr>
        </thead>
        <tbody>
          {m.sources.map((s) => (
            <tr key={s.name}>
              <th scope="row">
                {s.name}
                <div className="meta">{s.attribution}</div>
              </th>
              <td>
                <Chip
                  tone={s.fresh?.status === "ok" ? "ok" : s.fresh?.status === "stale" ? "watch" : "muted"}
                >
                  {s.fresh?.status ?? "missing"}
                </Chip>
                <div className="meta">
                  {s.fresh?.data_through ? `through ${shortDate(s.fresh.data_through)}` : "no data"}
                  {s.fresh?.last_fetch ? ` · fetched ${ageLabel(s.fresh.last_fetch)}` : ""}
                </div>
              </td>
              <td>{s.license.join(", ")}</td>
              <td>
                <Chip tone={s.commercial_ok ? "ok" : "alert"}>
                  {s.commercial_ok ? "cleared" : "not cleared"}
                </Chip>
                <div className="meta">{s.reason}</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="meta">
        Region boundaries: geoBoundaries (CC BY 3.0 IGO). Built {shortDate(m.generated_at)} · v{m.version}.
      </p>
    </>
  );
}
