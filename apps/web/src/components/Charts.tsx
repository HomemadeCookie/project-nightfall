import { useId, useState } from "react";

export interface Series {
  name: string;
  tone: "a" | "b";
  points: { x: string; y: number }[];
}

const W = 640;
const H = 240;
const PAD = { l: 52, r: 12, t: 12, b: 28 };

const day = (iso: string): number => Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);

export function niceRange(min: number, max: number): [number, number] {
  if (min === max) return [min - 1, max + 1];
  const pad = (max - min) * 0.1;
  return [min - pad, max + pad];
}

export function LineChart({
  series,
  format = (n: number) => n.toFixed(1),
  label,
}: {
  series: Series[];
  format?: (n: number) => string;
  label: string;
}) {
  const id = useId();
  const [hover, setHover] = useState<number | null>(null);
  // Real feeds can contain unparseable dates or missing values; drop those points instead of drawing NaN.
  series = series.map((s) => ({
    ...s,
    points: s.points.filter((p) => Number.isFinite(day(p.x)) && Number.isFinite(p.y)),
  }));
  const all = series.flatMap((s) => s.points);
  if (all.length < 2) return <p className="meta">Not enough data to chart yet.</p>;
  const xs = all.map((p) => day(p.x));
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [y0, y1] = niceRange(Math.min(...all.map((p) => p.y)), Math.max(...all.map((p) => p.y)));
  const sx = (t: number) => PAD.l + ((t - x0) / (x1 - x0 || 1)) * (W - PAD.l - PAD.r);
  const sy = (v: number) => H - PAD.b - ((v - y0) / (y1 - y0 || 1)) * (H - PAD.t - PAD.b);
  const longSpan = x1 - x0 > 200 * 864e5; // a year of weeks needs the year to be readable
  const ticks = [0, 1, 2, 3].map((i) => y0 + ((y1 - y0) * i) / 3);
  const first = series[0]?.points ?? [];
  const hv = hover !== null ? first[hover] : undefined;
  const summary = `${label}: ${series
    .map((s) => `${s.name} latest ${format(s.points[s.points.length - 1]?.y ?? 0)}`)
    .join(", ")}`;

  return (
    <figure className="chart">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-labelledby={id}
        onPointerLeave={() => setHover(null)}
        onPointerMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const t = x0 + ((((e.clientX - r.left) / r.width) * W - PAD.l) / (W - PAD.l - PAD.r)) * (x1 - x0);
          let best = 0;
          first.forEach((p, i) => {
            if (Math.abs(day(p.x) - t) < Math.abs(day(first[best]?.x ?? p.x) - t)) best = i;
          });
          setHover(best);
        }}
      >
        <title id={id}>{summary}</title>
        {ticks.map((v) => (
          <g key={v}>
            <line className="grid" x1={PAD.l} x2={W - PAD.r} y1={sy(v)} y2={sy(v)} />
            <text className="axis" x={PAD.l - 6} y={sy(v) + 4} textAnchor="end">
              {format(v)}
            </text>
          </g>
        ))}
        {[x0, (x0 + x1) / 2, x1].map((t, i) => (
          <text
            key={t}
            className="axis"
            x={sx(t)}
            y={H - 8}
            textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}
          >
            {new Date(t).toLocaleDateString(
              "en-US",
              longSpan
                ? { month: "short", year: "numeric", timeZone: "UTC" }
                : { month: "short", day: "numeric", timeZone: "UTC" },
            )}
          </text>
        ))}
        {series.map((s) => (
          <polyline
            key={s.name}
            className={`line line-${s.tone}`}
            fill="none"
            points={s.points.map((p) => `${sx(day(p.x)).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ")}
          />
        ))}
        {hv ? (
          <line className="cursor" x1={sx(day(hv.x))} x2={sx(day(hv.x))} y1={PAD.t} y2={H - PAD.b} />
        ) : null}
      </svg>
      <figcaption>
        {series.map((s) => (
          <span key={s.name} className="legend">
            <i className={`swatch swatch-${s.tone}`} /> {s.name}
          </span>
        ))}
        {hv ? (
          <span className="readout">
            {new Date(day(hv.x)).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
              timeZone: "UTC",
            })}
            : {series.map((s) => `${s.name} ${format(s.points[hover ?? 0]?.y ?? 0)}`).join(" · ")}
          </span>
        ) : null}
      </figcaption>
    </figure>
  );
}

export function Sparkline({ values, label }: { values: number[]; label: string }) {
  if (values.length < 2) return null;
  const [lo, hi] = [Math.min(...values), Math.max(...values)];
  const pts = values
    .map(
      (v, i) =>
        `${((i / (values.length - 1)) * 100).toFixed(1)},${(22 - ((v - lo) / (hi - lo || 1)) * 20).toFixed(1)}`,
    )
    .join(" ");
  return (
    <svg className="spark" viewBox="0 0 100 24" preserveAspectRatio="none" role="img" aria-label={label}>
      <polyline className="line line-a" fill="none" points={pts} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
