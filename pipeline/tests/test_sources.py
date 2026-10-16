import io
import json
import re

import httpx
import openpyxl

from nightfall.core.http import Http
from nightfall.core.license import License
from nightfall.sources.registry import all_sources
from tests.helpers import NOW, fixture


def http_for(routes):
    """MockTransport that answers by URL substring, recording requests."""
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        for needle, resp in routes.items():
            if needle in str(req.url):
                return resp(req) if callable(resp) else resp
        return httpx.Response(404, text=f"unrouted {req.url}")

    return Http(transport=httpx.MockTransport(handler), sleep=lambda s: None), seen


def run(source_cls, routes, **kw):
    http, seen = http_for(routes)
    return list(source_cls(http, **kw).fetch(NOW)), seen


def test_every_source_declares_a_licence_and_cadence():
    for name, cls in all_sources().items():
        assert cls.name == name
        assert cls.license and all(isinstance(x, License) for x in cls.license), name
        assert cls.cadence in {"hourly", "daily", "weekly", "stream"}, name


def test_non_commercial_and_unclear_sources_are_flagged():
    srcs = all_sources()
    assert License.NON_COMMERCIAL in srcs["open_meteo"].license
    for name in ("portwatch", "gdacs", "da_prices", "news_rss"):
        assert License.UNCLEAR in srcs[name].license, name


def test_eia_requests_four_products_and_hides_the_api_key(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "SECRET123")
    envs, seen = run(
        all_sources()["eia"], {"api.eia.gov": httpx.Response(200, json=fixture("eia_spot.json"))}
    )
    assert len(envs) == 1 and envs[0].dataset == "spot_prices"
    url = str(seen[0].url)
    assert "SECRET123" in url  # sent to EIA...
    assert "SECRET123" not in json.dumps(envs[0].request)  # ...but never stored in the lake
    assert url.count("EPCBRENT") == 1 and "EPD2DXL0" in url and "EPMRU" in url


def test_frankfurter_requests_a_range():
    envs, seen = run(
        all_sources()["frankfurter"],
        {"frankfurter.dev": httpx.Response(200, json=fixture("frankfurter_range.json"))},
        lookback_days=100,
    )
    assert "2026-07-08.." in str(seen[0].url) and "symbols=PHP" in str(seen[0].url)
    assert envs[0].payload["rates"]


def test_portwatch_pages_within_windows_and_sorts_results():
    def daily(req):
        offset = int(req.url.params["resultOffset"])
        where = req.url.params["where"]
        lower = re.search(r"date >= timestamp '(\d{4}-\d{2}-\d{2})", where).group(1)
        if lower >= "2026-09-01":  # only the newest window has data
            if offset == 0:
                return httpx.Response(
                    200,
                    json={
                        "features": [
                            {"attributes": {"date": "2026-10-02", "portid": "port694", "portcalls": 2}}
                        ],
                        "exceededTransferLimit": True,
                    },
                )
            return httpx.Response(
                200,
                json={
                    "features": [{"attributes": {"date": "2026-10-01", "portid": "port694", "portcalls": 1}}]
                },
            )
        return httpx.Response(200, json={"features": []})

    ports = {
        "features": [{"attributes": {"portid": "port694", "portname": "Manila", "lat": 14.5, "lon": 120.9}}]
    }
    envs, seen = run(
        all_sources()["portwatch"],
        {
            "PortWatch_ports_database": httpx.Response(200, json=ports),
            "Daily_Ports_Data": daily,
            "Daily_Chokepoints_Data": httpx.Response(200, json={"features": []}),
        },
        lookback_days=150,
    )
    by = {e.dataset: e for e in envs}
    assert [r["portcalls"] for r in by["daily_ports"].payload] == [1, 2]  # sorted by date across pages
    daily_reqs = [r for r in seen if "Daily_Ports_Data" in str(r.url)]
    assert len(daily_reqs) >= 4  # 150 days / 60-day windows, plus a second page
    assert all("date <" in r.url.params["where"] and "date >=" in r.url.params["where"] for r in daily_reqs)
    assert "port694" in daily_reqs[0].url.params["where"]
    assert by["daily_chokepoints"].payload == []


def test_portwatch_surfaces_api_errors():
    import pytest

    http, _ = http_for({"PortWatch_ports_database": httpx.Response(200, json={"error": {"code": 400}})})
    with pytest.raises(RuntimeError, match="PortWatch"):
        list(all_sources()["portwatch"](http).fetch(NOW))


def test_gdacs_slims_features_and_computes_wind_radius():
    from nightfall.sources.weather.gdacs import slim_feature

    raw = fixture("gdacs_map_raw_small.json")["features"]
    slim = [slim_feature(f) for f in raw]
    classes = {f["properties"]["Class"] for f in slim}
    assert "Point_Polygon_Point_0" in classes and "icon" not in slim[0]["properties"]
    pt = next(f for f in slim if f["properties"]["Class"] == "Point_Polygon_Point_0")
    assert pt["geometry"]["type"] == "Point" and pt["geometry"]["radius_deg"] > 0
    assert next(f for f in slim if f["properties"]["Class"] == "Poly_Cones")["geometry"] is None


def test_gdacs_fetch_keeps_only_current_storms():
    raw = fixture("gdacs_map_raw_small.json")
    raw["features"].append(
        {
            "properties": {**raw["features"][0]["properties"], "iscurrent": "false", "eventname": "OLD"},
            "geometry": raw["features"][0]["geometry"],
        }
    )
    envs, _ = run(all_sources()["gdacs"], {"gdacs.org": httpx.Response(200, json=raw)})
    assert "OLD" not in {f["properties"]["eventname"] for f in envs[0].payload}
    assert envs[0].payload  # cones dropped, track kept


