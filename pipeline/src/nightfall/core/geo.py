"""Spatial helpers. Joins use H3 cells and named geofences, never raw coordinates."""

from __future__ import annotations

import math
from collections.abc import Sequence

import h3

EARTH_KM = 6371.0088
Point = tuple[float, float]  # (lat, lon)


def haversine_km(a: Point, b: Point) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(h))


def cell(lat: float, lon: float, res: int = 7) -> str:
    return h3.latlng_to_cell(lat, lon, res)


def point_in_polygon(pt: Point, ring: Sequence[Point]) -> bool:
    """Ray casting on (lat, lon) pairs. Fine for small geofences, not for the antimeridian."""
    lat, lon = pt
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        lat_i, lon_i = ring[i]
        lat_j, lon_j = ring[j]
        if (lat_i > lat) != (lat_j > lat):
            cross = (lon_j - lon_i) * (lat - lat_i) / (lat_j - lat_i) + lon_i
            if lon < cross:
                inside = not inside
        j = i
    return inside


def _local_xy(origin: Point, p: Point) -> tuple[float, float]:
    """Equirectangular km offsets around ``origin``; accurate enough within ~500 km."""
    x = math.radians(p[1] - origin[1]) * EARTH_KM * math.cos(math.radians(origin[0]))
    y = math.radians(p[0] - origin[0]) * EARTH_KM
    return x, y


def distance_to_segment_km(p: Point, a: Point, b: Point) -> float:
    ax, ay = _local_xy(p, a)
    bx, by = _local_xy(p, b)
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    t = 0.0 if seg2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg2))
    return math.hypot(ax + t * dx, ay + t * dy)


def distance_to_polyline_km(p: Point, line: Sequence[Point]) -> float:
    if len(line) == 1:
        return haversine_km(p, line[0])
    return min(distance_to_segment_km(p, line[i], line[i + 1]) for i in range(len(line) - 1))


def sample_polyline(line: Sequence[Point], step_km: float = 25.0) -> list[Point]:
    """Points along a polyline at roughly ``step_km`` spacing, endpoints included."""
    out: list[Point] = [line[0]]
    for a, b in zip(line, line[1:], strict=False):
        d = haversine_km(a, b)
        n = max(1, math.ceil(d / step_km))
        for k in range(1, n + 1):
            f = k / n
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return out
