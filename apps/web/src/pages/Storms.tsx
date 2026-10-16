import { VerdictChip } from "../components/Chips";
import { PhMap } from "../components/PhMap";
import type { Bundle } from "../data/types";
import { byQuestion, text, tone } from "../format";
import { useLang } from "../i18n";

export function Storms({ bundle }: { bundle: Bundle }) {
  const { t, lang } = useLang();
  const sites = byQuestion(bundle.answers, "typhoon.asset_exposure");
  const mapSites = sites.map((a) => {
    const v = a.value as { site: string; lat: number; lon: number };
    return {
      id: a.scope.site ?? v.site,
      label: `${v.site}: ${a.verdict}`,
      lat: v.lat,
      lon: v.lon,
      tone: tone(a.verdict),
    };
  });
  return (
    <>
      <h2>{t("storms")}</h2>
      <p className="lede">
        Tracked tropical cyclones (JTWC via GDACS) and how close they come to example sites. Bring your own
        sites with the CLI.
      </p>
      <div className="split">
        <PhMap
          geo={bundle.regionsGeo}
          ports={bundle.reference?.ports}
          storms={bundle.storms}
          sites={mapSites}
          label="Map of tracked tropical cyclones near the Philippines"
        />
        <div>
          <h3>{t("tracked")}</h3>
          {bundle.storms?.storms.length ? (
            <ul className="plain">
              {bundle.storms.storms.map((s) => (
                <li key={s.id}>
                  <strong>{s.name}</strong> · alert {s.alert ?? "n/a"} · max wind{" "}
                  {s.max_wind_kmh ? `${Math.round(s.max_wind_kmh)} km/h` : "n/a"}
                </li>
              ))}
            </ul>
          ) : (
            <p className="meta">{t("none")}</p>
          )}
          <h3>Example sites</h3>
          <ul className="plain">
            {sites.map((a) => (
              <li key={a.scope.site}>
                <VerdictChip verdict={a.verdict} /> {text(a, lang)}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}
