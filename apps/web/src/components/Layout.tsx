import type { ReactNode } from "react";
import type { Tone } from "../format";
import { Icon } from "./Icons";

export function PageHeader({
  eyebrow,
  title,
  lede,
  icon,
}: { eyebrow?: string; title: string; lede?: ReactNode; icon?: string }) {
  return (
    <header className="page-head">
      {eyebrow ? (
        <p className="eyebrow">
          {icon ? <Icon name={icon} size={16} /> : null}
          {eyebrow}
        </p>
      ) : null}
      <h2>{title}</h2>
      {lede ? <p className="lede">{lede}</p> : null}
    </header>
  );
}

/** A glanceable number with a label, tinted by tone, optionally linking to the page that explains it. */
export function StatTile({
  label,
  value,
  sub,
  tone,
  icon,
  href,
  trend,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone: Tone;
  icon: string;
  href?: string;
  trend?: "up" | "down" | "flat";
}) {
  const body = (
    <>
      <span className="stat-top">
        <span className="stat-icon">
          <Icon name={icon} size={18} />
        </span>
        <span className="stat-label">{label}</span>
        {href ? <Icon name="arrow" size={16} className="stat-go" /> : null}
      </span>
      <span className="stat-value">
        {trend ? <Icon name={trend} size={22} className={`trend trend-${trend}`} /> : null}
        {value}
      </span>
      {sub ? <span className="stat-sub">{sub}</span> : null}
    </>
  );
  return href ? (
    <a className={`stat stat-${tone}`} href={href}>
      {body}
    </a>
  ) : (
    <div className={`stat stat-${tone}`}>{body}</div>
  );
}
