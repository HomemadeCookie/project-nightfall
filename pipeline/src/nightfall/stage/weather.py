from __future__ import annotations

import re
from datetime import UTC, datetime

from nightfall.core.lake import Lake
from nightfall.core.time import parse_iso
from nightfall.stage.common import make_table, num

_LABEL = re.compile(r"(?P<d>\d{1,2})/(?P<m>\d{1,2})\s+(?P<h>\d{1,2}):(?P<mi>\d{2})\s+UTC")


def point_time(label: str, polygondate: str) -> datetime | None:
    """GDACS labels forecast points 'DD/MM HH:MM UTC' (no year); take the year from the issue date."""
    m = _LABEL.search(label or "")
    if not m or not polygondate:
        return None
    issued = parse_iso(polygondate)
    month = int(m["m"])
    year = issued.year + (1 if (month < issued.month - 6) else -1 if (month > issued.month + 6) else 0)
    try:
        return datetime(year, month, int(m["d"]), int(m["h"]), int(m["mi"]), tzinfo=UTC)
    except ValueError:
        return None


def stage_gdacs(lake: Lake):
    points, lines = [], []
    for rec in lake.iter_raw("gdacs", "tc_current"):
        issued_at = rec["fetched_at"]
        for f in rec["payload"]:
            p, g = f["properties"], f["geometry"]
            sev = p.get("severitydata") or {}
            base = {
                "storm_id": str(p["eventid"]),
                "name": p["eventname"],
                "issued_at": issued_at,
                "alert": p.get("alertlevel"),
                "max_wind_kmh": num(sev.get("severity")),
                "agency": p.get("source"),
            }
            cls = p.get("Class") or ""
            if cls.startswith("Point_Polygon_Point"):
                t = point_time(p.get("polygonlabel") or "", p.get("polygondate") or "")
                if t is None:
                    continue
                lon, lat = g["coordinates"]
                points.append(
                    {
                        **base,
                        "point_time": t,
                        "lat": lat,
                        "lon": lon,
                        "radius_km": round(g.get("radius_deg", 0.0) * 111.0, 1),
                    }
                )
            elif cls.startswith("Line_Line"):
                (lon1, lat1), (lon2, lat2) = g["coordinates"][0], g["coordinates"][-1]
                lines.append(
                    {
                        **base,
                        "seq": int(cls.rsplit("_", 1)[1]),
                        "lat1": lat1,
                        "lon1": lon1,
                        "lat2": lat2,
                        "lon2": lon2,
                        "intensity_class": p.get("polygonlabel"),
                    }
                )
    pcols = {
        "storm_id": "str",
        "name": "str",
        "issued_at": "ts",
        "alert": "str",
        "max_wind_kmh": "f",
        "agency": "str",
        "point_time": "ts",
        "lat": "f",
        "lon": "f",
        "radius_km": "f",
    }
    lcols = {
        "storm_id": "str",
        "name": "str",
        "issued_at": "ts",
        "alert": "str",
        "max_wind_kmh": "f",
        "agency": "str",
        "seq": "i",
        "lat1": "f",
        "lon1": "f",
        "lat2": "f",
        "lon2": "f",
        "intensity_class": "str",
    }
    return {"storm_points": make_table(points, pcols), "storm_segments": make_table(lines, lcols)}


def stage_ibtracs(lake: Lake):
    rows = {}
    for rec in lake.iter_raw("ibtracs", "wp_tracks"):
        for r in rec["payload"]:
            t = datetime.fromisoformat(r["iso_time"]).replace(tzinfo=UTC)
            wind = num(r.get("usa_wind")) or num(r.get("wmo_wind"))
            rows[(r["sid"], t)] = {
                "sid": r["sid"],
                "season": int(r["season"]),
                "name": r["name"],
                "time": t,
                "lat": r["lat"],
                "lon": r["lon"],
                "wind_kt": wind,
                "r34_km": _r34(r),
            }
    cols = {
        "sid": "str",
        "season": "i",
        "name": "str",
        "time": "ts",
        "lat": "f",
        "lon": "f",
        "wind_kt": "f",
        "r34_km": "f",
    }
    return {"ibtracs_points": make_table(sorted(rows.values(), key=lambda x: (x["sid"], x["time"])), cols)}


def _r34(r: dict) -> float | None:
    quads = [num(r.get(k)) for k in ("usa_r34_ne", "usa_r34_se", "usa_r34_sw", "usa_r34_nw")]
    quads = [q for q in quads if q is not None and q >= 0]
    return round(max(quads) * 1.852, 1) if quads else None  # nautical miles -> km


def stage_route_forecast(lake: Lake):
    rows = []
    for provider in ("open_meteo", "noaa_gfs"):
        for rec in lake.iter_raw(provider, "route_forecast"):
            issued = rec["fetched_at"]
            for wp in rec["payload"]:
                w, m = wp["weather"], wp["marine"]
                wave = dict(zip(m["time"], m["wave_height"], strict=False))
                for i, t in enumerate(w["time"]):
                    rows.append(
                        {
                            "provider": provider,
                            "waypoint_id": wp["waypoint_id"],
                            "route_id": wp["waypoint_id"].split("#")[0],
                            "issued_at": issued,
                            "valid_time": datetime.fromisoformat(t).replace(tzinfo=UTC),
                            "wind_kmh": num(w["wind_speed_10m"][i]),
                            "gust_kmh": num(w["wind_gusts_10m"][i]),
                            "precip_mm": num(w["precipitation"][i]),
                            "wave_m": num(wave.get(t)),
                        }
                    )
    cols = {
        "provider": "str",
        "waypoint_id": "str",
        "route_id": "str",
        "issued_at": "ts",
        "valid_time": "ts",
        "wind_kmh": "f",
        "gust_kmh": "f",
        "precip_mm": "f",
        "wave_m": "f",
    }
    return {"route_forecast": make_table(rows, cols)}
