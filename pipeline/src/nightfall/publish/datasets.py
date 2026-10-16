"""Small JSON datasets the web app charts and maps. Built from the same as-of Context as answers."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from nightfall.core import reference
from nightfall.core.context import Context
from nightfall.indicators.fuel import weekly_costs
from nightfall.indicators.prices import weekly_prices
from nightfall.indicators.storms import current_tracks
from nightfall.sources.ships.portwatch import CHOKEPOINTS


def fuel_weekly(ctx: Context) -> dict:
    return {
        p: [
            {"week_start": w.week_start.isoformat(), "php_per_l": round(w.php_per_l, 2), "n_days": w.n_days}
            for w in weekly_costs(ctx, p)[-52:]
        ]
        for p in ("diesel", "gasoline")
    }


def ports_daily(ctx: Context, days: int = 180) -> dict:
    out = {}
    for p in reference.ports():
        if not p["key_port"]:
            continue
        rows = ctx.rows("port_daily", "portid = ?", [p["portwatch_id"]], order="date")[-days:]
        out[p["port_id"]] = {
            "name": p["name"],
            "lat": p["lat"],
            "lon": p["lon"],
            "series": [{"date": r["date"].isoformat(), "calls": r["calls"]} for r in rows],
        }
    return out


def chokepoints(ctx: Context, weeks: int = 40) -> dict:
    out = {}
    for cid, name in CHOKEPOINTS.items():
        rows = ctx.rows("chokepoint_daily", "chokepoint_id = ?", [cid], order="date")
        if not rows:
            continue
        by_week: dict = defaultdict(float)
        for r in rows:
            by_week[r["date"] - timedelta(days=r["date"].weekday())] += r["n_total"] or 0.0
        series = [{"week_start": d.isoformat(), "transits": v} for d, v in sorted(by_week.items())][-weeks:-1]
        out[cid] = {"name": name, "series": series}
    return out


def prices(ctx: Context, weeks: int = 104) -> dict:
    out = {}
    for item in reference.price_items():
        series = weekly_prices(ctx, item["item_id"])[-weeks:]
        if series:
            out[item["item_id"]] = {
                "label_en": item["label_en"],
                "label_fil": item["label_fil"],
                "unit": item["unit_hint"],
                "series": [{"week_end": w.week_end.isoformat(), "price": w.price} for w in series],
            }
    return out


def storms(ctx: Context) -> dict:
    tracks = current_tracks(ctx)
    return {
        "storms": [
            {
                "id": t.storm_id,
                "name": t.name,
                "alert": t.alert,
                "max_wind_kmh": t.max_wind_kmh,
                "issued_at": t.issued_at.isoformat(),
                "points": [
                    {"time": p.time.isoformat(), "lat": p.lat, "lon": p.lon, "radius_km": round(p.radius_km)}
                    for p in t.points
                ],
            }
            for t in tracks
        ],
        "segments": [
            {
                "storm_id": r["storm_id"],
                "seq": r["seq"],
                "coords": [[r["lon1"], r["lat1"]], [r["lon2"], r["lat2"]]],
                "intensity": r["intensity_class"],
            }
            for r in ctx.rows(
                "storm_segments", "issued_at = (SELECT max(issued_at) FROM staging_storm_segments)"
            )
        ],
    }


def reference_data() -> dict:
    return {
        "ports": [
            {k: p[k] for k in ("port_id", "name", "lat", "lon", "key_port", "region_code")}
            for p in reference.ports()
        ],
        "ferry_routes": [
            {
                "route_id": r["route_id"],
                "name": r["name"],
                "line": [[lat, lon] for lat, lon in r["line"]],
                "serves": r["serves_regions"].split(";"),
            }
            for r in reference.ferry_routes()
        ],
        "regions": [
            {k: r[k] for k in ("region_code", "name", "short", "lat", "lon")} for r in reference.regions()
        ],
    }


def build_all(ctx: Context) -> dict[str, dict]:
    return {
        "fuel_weekly": fuel_weekly(ctx),
        "ports_daily": ports_daily(ctx),
        "chokepoints": chokepoints(ctx),
        "prices": prices(ctx),
        "storms": storms(ctx),
        "reference": reference_data(),
    }
