"""Anchorage wait times at a port, from AIS-derived port calls."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import timedelta

from nightfall.core.context import Context
from nightfall.detect.ais import Fix, detect_port_calls

MIN_WAITS = 3  # fewer than this and a median means nothing


@dataclass(frozen=True)
class WaitSummary:
    port_id: str
    window_days: int
    vessels_seen: int
    calls: int
    waits_measured: int
    median_wait_h: float | None
    p90_wait_h: float | None


def port_waits(ctx: Context, port_id: str, center: tuple[float, float], days: int = 7) -> WaitSummary | None:
    since = ctx.as_of - timedelta(days=days)
    rows = ctx.rows("ais_positions", "observed_at >= ?", [since], order="mmsi, observed_at")
    if not rows:
        return None
    fixes = [
        Fix(r["mmsi"], r["observed_at"], r["lat"], r["lon"], r["sog_kt"] if r["sog_kt"] is not None else 99.0)
        for r in rows
    ]
    calls = detect_port_calls(fixes, port_id, center)
    waits = sorted(w for c in calls if (w := c.wait_hours) is not None)
    enough = len(waits) >= MIN_WAITS
    p90 = waits[min(len(waits) - 1, int(round(0.9 * (len(waits) - 1))))] if enough else None
    return WaitSummary(
        port_id,
        days,
        len({f.mmsi for f in fixes}),
        len(calls),
        len(waits),
        round(statistics.median(waits), 1) if enough else None,
        p90,
    )
