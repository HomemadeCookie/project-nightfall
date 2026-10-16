"""Forecast wind and waves along a ferry corridor, from the latest forecast issue."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from nightfall.core.context import Context


@dataclass(frozen=True)
class RouteWeather:
    route_id: str
    issued_at: datetime
    horizon_h: int
    peak_wind_kmh: float
    peak_gust_kmh: float
    peak_wave_m: float
    hours_wind_over_39: int  # hours at or above tropical-storm-force-equivalent sustained wind


def route_weather(ctx: Context, route_id: str, horizon_h: int) -> RouteWeather | None:
    issue = ctx.latest_issue("route_forecast")
    if issue is None:
        return None
    end = ctx.as_of + timedelta(hours=horizon_h)
    rows = ctx.rows(
        "route_forecast",
        "route_id = ? AND issued_at = ? AND valid_time >= ? AND valid_time <= ?",
        [route_id, issue, ctx.as_of, end],
    )
    if not rows:
        return None
    hours_by_time: dict[datetime, float] = {}
    for r in rows:
        w = r["wind_kmh"] or 0.0
        hours_by_time[r["valid_time"]] = max(hours_by_time.get(r["valid_time"], 0.0), w)
    return RouteWeather(
        route_id,
        issue,
        horizon_h,
        max((r["wind_kmh"] or 0.0) for r in rows),
        max((r["gust_kmh"] or 0.0) for r in rows),
        max((r["wave_m"] or 0.0) for r in rows),
        sum(1 for w in hours_by_time.values() if w >= 39.0),
    )
