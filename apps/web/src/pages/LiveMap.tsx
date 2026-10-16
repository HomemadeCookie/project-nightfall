import { useMemo, useRef, useState } from "react";
import { Chip } from "../components/Chips";
import { Icon } from "../components/Icons";
import { PageHeader } from "../components/Layout";
import { PH_BOX, kmToPx, makeProjection } from "../components/PhMap";
import type { BakedAnswer, Bundle } from "../data/types";
import { type Tone, byQuestion, pct, shortDate, text, tone, verdictLabel } from "../format";
import { type Lang, useLang } from "../i18n";

export type PlaceKind = "region" | "port" | "route" | "storm";

export interface Place {
  id: string;
  kind: PlaceKind;
  name: string;
  tone: Tone;
  verdict: string;
  headline: string;
  lines: string[];
  significant: boolean;
}

const H = 640;
// The map frames the Philippines plus storm activity within reach of it. A storm farther out is shown as an
// arrow on the edge instead of zooming out until the islands are specks.
const NEAR = { lonMin: 108, lonMax: 138, latMin: 0, latMax: 28 };
const isNear = ([lon, lat]: [number, number]) =>
  lon >= NEAR.lonMin && lon <= NEAR.lonMax && lat >= NEAR.latMin && lat <= NEAR.latMax;
const LABEL_LEFT = new Set(["SBM"]); // Subic Bay sits just west of Manila: label it on the other side
const KIND_ICON: Record<PlaceKind, string> = { region: "rice", port: "port", route: "ship", storm: "storm" };
const KIND_LABEL: Record<PlaceKind, Record<Lang, string>> = {
  region: { en: "Region", fil: "Rehiyon" },
  port: { en: "Port", fil: "Pantalan" },
  route: { en: "Ferry route", fil: "Ruta ng barko" },
  storm: { en: "Storm", fil: "Bagyo" },
};
const SIGNIFICANT: Tone[] = ["watch", "alert"];
const RANK: Record<Tone, number> = { alert: 0, watch: 1, ok: 2, muted: 3 };

interface StockItem {
  label_en: string;
  label_fil: string;
  verdict: string;
  reasons_en: string[];
  reasons_fil: string[];
}

/** Compile every answer into map places: the single source the map, the tooltip and the list all read. */
export function buildPlaces(bundle: Bundle, lang: Lang): Place[] {
  const { answers, reference, storms } = bundle;
  const places: Place[] = [];
  const by = (q: string, key: string) => new Map(byQuestion(answers, q).map((a) => [a.scope[key] ?? "", a]));

  const stock = by("retail.stock_up", "region");
  for (const r of reference?.regions ?? []) {
    const a = stock.get(r.region_code);
    if (!a) continue;
    const items = ((a.value as { items?: StockItem[] }).items ?? []).filter((i) => i.verdict !== "normal");
    places.push(
      place(
        `region:${r.region_code}`,
        "region",
        r.name,
        a,
        lang,
        items.map((i) =>
          `${lang === "fil" ? i.label_fil : i.label_en}: ${verdictLabel(i.verdict, lang)}. ${(lang === "fil" ? i.reasons_fil : i.reasons_en)[0] ?? ""}`.trim(),
        ),
      ),
    );
  }

  const ports = by("ports.pressure", "port");
  const arrivals = byQuestion(answers, "staples.arrivals");
  for (const p of reference?.ports ?? []) {
    const a = ports.get(p.port_id);
    if (!a) continue;
    const lines = arrivals
      .filter((x) => x.scope.port === p.port_id)
      .map((x) => {
        const v = x.value as { group?: string; pct_vs_norm?: number };
        return `${v.group ?? x.scope.vessel_class}: ${verdictLabel(x.verdict, lang)} (${pct(v.pct_vs_norm ?? 0, 0)})`;
      });
    const ais = (a.value as { ais?: { median_wait_h: number } | null }).ais;
    if (ais) lines.unshift(`Median anchorage wait ${ais.median_wait_h} h (AIS)`);
    places.push(place(`port:${p.port_id}`, "port", p.name, a, lang, lines));
  }

  const ferries = by("ferry.suspension", "ferry_route");
  for (const r of reference?.ferry_routes ?? []) {
    const a = ferries.get(r.route_id);
    if (!a) continue;
    const hs =
      (
        a.value as {
          horizons?: Record<
            string,
            { risk?: string; peak_wave_m?: number | null; peak_wind_kmh?: number | null }
          >;
        }
      ).horizons ?? {};
    const lines = [
      ["h24", "24 h"],
      ["h72", "72 h"],
      ["h120", "5 days"],
    ].map(([k, label]) => `${label}: ${verdictLabel(hs[k ?? ""]?.risk ?? "insufficient_data", lang)}`);
    const h72 = hs.h72;
    if (h72?.peak_wave_m != null)
      lines.push(`Peak wave ${h72.peak_wave_m} m · wind ${h72.peak_wind_kmh ?? "-"} km/h (72 h)`);
    places.push(place(`route:${r.route_id}`, "route", r.name, a, lang, lines));
  }

  for (const s of storms?.storms ?? []) {
    const last = s.points[s.points.length - 1];
    const strong = (s.max_wind_kmh ?? 0) >= 118 || s.alert === "Red" || s.alert === "Orange";
    const t: Tone = strong ? "alert" : "watch";
    places.push({
      id: `storm:${s.id}`,
      kind: "storm",
      name: s.name,
      tone: t,
      verdict: strong ? "likely" : "watch",
      headline: `${s.name}: alert ${s.alert ?? "n/a"}, max wind ${s.max_wind_kmh ? Math.round(s.max_wind_kmh) : "?"} km/h.`,
      lines: [
        last ? `Forecast through ${shortDate(last.time)}` : "",
        "Track by JTWC via GDACS. Forecast error grows with lead time.",
      ].filter(Boolean),
      significant: true,
    });
  }
  return places;
}

