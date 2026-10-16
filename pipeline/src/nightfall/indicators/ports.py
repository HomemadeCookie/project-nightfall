"""Port activity pressure from IMF PortWatch daily port calls."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from nightfall.core.context import Context


def calls_series(ctx: Context, portid: str, column: str = "calls") -> list[tuple[date, float]]:
    rows = ctx.rows("port_daily", "portid = ?", [portid], order="date")
    return [(r["date"], r[column] or 0.0) for r in rows]


def weekly_sums(values: list[float], ending_at_last: bool = True) -> list[float]:
    """Non-overlapping 7-day sums, aligned so the final block ends on the last observation."""
    n = len(values) // 7
    start = len(values) - 7 * n if ending_at_last else 0
    return [sum(values[start + 7 * i : start + 7 * (i + 1)]) for i in range(n)]


@dataclass(frozen=True)
class PortPressure:
    portid: str
    data_through: date
    calls_7d: float
    baseline_mean: float
    baseline_std: float
    z: float
    yoy_ratio: float | None
    weeks_of_history: int


def pressure(ctx: Context, portid: str, baseline_weeks: int = 12) -> PortPressure | None:
    series = calls_series(ctx, portid)
    if len(series) < 7 * (baseline_weeks // 2 + 1):
        return None
    vals = [v for _, v in series]
    weeks = weekly_sums(vals)
    last, base = weeks[-1], weeks[-1 - baseline_weeks : -1]
    mean = statistics.fmean(base)
    std = max(statistics.pstdev(base), 0.15 * mean, 1.0)
    yoy = None
    if len(vals) >= 365 + 28:
        a, b = sum(vals[-28:]), sum(vals[-28 - 364 : -364])
        yoy = a / b if b > 0 else None
    return PortPressure(portid, series[-1][0], last, mean, std, (last - mean) / std, yoy, len(weeks))


def forecast_next_week(vals: list[float], model: str) -> float:
    """Total calls over the next 7 days. ``naive`` repeats last week; ``blend4`` averages 4."""
    weeks = weekly_sums(vals)
    if model == "naive":
        return weeks[-1]
    if model == "blend4":
        return statistics.fmean(weeks[-4:])
    raise ValueError(model)


def history_start(series: list[tuple[date, float]]) -> date | None:
    return series[0][0] if series else None


def expected_date(d: date, days: int) -> date:
    return d + timedelta(days=days)
