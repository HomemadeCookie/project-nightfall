import { AnswerCard } from "../components/AnswerCard";
import { Chip } from "../components/Chips";
import { PageHeader } from "../components/Layout";
import { PhMap } from "../components/PhMap";
import type { Bundle } from "../data/types";
import { byQuestion, tone, verdictLabel } from "../format";
import { useLang } from "../i18n";

interface Horizon {
  risk: string;
  peak_wave_m: number | null;
  peak_wind_kmh: number | null;
}

export function Sea({ bundle }: { bundle: Bundle }) {
  const { t, lang } = useLang();
  const answers = byQuestion(bundle.answers, "ferry.suspension");
  const routes = (bundle.reference?.ferry_routes ?? []).map((r) => {
    const a = answers.find((x) => x.scope.ferry_route === r.route_id);
    return {
      id: r.route_id,
      label: `${r.name}: ${a?.verdict ?? "n/a"}`,
      line: r.line,
      tone: tone(a?.verdict ?? "insufficient_data"),
    };
  });
  return (
    <>
      <PageHeader
        eyebrow="Shipping"
        icon="ship"
        title={t("sea")}
        lede={
          <>
            Will RoRo sailings be suspended in the next few days? A rule-based risk from forecast wind, waves
            and storm distance. Always follow Coast Guard advisories.
          </>
        }
      />
      <div className="split">
        <PhMap
          geo={bundle.regionsGeo}
          ports={bundle.reference?.ports}
          routes={routes}
          storms={bundle.storms}
          label="Map of ferry routes coloured by suspension risk"
        />
        <div className="grid one">
          {answers.map((a) => {
            const hs = (a.value as { horizons: Record<string, Horizon>; route: string }).horizons;
            return (
              <AnswerCard key={a.scope.ferry_route} answer={a} title={(a.value as { route: string }).route}>
                <div className="chips">
                  {(["h24", "h72", "h120"] as const).map((h) => (
                    <Chip key={h} tone={tone(hs[h]?.risk ?? "insufficient_data")}>
                      {h.slice(1)} h: {verdictLabel(hs[h]?.risk ?? "insufficient_data", lang)}
                    </Chip>
                  ))}
                </div>
                <p className="meta">
                  Peak wave {hs.h72?.peak_wave_m ?? "-"} m · wind {hs.h72?.peak_wind_kmh ?? "-"} km/h (next 72
                  h)
                </p>
              </AnswerCard>
            );
          })}
        </div>
      </div>
    </>
  );
}
