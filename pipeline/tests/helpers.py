"""Builders for synthetic-but-realistic lakes used across tests."""

from __future__ import annotations

import json
import math
import random
import zlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from nightfall.core.envelope import Envelope
from nightfall.core.lake import Lake
from nightfall.core.license import License

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


def fixture(name: str):
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else text


def put(
    lake: Lake,
    source: str,
    dataset: str,
    payload,
    *,
    at: datetime = NOW,
    request=None,
    event_time: datetime | None = None,
) -> None:
    lake.write_raw(
        [
            Envelope(
                source=source,
                dataset=dataset,
                license=[License.PUBLIC_DOMAIN],
                fetched_at=at,
                event_time=event_time,
                request=request or {},
                payload=payload,
            )
        ]
    )


def business_days(end: date, n: int) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def seed_fuel(lake: Lake, end: date = date(2026, 10, 15), days: int = 60, drift: float = 0.0) -> None:
    """EIA spot rows (diesel/gasoline $/gal, crude $/bbl) and USD/PHP, with optional daily drift."""
    rows = []
    for i, d in enumerate(business_days(end, days)):
        for product, base, unit in (
            ("EPD2DXL0", 2.50, "$/GAL"),
            ("EPMRU", 2.30, "$/GAL"),
            ("EPCBRENT", 80.0, "$/BBL"),
            ("EPCWTI", 76.0, "$/BBL"),
        ):
            rows.append(
                {
                    "period": d.isoformat(),
                    "product": product,
                    "value": str(round(base + drift * i, 4)),
                    "units": unit,
                }
            )
    put(lake, "eia", "spot_prices", rows)
    fx = {(end - timedelta(days=k)).isoformat(): {"PHP": 58.0} for k in range(days + 10)}
    put(lake, "frankfurter", "usd_php", {"base": "USD", "rates": fx})


def weekly_pattern(rng: random.Random, mean: float, d: date) -> float:
    dow = [1.1, 1.0, 1.0, 1.0, 1.05, 0.9, 0.95][d.weekday()]
    return max(0.0, round(mean * dow + rng.gauss(0, mean * 0.12)))


def seed_ports(
    lake: Lake, end: date = date(2026, 10, 9), days: int = 420, seed: int = 1, shock_last_week: float = 1.0
) -> None:
    rng = random.Random(seed)
    ports = [
        {"portid": "port694", "portname": "Manila", "lat": 14.59, "lon": 120.87, "vessel_count_total": 8000},
        {
            "portid": "port125",
            "portname": "Batangas City",
            "lat": 13.74,
            "lon": 121.02,
            "vessel_count_total": 2000,
        },
    ]
    daily = []
    for k in range(days):
        d = end - timedelta(days=days - 1 - k)
        for p, mean in (("port694", 15.0), ("port125", 6.0)):
            factor = shock_last_week if (end - d).days < 7 else 1.0
            calls = weekly_pattern(rng, mean * factor, d)
            daily.append(
                {
                    "date": d.isoformat(),
                    "portid": p,
                    "portcalls": calls,
                    "portcalls_container": round(calls * 0.5),
                    "portcalls_tanker": round(calls * 0.2),
                    "portcalls_dry_bulk": round(calls * 0.1),
                    "portcalls_general_cargo": 0,
                    "portcalls_roro": 0,
                    "import": calls * 3000,
                    "export": calls * 500,
                    "import_dry_bulk": calls * 1200 * (1.4 if (end - d).days < 28 else 1.0),
                    "import_tanker": calls * 900,
                    "import_container": 0,
                    "import_general_cargo": 0,
                    "import_roro": 0,
                    "export_dry_bulk": 0,
                    "export_tanker": 0,
                    "export_container": 0,
                    "export_general_cargo": 0,
                    "export_roro": 0,
                }
            )
    put(lake, "portwatch", "ports", ports)
    put(lake, "portwatch", "daily_ports", daily)
    choke = []
    for k in range(days):
        d = end - timedelta(days=days - 1 - k)
        choke.append(
            {
                "date": d.isoformat(),
                "portid": "chokepoint5",
                "portname": "Malacca Strait",
                "n_total": round(200 + rng.gauss(0, 10)),
                "n_container": 80,
                "n_dry_bulk": 60,
                "n_tanker": 40,
                "n_roro": 5,
                "capacity": 1_000_000,
            }
        )
    put(lake, "portwatch", "daily_chokepoints", choke)


def da_text(period: str, prices: dict[str, float]) -> str:
    lines = [
        "Department of Agriculture",
        "Bantay Presyo Monitoring",
        f"For the period of {period}",
        "COMMODITY SPECIFICATION UNIT WEEKLY AVERAGE PRICE",
        "LOCAL COMMERCIAL RICE",
    ]
    lines.append(f"Regular Milled 20-40% bran streak kg {prices['rice']:.2f}")
    lines.append(f"Well Milled 1-19% bran streak kg {prices['rice'] + 4:.2f}")
    lines += [
        "OTHER BASIC COMMODITIES",
        f"Sugar (Refined) kg {prices['sugar']:.2f}",
        f"Cooking Oil (Palm) 1 Liter/bottle L {prices['oil']:.2f}",
    ]
    return "\n".join(lines)


