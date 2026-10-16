import { useEffect, useState } from "react";
import type { BakedAnswer, Bundle, Manifest } from "./types";

async function getJson<T>(path: string, optional = false): Promise<T | null> {
  try {
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
    return (await res.json()) as T;
  } catch (err) {
    if (optional) return null;
    throw err;
  }
}

export async function loadBundle(): Promise<Bundle> {
  const manifest = await getJson<Manifest & { empty?: boolean }>("manifest.json");
  if (!manifest || manifest.empty) throw new Error("No data published yet. Run `nightfall publish` first.");
  const [answers, fuel, ports, chokepoints, prices, storms, reference, regionsGeo] = await Promise.all([
    getJson<BakedAnswer[]>("answers/index.json"),
    getJson<Bundle["fuel"]>("data/fuel_weekly.json", true),
    getJson<Bundle["ports"]>("data/ports_daily.json", true),
    getJson<Bundle["chokepoints"]>("data/chokepoints.json", true),
    getJson<Bundle["prices"]>("data/prices.json", true),
    getJson<Bundle["storms"]>("data/storms.json", true),
    getJson<Bundle["reference"]>("data/reference.json", true),
    getJson<GeoJSON.FeatureCollection>("ph-regions.json", true),
  ]);
  const reports: Record<string, unknown> = {};
  await Promise.all(
    manifest.questions.map(async (q) => {
      const r = await getJson<unknown>(`eval/${q.id}.json`, true);
      if (r) reports[q.id] = r;
    }),
  );
  return {
    manifest,
    answers: answers ?? [],
    fuel,
    ports,
    chokepoints,
    prices,
    storms,
    reference,
    reports,
    regionsGeo,
  };
}

export type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; bundle: Bundle };

export function useBundle(): LoadState {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    loadBundle()
      .then((bundle) => alive && setState({ status: "ready", bundle }))
      .catch(
        (e: unknown) =>
          alive && setState({ status: "error", message: e instanceof Error ? e.message : String(e) }),
      );
    return () => {
      alive = false;
    };
  }, []);
  return state;
}
