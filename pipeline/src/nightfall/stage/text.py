from __future__ import annotations

from datetime import UTC, datetime

from nightfall.core.lake import Lake
from nightfall.core.time import parse_iso
from nightfall.stage.common import make_table


def stage_news(lake: Lake):
    items = {}
    for rec in lake.iter_raw("news_rss", "items"):
        feed = rec["payload"]["feed"]
        for it in rec["payload"]["items"]:
            if not it["url"]:
                continue
            first = items.get(it["url"])
            items[it["url"]] = {
                "url": it["url"],
                "feed": feed,
                "title": it["title"],
                "teaser": it["teaser"],
                "published": parse_iso(it["published"]) if it["published"] else None,
                "first_seen": first["first_seen"] if first else rec["fetched_at"],
            }
    cols = {
        "url": "str",
        "feed": "str",
        "title": "str",
        "teaser": "str",
        "published": "ts",
        "first_seen": "ts",
    }
    rows = sorted(items.values(), key=lambda x: x["first_seen"])
    news = make_table(rows, cols)

    g = {}
    for rec in lake.iter_raw("gdelt", "articles"):
        topic = rec["payload"]["topic"]
        for a in rec["payload"]["articles"]:
            try:
                seen = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            except (TypeError, ValueError):
                seen = rec["fetched_at"]
            g[(topic, a["url"])] = {
                "topic": topic,
                "url": a["url"],
                "title": a["title"],
                "seen": seen,
                "domain": a["domain"],
                "language": a["language"],
                "country": a["sourcecountry"],
            }
    gcols = {
        "topic": "str",
        "url": "str",
        "title": "str",
        "seen": "ts",
        "domain": "str",
        "language": "str",
        "country": "str",
    }
    return {"news_items": news, "gdelt_articles": make_table(list(g.values()), gcols)}


def stage_aircraft(lake: Lake):
    rows = []
    for rec in lake.iter_raw("adsb_lol", "aircraft_snapshot"):
        observed = rec["event_time"] or rec["fetched_at"]
        for a in rec["payload"]["aircraft"]:
            alt = a.get("alt_baro")
            rows.append(
                {
                    "airport": rec["payload"]["airport"],
                    "observed_at": observed,
                    "hex": a.get("hex"),
                    "callsign": (a.get("flight") or "").strip() or None,
                    "registration": a.get("r"),
                    "type": a.get("t"),
                    "on_ground": alt == "ground",
                    "alt_ft": alt if isinstance(alt, int | float) else None,
                    "gs_kt": a.get("gs"),
                    "lat": a.get("lat"),
                    "lon": a.get("lon"),
                }
            )
    cols = {
        "airport": "str",
        "observed_at": "ts",
        "hex": "str",
        "callsign": "str",
        "registration": "str",
        "type": "str",
        "on_ground": "b",
        "alt_ft": "f",
        "gs_kt": "f",
        "lat": "f",
        "lon": "f",
    }
    return {"aircraft_obs": make_table(rows, cols)}


def stage_ais(lake: Lake):
    pos, static = {}, {}
    for rec in lake.iter_raw("aisstream", "positions"):
        for r in rec["payload"]:
            if r["lat"] is None or r["lon"] is None or not r["t"]:
                continue
            t = parse_iso(r["t"])
            pos[(r["mmsi"], t)] = {
                "mmsi": r["mmsi"],
                "observed_at": t,
                "lat": r["lat"],
                "lon": r["lon"],
                "sog_kt": r["sog"],
                "nav_status": r["nav"],
            }
    for rec in lake.iter_raw("aisstream", "static"):
        for r in rec["payload"]:
            static[r["mmsi"]] = {
                "mmsi": r["mmsi"],
                "name": r["name"],
                "ship_type": r["type"],
                "destination": r["destination"],
                "draught_m": r["draught"],
                "length_m": r["length"],
                "observed_at": parse_iso(r["t"]) if r["t"] else rec["fetched_at"],
            }
    pcols = {"mmsi": "str", "observed_at": "ts", "lat": "f", "lon": "f", "sog_kt": "f", "nav_status": "i"}
    scols = {
        "mmsi": "str",
        "name": "str",
        "ship_type": "i",
        "destination": "str",
        "draught_m": "f",
        "length_m": "f",
        "observed_at": "ts",
    }
    return {
        "ais_positions": make_table(sorted(pos.values(), key=lambda x: (x["mmsi"], x["observed_at"])), pcols),
        "ais_static": make_table(list(static.values()), scols),
    }