def test_ibtracs_parser_filters_area_and_years():
    from nightfall.sources.weather.ibtracs import parse_ibtracs

    header = "SID,SEASON,NUMBER,BASIN,SUBBASIN,NAME,ISO_TIME,NATURE,LAT,LON,WMO_WIND,USA_WIND,USA_R34_NE,USA_R34_SE,USA_R34_SW,USA_R34_NW"
    units = " ,Year, , , , , , ,degrees_north,degrees_east,kts,kts,nmile,nmile,nmile,nmile"
    rows = [
        "A,2013,1,WP,MM,HAIYAN,2013-11-07 00:00:00,TS,10.5,126.0,150,155,100,90,80,90",
        "B,2013,2,WP,MM,FAR,2013-11-07 00:00:00,TS,35.0,150.0,50,50,,,,",
        "C,1985,3,WP,MM,OLD,1985-08-01 00:00:00,TS,12.0,125.0,60,60,,,,",
    ]
    out = parse_ibtracs("\n".join([header, units, *rows]), from_year=1990)
    assert [r["name"] for r in out] == ["HAIYAN"] and out[0]["lat"] == 10.5


def test_open_meteo_batches_waypoints_and_pairs_marine_data():
    wp = fixture("open_meteo_waypoint.json")

    def weather(req):
        n = len(req.url.params["latitude"].split(","))
        return httpx.Response(200, json=[{"hourly": wp["weather"]}] * n)

    def marine(req):
        n = len(req.url.params["latitude"].split(","))
        return httpx.Response(200, json=[{"hourly": wp["marine"]}] * n)

    envs, _ = run(all_sources()["open_meteo"], {"marine-api": marine, "api.open-meteo.com": weather})
    recs = [r for e in envs for r in e.payload]
    assert len(recs) == 32 and recs[0]["waypoint_id"].startswith("batangas-calapan#")
    assert recs[0]["marine"]["wave_height"]


def test_adsb_one_request_per_airport_and_trims_fields():
    envs, seen = run(
        all_sources()["adsb_lol"], {"api.adsb.lol": httpx.Response(200, json=fixture("adsb_point.json"))}
    )
    assert [e.payload["airport"] for e in envs] == ["MNL", "CRK", "CEB", "DVO"]
    ac = envs[0].payload["aircraft"][0]
    assert set(ac) == {"hex", "flight", "r", "t", "alt_baro", "gs", "lat", "lon", "category"}
    assert envs[0].event_time == NOW


def test_rss_parsing_strips_html_and_parses_dates():
    from nightfall.sources.text.rss import parse_feed

    items = parse_feed(fixture("news.rss.xml"))
    assert items[0]["title"].startswith("Diesel prices")
    assert items[0]["teaser"] == "Oil firms announced a rollback."
    assert items[0]["published"] == "2026-10-15T22:30:00Z"


def test_gdelt_tolerates_throttling_notices():
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "articles": [
                        {
                            "url": "u",
                            "title": "t",
                            "seendate": "20261016T010000Z",
                            "domain": "d",
                            "language": "English",
                            "sourcecountry": "PH",
                        }
                    ]
                },
            )
        return httpx.Response(200, text="Please limit requests to one every 5 seconds")

    envs, _ = run(all_sources()["gdelt"], {"gdeltproject": handler})
    assert len(envs) == 1 and envs[0].payload["articles"][0]["url"] == "u"


def test_worldbank_parser_reads_the_pink_sheet_layout():
    from nightfall.sources.markets.worldbank import parse_pink_sheet

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Monthly Prices"
    ws.append(["World Bank Commodity Price Data"])
    ws.append([None, "Crude oil, Brent", "Rice, Thai 5% ", "Cocoa"])
    ws.append([None, "($/bbl)", "($/mt)", "($/kg)"])
    ws.append(["2025M11", 64.1, 368.0, 5.0])
    ws.append(["2025M12", "…", 424.0, 5.1])
    buf = io.BytesIO()
    wb.save(buf)
    rows = parse_pink_sheet(buf.getvalue())
    assert {"period": "2025-11", "series": "brent", "value": 64.1} in rows
    assert {"period": "2025-12", "series": "rice_thai_5", "value": 424.0} in rows
    assert not any(r["series"] == "brent" and r["period"] == "2025-12" for r in rows)  # missing "…" skipped
    assert not any(r["series"] == "cocoa" for r in rows)


def test_da_links_and_incremental_fetch(monkeypatch):
    from nightfall.sources.markets import da_prices

    html = (
        '<a href="https://www.da.gov.ph/wp-content/uploads/2026/10/Weekly-Average-Prices-October-5-11-2026.pdf">'
        '<a href="https://www.da.gov.ph/wp-content/uploads/2026/10/Revised-Weekly-Average-Price-September-28-October-4-2026.pdf">'
        '<a href="https://www.da.gov.ph/wp-content/uploads/2026/10/Price-Monitoring-October-9-2026.pdf">'
    )
    links = da_prices.weekly_links(html)
    assert len(links) == 2 and all("Weekly-Average" in u for u in links)  # daily PDFs are ignored
    known = {links[0]}
    http, seen = http_for(
        {
            "price-monitoring": httpx.Response(200, text=html),
            ".pdf": httpx.Response(200, content=b"%PDF-1.4 not really"),
        }
    )
    monkeypatch.setattr(da_prices, "pdf_text", lambda content: "extracted text")
    envs = list(all_sources()["da_prices"](http, known=known).fetch(NOW))
    assert [e.request["url"] for e in envs] == [links[1]] and envs[0].payload == {"text": "extracted text"}
    pdf_requests = [str(r.url) for r in seen if str(r.url).endswith(".pdf")]
    assert pdf_requests == [links[1]]
