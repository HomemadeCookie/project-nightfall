"""Loaders for the small, hand-curated tables in ``reference/``."""

from __future__ import annotations

import csv
import os
from functools import cache
from pathlib import Path

from nightfall.core.geo import sample_polyline


def reference_dir() -> Path:
    env = os.environ.get("NIGHTFALL_REFERENCE")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[4] / "reference"


@cache
def read_csv(name: str) -> tuple[dict[str, str], ...]:
    with open(reference_dir() / name, newline="", encoding="utf-8") as fh:
        return tuple(csv.DictReader(fh))


def ports() -> list[dict]:
    return [
        {**r, "lat": float(r["lat"]), "lon": float(r["lon"]), "key_port": r["key_port"] == "true"}
        for r in read_csv("ports.csv")
    ]


def regions() -> list[dict]:
    return [
        {
            **r,
            "lat": float(r["lat"]),
            "lon": float(r["lon"]),
            "ferry_route_ids": [x for x in r["ferry_route_ids"].split(";") if x],
        }
        for r in read_csv("regions.csv")
    ]


def commodities() -> list[dict]:
    return [
        {**r, "worldbank_series": [x for x in r["worldbank_series"].split(";") if x]}
        for r in read_csv("commodities.csv")
    ]


def ferry_routes() -> list[dict]:
    out = []
    for r in read_csv("ferry_routes.csv"):
        line = [(float(r["from_lat"]), float(r["from_lon"]))]
        for v in [x for x in r["via"].split(";") if x]:
            la, lo = v.split(":")
            line.append((float(la), float(lo)))
        line.append((float(r["to_lat"]), float(r["to_lon"])))
        out.append({**r, "line": line})
    return out


def ferry_waypoints(step_km: float = 25.0) -> list[dict]:
    """Points along every ferry corridor; forecasts are fetched at these."""
    pts: list[dict] = []
    for route in ferry_routes():
        for i, (lat, lon) in enumerate(sample_polyline(route["line"], step_km)):
            pts.append(
                {
                    "waypoint_id": f"{route['route_id']}#{i:02d}",
                    "route_id": route["route_id"],
                    "seq": i,
                    "lat": round(lat, 4),
                    "lon": round(lon, 4),
                }
            )
    return pts


def price_items() -> list[dict]:
    return [dict(r) for r in read_csv("price_items.csv")]