def seed_da_weekly(
    lake: Lake,
    weeks: int = 120,
    start: date = date(2024, 7, 1),
    trend: float = 0.002,
    seed: int = 3,
    rice_shock_from: int | None = None,
) -> date:
    """Weekly NCR price PDFs as extracted text. Week ``w`` depends only on ``w``, so a lake with
    fewer weeks is an exact prefix of one with more (needed by the leakage test). Returns the
    last week's end date."""
    rng = random.Random(seed)
    fri = start
    for w in range(weeks):
        mon = start + timedelta(days=7 * w)
        fri = mon + timedelta(days=4)
        base = 1.0 + trend * w
        shock = 1.0 + (
            0.08 * (w - rice_shock_from) / 10 if rice_shock_from is not None and w > rice_shock_from else 0
        )
        prices = {
            "rice": 45 * base * shock * (1 + rng.gauss(0, 0.01)),
            "sugar": 80 * base * (1 + rng.gauss(0, 0.01)),
            "oil": 100 * (1 + 0.05 * math.sin(w / 8)) * (1 + rng.gauss(0, 0.01)),
        }
        period = (
            f"{mon:%B} {mon.day}-{fri.day}, {fri.year}"
            if mon.month == fri.month
            else f"{mon:%B} {mon.day}-{fri:%B} {fri.day}, {fri.year}"
        )
        put(
            lake,
            "da_prices",
            "weekly_ncr",
            {"text": da_text(period, prices)},
            at=datetime.combine(fri + timedelta(days=3), datetime.min.time(), tzinfo=UTC),
            request={"url": f"https://example.test/Weekly-Average-Prices-{mon.isoformat()}.pdf"},
        )
    return fri


def seed_pink(lake: Lake, months: int = 60) -> None:
    rows = []
    y, m = 2026, 9
    for i in range(months):
        rows.append({"period": f"{y:04d}-{m:02d}", "series": "rice_thai_5", "value": 500 - i})
        rows.append({"period": f"{y:04d}-{m:02d}", "series": "sugar_world", "value": 400 - i})
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    put(lake, "worldbank", "pink_sheet_monthly", rows)


def seed_storm(
    lake: Lake,
    *,
    at: datetime = NOW,
    lat: float = 13.0,
    lon: float = 123.0,
    radius_deg: float = 2.0,
    hours: int = 72,
    name: str = "TESTSTORM",
    eventid: int | None = None,
) -> None:
    """A storm moving west at 10 km/h-ish near the Philippines, timed every 12 h."""
    feats = []
    for k in range(0, hours + 1, 12):
        t = at + timedelta(hours=k)
        feats.append(
            {
                "properties": {
                    "eventid": eventid if eventid is not None else zlib.crc32(name.encode()) % 10_000,
                    "eventname": name,
                    "alertlevel": "Orange",
                    "episodeid": 1,
                    "fromdate": None,
                    "todate": None,
                    "datemodified": None,
                    "polygondate": at.strftime("%Y-%m-%dT%H:%M:%S"),
                    "polygonlabel": t.strftime("%d/%m %H:%M UTC"),
                    "Class": f"Point_Polygon_Point_{k // 12}",
                    "severitydata": {"severity": 120.0},
                    "source": "JTWC",
                    "iscurrent": "true",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon - 0.3 * (k // 12), lat],
                    "radius_deg": radius_deg,
                },
            }
        )
    put(lake, "gdacs", "tc_current", feats, at=at)


def seed_route_forecast(
    lake: Lake,
    *,
    source: str = "open_meteo",
    at: datetime = NOW,
    wave: float = 0.5,
    wind: float = 15.0,
    gust: float = 30.0,
    route_ids: list[str] | None = None,
) -> None:
    from nightfall.core.reference import ferry_waypoints

    wps = [w for w in ferry_waypoints() if route_ids is None or w["route_id"] in route_ids]
    times = [(at + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(0, 121)]
    recs = []
    for w in wps:
        recs.append(
            {
                "waypoint_id": w["waypoint_id"],
                "lat": w["lat"],
                "lon": w["lon"],
                "weather": {
                    "time": times,
                    "wind_speed_10m": [wind] * len(times),
                    "wind_gusts_10m": [gust] * len(times),
                    "precipitation": [0.0] * len(times),
                },
                "marine": {"time": times, "wave_height": [wave] * len(times)},
            }
        )
    put(lake, source, "route_forecast", recs, at=at)


def full_lake(root: Path) -> Lake:
    from nightfall.stage import stage_all

    lake = Lake(root)
    seed_fuel(lake)
    seed_ports(lake)
    seed_da_weekly(lake)
    seed_pink(lake)
    seed_storm(lake, lat=11.0, lon=125.0)
    seed_route_forecast(lake)
    for source in ("eia", "frankfurter", "portwatch", "da_prices", "worldbank", "gdacs", "open_meteo"):
        lake.record_fetch(source, NOW)
    stage_all(lake)
    return lake
