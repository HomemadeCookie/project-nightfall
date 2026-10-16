"""Forecast wind and waves along a ferry corridor, from the latest forecast issue."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from nightfall.core.context import Context

PREFERRED = ("noaa_gfs", "open_meteo")  # commercial-safe first
MAX_ISSUE_AGE = timedelta(hours=18)  # GFS cycles are 6-hourly and arrive ~4.5 h late


@dataclass(frozen=True)
class RouteWeather:
    route_id: str
    issued_at: datetime
    horizon_h: int
    peak_wind_kmh: float
    peak_gust_kmh: float
    peak_wave_m: float
    hours_wind_over_39: int  # forecast steps at or above tropical-storm-force-equivalent sustained wind
    provider: str = "open_meteo"


def _issue(ctx: Context, provider: str) -> datetime | None:
    rows = ctx.rows("route_forecast", "provider = ?", [provider], order="issued_at DESC")
    return rows[0]["issued_at"] if rows else None


def pick_provider(ctx: Context) -> tuple[str, datetime] | None:
    """First provider with a fresh-enough forecast, in order of licence safety."""
    for provider in PREFERRED:
        issue = _issue(ctx, provider)
        if issue is not None and ctx.as_of - issue <= MAX_ISSUE_AGE:
            return provider, issue
    for provider in PREFERRED:  # nothing fresh: fall back to the newest of whatever exists
        issue = _issue(ctx, provider)
        if issue is not None:
            return provider, issue
    return None


def route_weather(ctx: Context, route_id: str, horizon_h: int) -> RouteWeather | None:
    picked = pick_provider(ctx)
    if picked is None:
        return None
    provider, issue = picked
    end = ctx.as_of + timedelta(hours=horizon_h)
    rows = ctx.rows(
        "route_forecast",
        "provider = ? AND route_id = ? AND issued_at = ? AND valid_time >= ? AND valid_time <= ?",
        [provider, route_id, issue, ctx.as_of, end],
    )
    if not rows:
        return None
    by_time: dict[datetime, float] = {}
    for r in rows:
        by_time[r["valid_time"]] = max(by_time.get(r["valid_time"], 0.0), r["wind_kmh"] or 0.0)
    return RouteWeather(
        route_id,
        issue,
        horizon_h,
        max((r["wind_kmh"] or 0.0) for r in rows),
        max((r["gust_kmh"] or 0.0) for r in rows),
        max((r["wave_m"] or 0.0) for r in rows),
        sum(1 for w in by_time.values() if w >= 39.0),
        provider,
    )
