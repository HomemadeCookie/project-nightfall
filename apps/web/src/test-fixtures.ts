import type { BakedAnswer, Bundle, Manifest } from "./data/types";

export function answer(
  over: Partial<BakedAnswer> & Pick<BakedAnswer, "question_id" | "verdict" | "scope">,
): BakedAnswer {
  return {
    question_version: 1,
    as_of: "2026-10-16T12:00:00Z",
    confidence: "low",
    coverage: 1,
    text: {
      en: `English text for ${over.question_id}`,
      fil: `Tekstong Filipino para sa ${over.question_id}`,
    },
    model: { name: "m", version: "1", status: "unvalidated" },
    license: ["PUBLIC_DOMAIN"],
    sources: ["eia"],
    attributions: ["EIA"],
    caveats: ["Limit one"],
    value: {},
    commercial_ok: true,
    ...over,
  } as BakedAnswer;
}

export const manifest: Manifest = {
  version: "0.1.0",
  mode: "research",
  generated_at: "2026-10-16T12:00:00Z",
  banner: "Research preview. Some inputs are not yet cleared for commercial use.",
  sources: [
    {
      name: "eia",
      license: ["PUBLIC_DOMAIN"],
      attribution: "U.S. Energy Information Administration",
      cadence: "daily",
      commercial_ok: true,
      reason: "licence allows commercial use",
      fresh: { source: "eia", data_through: "2026-10-15", last_fetch: "2026-10-16T10:00:00Z", status: "ok" },
    },
    {
      name: "open_meteo",
      license: ["NON_COMMERCIAL"],
      attribution: "Open-Meteo",
      cadence: "hourly",
      commercial_ok: false,
      reason: "NON_COMMERCIAL: buy a plan",
      fresh: null,
    },
  ],
  questions: [
    {
      id: "fuel.next_week",
      tier: 1,
      ask: { en: "Will pump prices go up?" },
      buyers: ["fleets"],
      decision: "d",
      implemented: true,
      model_status: "unvalidated",
      report_summary: "0 official adjustments recorded",
      n_answers: 2,
      ship_when: "8 adjustments recorded",
    },
  ],
  counts: { answers: 4, blocked: 0, errors: 0 },
};

const weekStart = (i: number): string => new Date(Date.UTC(2026, 8, 7 + 7 * i)).toISOString().slice(0, 10);

export const answers: BakedAnswer[] = [
  answer({
    question_id: "retail.stock_up",
    scope: { region: "NCR" },
    verdict: "stock_up",
    value: {
      region: "Metro Manila",
      hazard_level: 0,
      items: [
        {
          item: "rice",
          label_en: "Rice",
          label_fil: "Bigas",
          verdict: "stock_up",
          reasons_en: ["Rice is likely to get pricier."],
          reasons_fil: ["Malamang tumaas ang bigas."],
        },
        {
          item: "sugar",
          label_en: "Sugar",
          label_fil: "Asukal",
          verdict: "normal",
          reasons_en: [],
          reasons_fil: [],
        },
      ],
    },
  }),
  answer({ question_id: "retail.stock_up", scope: { region: "V" }, verdict: "normal" }),
  answer({
    question_id: "fuel.next_week",
    scope: { product: "diesel" },
    verdict: "up",
    value: { delta_php_per_l: 2.8 },
  }),
  answer({
    question_id: "fuel.next_week",
    scope: { product: "gasoline" },
    verdict: "down",
    value: { delta_php_per_l: -2.4 },
  }),
  answer({
    question_id: "ferry.suspension",
    scope: { ferry_route: "matnog-allen" },
    verdict: "likely",
    value: {
      route: "Matnog - Allen",
      horizons: {
        h24: { risk: "watch" },
        h72: { risk: "likely", peak_wave_m: 4.5, peak_wind_kmh: 65 },
        h120: { risk: "likely" },
      },
    },
  }),
  answer({
    question_id: "ports.pressure",
    scope: { port: "MNL" },
    verdict: "elevated",
    value: { calls_7d: 160, baseline_mean: 134, port_name: "Manila", ais: null },
  }),
];

export const bundle: Bundle = {
  manifest,
  answers,
  fuel: {
    diesel: Array.from({ length: 6 }, (_, i) => ({ week_start: weekStart(i), php_per_l: 38 + i, n_days: 5 })),
    gasoline: Array.from({ length: 6 }, (_, i) => ({
      week_start: weekStart(i),
      php_per_l: 36 - i,
      n_days: 5,
    })),
  },
  ports: {
    MNL: {
      name: "Manila",
      lat: 14.59,
      lon: 120.87,
      series: Array.from({ length: 30 }, (_, i) => ({
        date: new Date(Date.UTC(2026, 8, 1 + i)).toISOString().slice(0, 10),
        calls: 15 + (i % 5),
      })),
    },
  },
  chokepoints: null,
  prices: null,
  storms: {
    storms: [
      {
        id: "1",
        name: "CHAMPI-26",
        alert: "Orange",
        max_wind_kmh: 120,
        issued_at: "2026-10-16T00:00:00Z",
        points: [{ time: "2026-10-16T00:00:00Z", lat: 12, lon: 128, radius_km: 150 }],
      },
    ],
    segments: [],
  },
  reference: {
    ports: [{ port_id: "MNL", name: "Manila", lat: 14.59, lon: 120.87, key_port: true, region_code: "NCR" }],
    ferry_routes: [
      {
        route_id: "matnog-allen",
        name: "Matnog - Allen",
        line: [
          [12.58, 124.08],
          [12.5, 124.28],
        ],
        serves: ["Bicol"],
      },
    ],
    regions: [
      { region_code: "NCR", name: "National Capital Region", short: "Metro Manila", lat: 14.6, lon: 121 },
      { region_code: "V", name: "Bicol Region", short: "Bicol", lat: 13.4, lon: 123.4 },
    ],
  },
  reports: {},
  regionsGeo: {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: { code: "NCR", name: "NCR" },
        geometry: {
          type: "MultiPolygon",
          coordinates: [
            [
              [
                [120.9, 14.4],
                [121.2, 14.4],
                [121.2, 14.8],
                [120.9, 14.8],
                [120.9, 14.4],
              ],
            ],
          ],
        },
      },
      {
        type: "Feature",
        properties: { code: "V", name: "Bicol" },
        geometry: {
          type: "MultiPolygon",
          coordinates: [
            [
              [
                [123, 12.5],
                [124.5, 12.5],
                [124.5, 14],
                [123, 14],
                [123, 12.5],
              ],
            ],
          ],
        },
      },
    ],
  },
};
