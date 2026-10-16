import { geoMercator } from "d3-geo";
import { useMemo } from "react";
import type { Reference, Storms } from "../data/types";
import type { Tone } from "../format";

export interface MapSite {
  id: string;
  label: string;
  lat: number;
  lon: number;
  tone: Tone;
}
export interface MapRoute {
  id: string;
  label: string;
  line: [number, number][]; // [lat, lon]
  tone: Tone;
}

const W = 420;
const H = 620;

// Philippines plus the seas around it. Fitting to a fixed box (not the polygons) matters: d3 reads GeoJSON
// rings as spherical, and geoBoundaries' winding order makes it fit the whole globe instead.
const PH_BOX: GeoJSON.MultiPoint = {
  type: "MultiPoint",
  coordinates: [
    [116.0, 4.2],
    [127.2, 4.2],
    [127.2, 21.6],
    [116.0, 21.6],
  ],
};

export function makeProjection() {
  return geoMercator().fitExtent(
    [
      [6, 6],
      [W - 6, H - 6],
    ],
    PH_BOX,
  );
}

/** Pixel radius of a circle of `km` kilometres at (lat, lon) under the projection. */
export function kmToPx(
  project: (p: [number, number]) => [number, number] | null,
  lat: number,
  lon: number,
  km: number,
) {
  const dLon = km / (111.32 * Math.cos((lat * Math.PI) / 180));
  const a = project([lon, lat]);
  const b = project([lon + dLon, lat]);
  return a && b ? Math.abs(b[0] - a[0]) : 0;
}

export function PhMap({
  geo,
  ports = [],
  routes = [],
  storms,
  sites = [],
  label,
}: {
  geo: GeoJSON.FeatureCollection | null;
  ports?: Reference["ports"];
  routes?: MapRoute[];
  storms?: Storms | null;
  sites?: MapSite[];
  label: string;
}) {
  const projection = useMemo(() => (geo ? makeProjection() : null), [geo]);
  if (!geo || !projection) return null;
  const project = (p: [number, number]) => projection(p) as [number, number] | null;
  const toPath = (coords: [number, number][]) =>
    coords
      .map(([lat, lon], i) => {
        const p = project([lon, lat]);
        return p ? `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}` : "";
      })
      .join(" ");
  const ringPath = (ring: number[][]) =>
    `${ring
      .map((c, i) => {
        const p = project([c[0] ?? 0, c[1] ?? 0]);
        return p ? `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}` : "";
      })
      .join(" ")}Z`;

  return (
    <svg className="map" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      <defs>
        <pattern id="sea-grid" width="24" height="24" patternUnits="userSpaceOnUse">
          <path d="M24 0H0V24" className="sea-line" fill="none" />
        </pattern>
      </defs>
      <rect className="sea" width={W} height={H} />
      <rect width={W} height={H} fill="url(#sea-grid)" />
      {geo.features.map((f) => {
        const g = f.geometry as GeoJSON.MultiPolygon;
        return (
          <path
            key={String(f.properties?.code)}
            className="region"
            d={g.coordinates.flatMap((poly) => poly.map(ringPath)).join(" ")}
          >
            <title>{String(f.properties?.name)}</title>
          </path>
        );
      })}
      {storms?.storms.map((s) => {
        const pts = s.points.filter((p) => p.lat > 0 && p.lon > 90);
        if (pts.length === 0) return null;
        return (
          <g key={s.id} className="storm">
            <path className="storm-track" d={toPath(pts.map((p) => [p.lat, p.lon]))} />
            {pts.slice(0, 1).map((p) => {
              const c = project([p.lon, p.lat]);
              return c ? (
                <circle
                  key="now"
                  className="storm-field"
                  cx={c[0]}
                  cy={c[1]}
                  r={Math.max(4, kmToPx(project, p.lat, p.lon, p.radius_km))}
                />
              ) : null;
            })}
            {(() => {
              const last = pts[pts.length - 1];
              const c = last ? project([last.lon, last.lat]) : null;
              return c ? (
                <text className="storm-label" x={c[0] + 6} y={c[1]}>
                  {s.name}
                </text>
              ) : null;
            })()}
          </g>
        );
      })}
      {routes.map((r) => (
        <path key={r.id} className={`route route-${r.tone}`} d={toPath(r.line)}>
          <title>{r.label}</title>
        </path>
      ))}
      {ports.map((p) => {
        const c = project([p.lon, p.lat]);
        return c ? (
          <g key={p.port_id}>
            <circle
              className={p.key_port ? "port port-key" : "port"}
              cx={c[0]}
              cy={c[1]}
              r={p.key_port ? 4 : 2.2}
            >
              <title>{p.name}</title>
            </circle>
            {p.key_port ? (
              <text className="port-label" x={c[0] + 7} y={c[1] + 3.5}>
                {p.name.replace(" City", "")}
              </text>
            ) : null}
          </g>
        ) : null;
      })}
      {sites.map((s) => {
        const c = project([s.lon, s.lat]);
        return c ? (
          <g key={s.id}>
            <rect
              className={`site site-${s.tone}`}
              x={c[0] - 4}
              y={c[1] - 4}
              width={8}
              height={8}
              transform={`rotate(45 ${c[0]} ${c[1]})`}
            >
              <title>{s.label}</title>
            </rect>
          </g>
        ) : null;
      })}
    </svg>
  );
}
