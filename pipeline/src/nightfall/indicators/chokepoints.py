"""Chokepoint transit pressure (vessel transits per day vs recent norm)."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date

from nightfall.core.context import Context


@dataclass(frozen=True)
class ChokepointPressure:
    chokepoint_id: str
    name: str
    data_through: date
    transits_7d: float
    baseline_mean: float
    pct_vs_baseline: float
    z: float


def pressure(ctx: Context, chokepoint_id: str, baseline_weeks: int = 12) -> ChokepointPressure | None:
    rows = ctx.rows("chokepoint_daily", "chokepoint_id = ?", [chokepoint_id], order="date")
    vals = [r["n_total"] or 0.0 for r in rows]
    n = len(vals) // 7
    if n < baseline_weeks // 2 + 1:
        return None
    start = len(vals) - 7 * n
    weeks = [sum(vals[start + 7 * i : start + 7 * i + 7]) for i in range(n)]
    base = weeks[-1 - baseline_weeks : -1]
    mean = statistics.fmean(base)
    std = max(statistics.pstdev(base), 0.05 * mean, 1.0)
    return ChokepointPressure(
        chokepoint_id,
        rows[-1]["name"],
        rows[-1]["date"],
        weeks[-1],
        mean,
        (weeks[-1] / mean - 1.0) if mean else 0.0,
        (weeks[-1] - mean) / std,
    )