function place(
  id: string,
  kind: PlaceKind,
  name: string,
  a: BakedAnswer,
  lang: Lang,
  lines: string[],
): Place {
  const t = tone(a.verdict);
  return {
    id,
    kind,
    name,
    tone: t,
    verdict: a.verdict,
    headline: text(a, lang),
    lines: lines.filter(Boolean),
    significant: SIGNIFICANT.includes(t),
  };
}

type Layers = Record<PlaceKind, boolean>;

export function LiveMap({ bundle }: { bundle: Bundle }) {
  const { lang, t } = useLang();
  const places = useMemo(() => buildPlaces(bundle, lang), [bundle, lang]);
  const byId = useMemo(() => new Map(places.map((p) => [p.id, p])), [places]);
  const [hover, setHover] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const [tip, setTip] = useState<{ x: number; y: number } | null>(null);
  const [layers, setLayers] = useState<Layers>({ region: true, port: true, route: true, storm: true });
  const wrap = useRef<HTMLDivElement>(null);

  const frame = useMemo(() => {
    const pts: [number, number][] = [];
    for (const st of bundle.storms?.storms ?? []) for (const q of st.points) pts.push([q.lon, q.lat]);
    for (const seg of bundle.storms?.segments ?? []) for (const c of seg.coords) pts.push([c[0], c[1]]);
    return pts.filter(isNear);
  }, [bundle.storms]);
  // Size the canvas to its content so a wide frame does not leave dead bands beside a tall country.
  const W = useMemo(() => {
    const probe = makeProjection(1000, 1000, frame);
    const xy = [...(PH_BOX.coordinates as [number, number][]), ...frame].map((c) => probe(c) ?? [0, 0]);
    const xs = xy.map((p) => p[0] ?? 0);
    const ys = xy.map((p) => p[1] ?? 0);
    const aspect = (Math.max(...xs) - Math.min(...xs)) / Math.max(1, Math.max(...ys) - Math.min(...ys));
    return Math.min(960, Math.max(440, Math.round(H * aspect)));
  }, [frame]);
  const projection = useMemo(() => makeProjection(W, H, frame), [W, frame]);
  const project = (c: [number, number]) => projection(c) as [number, number] | null;
  const path = (pts: [number, number][]) =>
    pts
      .map((c, i) => {
        const p = project(c);
        return p ? `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}` : "";
      })
      .join(" ");

  const activeId = hover ?? pinned;
  const active = activeId ? byId.get(activeId) : undefined;
  const significant = places.filter((p) => p.significant).sort((a, b) => RANK[a.tone] - RANK[b.tone]);

  const handlers = (id: string, label: string) => ({
    tabIndex: 0,
    role: "button",
    "aria-label": label,
    "aria-pressed": pinned === id,
    onMouseEnter: () => setHover(id),
    onMouseMove: (e: React.MouseEvent) => {
      const r = wrap.current?.getBoundingClientRect();
      if (r) setTip({ x: e.clientX - r.left, y: e.clientY - r.top });
    },
    onMouseLeave: () => {
      setHover(null);
      setTip(null);
    },
    onFocus: () => setHover(id),
    onBlur: () => setHover(null),
    onClick: () => setPinned((cur) => (cur === id ? null : id)),
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setPinned((cur) => (cur === id ? null : id));
      }
    },
  });
  const cls = (p: Place | undefined, base: string) =>
    `${base} tone-${p?.tone ?? "muted"}${activeId === p?.id ? " is-active" : ""}${p?.significant ? " is-significant" : ""}`;

  return (
    <>
      <PageHeader
        eyebrow={lang === "fil" ? "Lahat sa isang tingin" : "Everything at a glance"}
        icon="globe"
        title={t("map")}
        lede={
          lang === "fil"
            ? "Itapat ang cursor (o pindutin) ang isang lugar para makita kung ano ang nangyayari. Ang kulay ay nagpapakita ng antas ng babala."
            : "Hover over (or tap) a region, port, ferry route or storm to see what's happening there. Colour shows how much attention it needs."
        }
      />
      <div className="lm">
        <div
          className="lm-map"
          ref={wrap}
          onKeyDown={(e) => {
            if (e.key === "Escape") setPinned(null);
          }}
        >
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="map lm-svg"
            // biome-ignore lint/a11y/useSemanticElements: an SVG of interactive shapes is a group; <fieldset> cannot hold SVG
            role="group"
            aria-label="Interactive map of current signals"
          >
            {/* biome-ignore lint/a11y/useKeyWithClickEvents: mouse shortcut to unpin; keyboard users press Escape (handled on the wrapper) */}
            <rect className="sea" width={W} height={H} onClick={() => setPinned(null)} />
            {layers.region
              ? bundle.regionsGeo?.features.map((f) => {
                  const code = String(f.properties?.code);
                  const p = byId.get(`region:${code}`);
                  const g = f.geometry as GeoJSON.MultiPolygon;
                  const d = g.coordinates
                    .flatMap((poly) =>
                      poly.map((ring) => `${path(ring.map((c) => [c[0] ?? 0, c[1] ?? 0]))}Z`),
                    )
                    .join(" ");
                  return p ? (
                    <path
                      key={code}
                      d={d}
                      className={cls(p, "lm-region")}
                      {...handlers(p.id, `${p.name}: ${verdictLabel(p.verdict, lang)}`)}
                    />
                  ) : (
                    <path key={code} d={d} className="lm-region tone-muted" />
                  );
                })
              : bundle.regionsGeo?.features.map((f) => (
                  <path
                    key={String(f.properties?.code)}
                    className="region"
                    d={(f.geometry as GeoJSON.MultiPolygon).coordinates
                      .flatMap((poly) =>
                        poly.map((ring) => `${path(ring.map((c) => [c[0] ?? 0, c[1] ?? 0]))}Z`),
                      )
                      .join(" ")}
                  />
                ))}
            {layers.storm
              ? (bundle.storms?.storms ?? []).map((st) => {
                  const p = byId.get(`storm:${st.id}`);
                  if (!p || st.points.length === 0) return null;
                  const now = Date.parse(bundle.manifest.generated_at);
                  const current = [...st.points].sort(
                    (x, y) => Math.abs(Date.parse(x.time) - now) - Math.abs(Date.parse(y.time) - now),
                  )[0];
                  if (!current) return null;
                  const forecast = (bundle.storms?.segments ?? [])
                    .filter((g) => g.storm_id === st.id)
                    .sort((x, y) => x.seq - y.seq)
                    .flatMap((g) => g.coords);
                  const c = project([current.lon, current.lat]);
                  if (!c) return null;
                  const onMap = c[0] >= 0 && c[0] <= W && c[1] >= 0 && c[1] <= H;
                  const label = `${p.name}: ${verdictLabel(p.verdict, lang)} storm`;
                  if (!onMap) {
                    const x = Math.min(W - 18, Math.max(18, c[0]));
                    const y = Math.min(H - 18, Math.max(18, c[1]));
                    const angle = (Math.atan2(c[1] - y, c[0] - x) * 180) / Math.PI;
                    return (
                      <g key={st.id} className={cls(p, "lm-storm lm-storm-off")} {...handlers(p.id, label)}>
                        {forecast.length > 1 ? <path className="storm-forecast" d={path(forecast)} /> : null}
                        <g transform={`translate(${x} ${y}) rotate(${angle})`}>
                          <circle className="storm-edge" r={13} />
                          <path className="storm-arrow" d="M-5 -6 L6 0 L-5 6 Z" />
                        </g>
                        <text
                          className="storm-label"
                          x={x}
                          y={y + (y > H / 2 ? -20 : 28)}
                          textAnchor={x > W / 2 ? "end" : "start"}
                        >
                          {st.name} (off map)
                        </text>
                      </g>
                    );
                  }
                  return (
                    <g key={st.id} className={cls(p, "lm-storm")} {...handlers(p.id, label)}>
                      <path className="storm-track" d={path(st.points.map((q) => [q.lon, q.lat]))} />
                      {forecast.length > 1 ? <path className="storm-forecast" d={path(forecast)} /> : null}
                      <circle
                        className="storm-field"
                        cx={c[0]}
                        cy={c[1]}
                        r={Math.max(6, kmToPx(project, current.lat, current.lon, current.radius_km))}
                      />
                      <circle className="storm-eye" cx={c[0]} cy={c[1]} r={4} />
                      <text className="storm-label" x={c[0] + 8} y={c[1] - 8}>
                        {st.name}
                      </text>
                    </g>
                  );
                })
              : null}
            {layers.route
              ? (bundle.reference?.ferry_routes ?? []).map((r) => {
                  const p = byId.get(`route:${r.route_id}`);
                  if (!p) return null;
                  const d = path(r.line.map(([la, lo]) => [lo, la]));
                  return (
                    <g
                      key={r.route_id}
                      {...handlers(p.id, `${p.name}: ${verdictLabel(p.verdict, lang)}`)}
                      className={cls(p, "lm-route")}
                    >
                      <path className="lm-route-hit" d={d} />
                      <path className="lm-route-line" d={d} />
                    </g>
                  );
                })
              : null}
            {layers.port
              ? (bundle.reference?.ports ?? []).map((pt) => {
                  const p = byId.get(`port:${pt.port_id}`);
                  const c = project([pt.lon, pt.lat]);
                  if (!c) return null;
                  if (!p) return <circle key={pt.port_id} className="port" cx={c[0]} cy={c[1]} r={2.2} />;
                  return (
                    <g
                      key={pt.port_id}
                      className={cls(p, "lm-port")}
                      {...handlers(p.id, `${p.name} port: ${verdictLabel(p.verdict, lang)}`)}
                    >
                      <circle className="lm-port-hit" cx={c[0]} cy={c[1]} r={11} />
                      <circle className="lm-port-dot" cx={c[0]} cy={c[1]} r={5.5} />
                      <text
                        className="port-label"
                        x={LABEL_LEFT.has(pt.port_id) ? c[0] - 9 : c[0] + 9}
                        y={c[1] + 4}
                        textAnchor={LABEL_LEFT.has(pt.port_id) ? "end" : "start"}
                      >
                        {pt.name.replace(" City", "")}
                      </text>
                    </g>
                  );
                })
              : null}
          </svg>
          {hover && tip && active ? (
            <div className="lm-tip" style={{ left: tip.x, top: tip.y }} aria-hidden="true">
              <strong>{active.name}</strong>
              <Chip tone={active.tone}>{verdictLabel(active.verdict, lang)}</Chip>
            </div>
          ) : null}
          <fieldset className="lm-layers">
            <legend className="sr">Layers</legend>
            {(Object.keys(layers) as PlaceKind[]).map((k) => (
              <label key={k}>
                <input
                  type="checkbox"
                  checked={layers[k]}
                  onChange={(e) => setLayers((l) => ({ ...l, [k]: e.target.checked }))}
                />
                <Icon name={KIND_ICON[k]} size={14} />
                {KIND_LABEL[k][lang]}
              </label>
            ))}
          </fieldset>
          <div className="lm-legend" aria-hidden="true">
            <span>
              <i className="sw tone-alert" />
              {lang === "fil" ? "Kumilos" : "Act"}
            </span>
            <span>
              <i className="sw tone-watch" />
              {lang === "fil" ? "Bantayan" : "Watch"}
            </span>
            <span>
              <i className="sw tone-ok" />
              Normal
            </span>
            <span>
              <i className="sw tone-muted" />
              {lang === "fil" ? "Walang datos" : "No call"}
            </span>
          </div>
        </div>

        <aside className="lm-side">
          <section
            className={`lm-detail ${active ? `tone-${active.tone}` : ""}`}
            aria-live="polite"
            aria-labelledby="lm-detail-h"
          >
            {active ? (
              <>
                <p className="eyebrow">
                  <Icon name={KIND_ICON[active.kind]} size={14} />
                  {KIND_LABEL[active.kind][lang]}
                  {pinned === active.id ? (lang === "fil" ? " · naka-pin" : " · pinned") : ""}
                </p>
                <div className="lm-detail-head">
                  <h3 id="lm-detail-h">{active.name}</h3>
                  <Chip tone={active.tone}>{verdictLabel(active.verdict, lang)}</Chip>
                </div>
                <p className="lm-headline">{active.headline}</p>
                {active.lines.length > 0 ? (
                  <ul className="lm-lines">
                    {active.lines.map((l) => (
                      <li key={l}>{l}</li>
                    ))}
                  </ul>
                ) : null}
                <a
                  className="lm-more"
                  href={`#/${({ region: "today", port: "ports", route: "sea", storm: "storms" } as const)[active.kind]}`}
                >
                  {lang === "fil" ? "Buong detalye" : "Full details"} <Icon name="arrow" size={14} />
                </a>
              </>
            ) : (
              <>
                <h3 id="lm-detail-h">{lang === "fil" ? "Pumili ng lugar" : "Pick a place"}</h3>
                <p className="meta">
                  {lang === "fil"
                    ? "Itapat ang cursor o pindutin ang mapa. Pindutin ulit para i-pin."
                    : "Hover or tap the map. Click to pin a place; click again to release."}
                </p>
              </>
            )}
          </section>

          <section className="lm-list" aria-labelledby="lm-list-h">
            <h3 id="lm-list-h">
              {lang === "fil" ? "Mahalaga ngayon" : "Significant now"}{" "}
              <span className="lm-count">{significant.length}</span>
            </h3>
            {significant.length === 0 ? (
              <p className="meta">
                {lang === "fil" ? "Walang kakaiba sa ngayon." : "Nothing unusual right now."}
              </p>
            ) : (
              <ul>
                {significant.map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      className={`lm-item tone-${p.tone}${activeId === p.id ? " is-active" : ""}`}
                      onMouseEnter={() => setHover(p.id)}
                      onMouseLeave={() => setHover(null)}
                      onFocus={() => setHover(p.id)}
                      onBlur={() => setHover(null)}
                      onClick={() => setPinned((cur) => (cur === p.id ? null : p.id))}
                    >
                      <Icon name={KIND_ICON[p.kind]} size={16} />
                      <span className="lm-item-name">{p.name}</span>
                      <Chip tone={p.tone}>{verdictLabel(p.verdict, lang)}</Chip>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      </div>
    </>
  );
}
