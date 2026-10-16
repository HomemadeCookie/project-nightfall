import type { Answer } from "./contracts";

export type { Answer };
export type BakedAnswer = Answer & { commercial_ok: boolean };

export interface SourceFresh {
  source: string;
  data_through: string | null;
  last_fetch: string | null;
  status: "ok" | "stale" | "missing";
  age_days?: number;
}
export interface SourceInfo {
  name: string;
  license: string[];
  attribution: string;
  cadence: string;
  commercial_ok: boolean;
  reason: string;
  fresh: SourceFresh | null;
}
export interface QuestionInfo {
  id: string;
  tier: 1 | 2 | 3;
  ask: { en: string; fil?: string | null };
  buyers: string[];
  decision: string;
  implemented: boolean;
  model_status: string;
  report_summary?: string | null;
  n_answers: number;
  error?: string | null;
  ship_when: string;
}
export interface Manifest {
  version: string;
  mode: "research" | "commercial";
  generated_at: string;
  banner: string | null;
  sources: SourceInfo[];
  questions: QuestionInfo[];
  counts: { answers: number; blocked: number; errors: number };
}

export interface Point {
  date: string;
  value: number;
}
export interface FuelWeekly {
  diesel: { week_start: string; php_per_l: number; n_days: number }[];
  gasoline: { week_start: string; php_per_l: number; n_days: number }[];
}
export type PortsDaily = Record<
  string,
  { name: string; lat: number; lon: number; series: { date: string; calls: number }[] }
>;
export type Chokepoints = Record<
  string,
  { name: string; series: { week_start: string; transits: number }[] }
>;
export type Prices = Record<
  string,
  { label_en: string; label_fil: string; unit: string; series: { week_end: string; price: number }[] }
>;
export interface Storms {
  storms: {
    id: string;
    name: string;
    alert: string | null;
    max_wind_kmh: number | null;
    issued_at: string;
    points: { time: string; lat: number; lon: number; radius_km: number }[];
  }[];
  segments: { storm_id: string; seq: number; coords: [number, number][]; intensity: string | null }[];
}
export interface Reference {
  ports: {
    port_id: string;
    name: string;
    lat: number;
    lon: number;
    key_port: boolean;
    region_code: string;
  }[];
  ferry_routes: { route_id: string; name: string; line: [number, number][]; serves: string[] }[];
  regions: { region_code: string; name: string; short: string; lat: number; lon: number }[];
}

export interface Bundle {
  manifest: Manifest;
  answers: BakedAnswer[];
  fuel: FuelWeekly | null;
  ports: PortsDaily | null;
  chokepoints: Chokepoints | null;
  prices: Prices | null;
  storms: Storms | null;
  reference: Reference | null;
  reports: Record<string, unknown>;
  regionsGeo: GeoJSON.FeatureCollection | null;
}
