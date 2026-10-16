"""The manifest: what was published, from what, how fresh, and what is blocked."""

from __future__ import annotations

from datetime import UTC, date, datetime

import duckdb

from nightfall.core.lake import Lake

# source -> (staged table, column that says how far the data reaches, days after which it is stale)
FRESHNESS = {
    "eia": ("eia_spot", "date", 6),
    "frankfurter": ("fx_usd_php", "date", 6),
    "worldbank": ("pink_sheet", "period_start", 400),  # published with a long lag
    "da_prices": ("price_weekly", "week_end", 16),
    "portwatch": ("port_daily", "date", 14),
    "gdacs": ("storm_points", "issued_at", 3),
    "open_meteo": ("route_forecast", "issued_at", 3),
    "ibtracs": ("ibtracs_points", "time", 400),
    "news_rss": ("news_items", "first_seen", 3),
    "gdelt": ("gdelt_articles", "seen", 7),
    "adsb_lol": ("aircraft_obs", "observed_at", 3),
}


def _as_date(v) -> date | None:
    if v is None:
        return None
    return v.date() if isinstance(v, datetime) else v


def source_freshness(lake: Lake, now: datetime) -> list[dict]:
    con = lake.connect()
    fetch_log = lake.fetch_log()
    out = []
    for name, (table, col, stale_after) in FRESHNESS.items():
        info: dict = {
            "source": name,
            "data_through": None,
            "last_fetch": None,
            "status": "missing",
            "stale_after_days": stale_after,
        }
        try:
            row = con.execute(f'SELECT max("{col}") FROM "staging_{table}"').fetchone()
            info["data_through"] = None if row is None or row[0] is None else _as_date(row[0]).isoformat()
        except duckdb.CatalogException:
            pass
        info["last_fetch"] = fetch_log.get(name, {}).get("last_success")
        if info["data_through"]:
            age = (now.date() - date.fromisoformat(info["data_through"])).days
            info["age_days"] = age
            info["status"] = "ok" if age <= stale_after else "stale"
        out.append(info)
    return out


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
