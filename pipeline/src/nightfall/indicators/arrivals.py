"""Import arrivals by vessel class, from PortWatch's estimated import tonnage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from nightfall.core.context import Context

# Vessel class is a proxy for cargo: dry bulk carries grain/sugar/feed, tankers carry fuel/oil.
CLASS_COLUMN = {"dry_bulk": "import_dry_bulk_t", "tanker": "import_tanker_t"}


@dataclass(frozen=True)
class Arrivals:
    vessel_class: str
    data_through: date
    tonnes_28d: float
    norm_28d: float
    pct_vs_norm: float
    pct_vs_last_year: float | None
    days_of_history: int


def arrivals(ctx: Context, vessel_class: str, portids: list[str] | None = None) -> Arrivals | None:
    col = CLASS_COLUMN[vessel_class]
    where, params = ("", None)
    if portids:
        where, params = f"portid IN ({','.join('?' * len(portids))})", list(portids)
    rows = ctx.rows("port_daily", where, params, order="date")
    by_day: dict[date, float] = {}
    for r in rows:
        by_day[r["date"]] = by_day.get(r["date"], 0.0) + (r[col] or 0.0)
    days = sorted(by_day)
    if len(days) < 28 * 4:
        return None
    vals = [by_day[d] for d in days]
    cur = sum(vals[-28:])
    blocks = [
        sum(vals[len(vals) - 28 * (k + 1) : len(vals) - 28 * k]) for k in range(1, min(6, len(vals) // 28))
    ]
    norm = sum(blocks) / len(blocks)
    ly = None
    if len(vals) >= 364 + 28:
        prev = sum(vals[-28 - 364 : -364])
        ly = (cur / prev - 1.0) if prev > 0 else None
    return Arrivals(vessel_class, days[-1], cur, norm, (cur / norm - 1.0) if norm else 0.0, ly, len(days))
