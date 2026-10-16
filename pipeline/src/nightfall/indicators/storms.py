"""Storm exposure: how close a forecast tropical cyclone comes to a site or a ferry corridor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from nightfall.core.context import Context
from nightfall.core.geo import Point, haversine_km

DEFAULT_RADIUS_KM = 150.0  # used when a track point carries no wind-field extent
STEP_H = 3


@dataclass(frozen=True)
class TrackPoint:
    time: datetime
    lat: float
    lon: float
    radius_km: float


@dataclass(frozen=True)
class StormTrack:
    storm_id: str
    name: str
    alert: str | None
    max_wind_kmh: float | None
    issued_at: datetime
    points: tuple[TrackPoint, ...]


@dataclass(frozen=True)
class Exposure:
    storm_id: str
    name: str
    min_distance_km: float
    hours_inside: int
    first_inside: datetime | None
    peak_wind_kmh: float | None
    alert: str | None


# Storms that can matter to the Philippines live in the western North Pacific / South China Sea.
BASIN_LAT, BASIN_LON = (-5.0, 45.0), (95.0, 185.0)


def in_basin(lat: float, lon: float) -> bool:
    return BASIN_LAT[0] <= lat <= BASIN_LAT[1] and BASIN_LON[0] <= lon <= BASIN_LON[1]


def current_tracks(ctx: Context) -> list[StormTrack]:
    """Latest track per storm known at as_of, western Pacific only, dropping storms that have ended."""
    rows = ctx.rows("storm_points", order="storm_id, issued_at DESC, point_time")
    by_storm: dict[str, list[dict]] = {}
    latest: dict[str, datetime] = {}
    for r in rows:
        latest.setdefault(r["storm_id"], r["issued_at"])
        if r["issued_at"] == latest[r["storm_id"]]:
            by_storm.setdefault(r["storm_id"], []).append(r)
    tracks = []
    for sid, pts in by_storm.items():
        pts.sort(key=lambda r: r["point_time"])
        if not any(in_basin(p["lat"], p["lon"]) for p in pts) or pts[-1]["point_time"] < ctx.as_of:
            continue
        tracks.append(
            StormTrack(
                sid,
                pts[0]["name"],
                pts[0]["alert"],
                pts[0]["max_wind_kmh"],
                pts[0]["issued_at"],
                tuple(
                    TrackPoint(p["point_time"], p["lat"], p["lon"], p["radius_km"] or DEFAULT_RADIUS_KM)
                    for p in pts
                ),
            )
        )
    return tracks


def position_at(track: StormTrack, t: datetime) -> TrackPoint | None:
    """Linear interpolation between timed track points; None outside the timed range."""
    pts = track.points
    if not pts or t < pts[0].time or t > pts[-1].time:
        return None
    for a, b in zip(pts, pts[1:], strict=False):
        if a.time <= t <= b.time:
            span = (b.time - a.time).total_seconds()
            f = 0.0 if span == 0 else (t - a.time).total_seconds() / span
            return TrackPoint(
                t,
                a.lat + (b.lat - a.lat) * f,
                a.lon + (b.lon - a.lon) * f,
                a.radius_km + (b.radius_km - a.radius_km) * f,
            )
    return pts[-1]


def exposure(track: StormTrack, targets: list[Point], as_of: datetime, horizon_h: int) -> Exposure:
    """Distance of the storm centre to the nearest target over the next ``horizon_h`` hours."""
    min_d, inside, first = float("inf"), 0, None
    t, end = as_of, as_of + timedelta(hours=horizon_h)
    while t <= end:
        pos = position_at(track, t)
        if pos is not None:
            d = min(haversine_km((pos.lat, pos.lon), tgt) for tgt in targets)
            min_d = min(min_d, d)
            if d <= pos.radius_km:
                inside += STEP_H
                first = first or t
        t += timedelta(hours=STEP_H)
    return Exposure(track.storm_id, track.name, min_d, inside, first, track.max_wind_kmh, track.alert)


def worst_exposure(ctx: Context, targets: list[Point], horizon_h: int) -> Exposure | None:
    """The most threatening current storm for these targets, or None if no storm is tracked."""
    results = [exposure(t, targets, ctx.as_of, horizon_h) for t in current_tracks(ctx)]
    results = [r for r in results if r.min_distance_km != float("inf")]
    if not results:
        return None
    return min(results, key=lambda r: (-r.hours_inside, r.min_distance_km))
