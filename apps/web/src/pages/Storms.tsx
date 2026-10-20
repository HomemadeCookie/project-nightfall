import { VerdictChip } from "../components/Chips";
import { PageHeader } from "../components/Layout";
import { PhMap } from "../components/PhMap";
import type { Bundle } from "../data/types";
import { byQuestion, text, tone } from "../format";
import { useLang } from "../i18n";

export function Storms({ bundle }: { bundle: Bundle }) {
  const { t, lang } = useLang();
  const sites = byQuestion(bundle.answers, "typhoon.asset_exposure");
  const floods = byQuestion(bundle.answers, "lastmile.flood_access");
  const mapSites = [
    ...sites.map((a) => {
      const v = a.value as { site: string; lat: number; lon: number };
      return {
        id: a.scope.site ?? v.site,
        label: `${v.site}: ${a.verdict}`,
        lat: v.lat,
        lon: v.lon,
        tone: tone(a.verdict),
      };
    }),
    ...floods.flatMap((a) => {
      const v = a.value as { name?: string; lat?: number; lon?: number };
      if (typeof v.lat !== "number" || typeof v.lon !== "number") return [];
      return [
        {
          id: a.scope.chip ?? v.name ?? "flood",
          label: `${v.name ?? "Square"}: ${a.verdict}`,
          lat: v.lat,
          lon: v.lon,
          tone: tone(a.verdict),
        },
      ];
    }),
  ];
  return (
    <>
      <PageHeader
        eyebrow="Hazards"
        icon="storm"
        title={t("storms")}
        lede={
          <>
            Tracked tropical cyclones (JTWC via GDACS) and how close they come to example sites. Bring your
            own sites with the CLI.
          </>
        }
      />
      <div className="split">
        <PhMap
          geo={bundle.regionsGeo}
          ports={bundle.reference?.ports}
          storms={bundle.storms}
          sites={mapSites}
          label="Map of tracked tropical cyclones near the Philippines"
        />
        <div>
          <p className="meta">
            The map shows the Philippine area; a storm farther out (for example near Guam) is listed but may
            be off the edge.
          </p>
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
          <h3>{lang === "fil" ? "Mga parisukat na binabantayan" : "Flood squares"}</h3>
          {floods.length ? (
            <ul className="plain">
              {floods.map((a) => (
                <li key={a.scope.chip}>
                  <VerdictChip verdict={a.verdict} /> {text(a, lang)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="meta">
              {lang === "fil"
                ? "Wala pang parisukat na binaha sa datos na ito."
                : "No flood squares in this data."}
            </p>
          )}
        </div>
      </div>
    </>
  );
}
