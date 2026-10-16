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
  // Older manifests do not list their files; fall back to probing so they still load.
  const has = (name: string) => manifest.datasets === undefined || manifest.datasets.includes(name);
  const dataset = <T>(name: string) =>
    has(name) ? getJson<T>(`data/${name}.json`, true) : Promise.resolve(null);
  const [answers, fuel, ports, chokepoints, prices, storms, reference, regionsGeo] = await Promise.all([
    getJson<BakedAnswer[]>("answers/index.json"),
    dataset<Bundle["fuel"]>("fuel_weekly"),
    dataset<Bundle["ports"]>("ports_daily"),
    dataset<Bundle["chokepoints"]>("chokepoints"),
    dataset<Bundle["prices"]>("prices"),
    dataset<Bundle["storms"]>("storms"),
    dataset<Bundle["reference"]>("reference"),
    getJson<GeoJSON.FeatureCollection>("ph-regions.json", true),
  ]);
  const reports: Record<string, unknown> = {};
  await Promise.all(
    (manifest.reports ?? manifest.questions.map((q) => q.id)).map(async (id) => {
      const r = await getJson<unknown>(`eval/${id}.json`, true);
      if (r) reports[id] = r;
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
