from datetime import UTC, date, datetime, timedelta

from nightfall.core.lake import Lake
from nightfall.stage import stage_all
from nightfall.stage.markets import parse_period, parse_weekly_text
from nightfall.stage.weather import point_time
from tests.helpers import NOW, fixture, put, seed_fuel, seed_ports


def staged(lake_dir):
    lake = Lake(lake_dir)
    return lake, lake.connect()


def test_eia_staging_dedups_and_sets_availability(lake_dir):
    lake = Lake(lake_dir)
    rows = fixture("eia_spot.json")["response"]["data"]
    put(lake, "eia", "spot_prices", rows, at=NOW)
    revised = [dict(r, value="999") for r in rows[:1]]
    put(lake, "eia", "spot_prices", revised, at=NOW + timedelta(hours=1))  # later fetch wins
    stage_all(lake)
    con = lake.connect()
    n_keys = len({(r["period"], r["product"]) for r in rows})
    assert con.execute("SELECT count(*) FROM staging_eia_spot").fetchone()[0] == n_keys
    first = rows[0]
    got = con.execute(
        "SELECT value, available_on - date FROM staging_eia_spot WHERE product=? AND date=?",
        [first["product"], date.fromisoformat(first["period"])],
    ).fetchone()
    assert got[0] == 999.0 and got[1] == 1  # one-day publication lag


def test_period_parsing_handles_month_and_year_boundaries():
    assert parse_period("For the period of October 5-11, 2026") == (date(2026, 10, 5), date(2026, 10, 11))
    assert parse_period("For the period of September 28-October 4, 2026") == (
        date(2026, 9, 28),
        date(2026, 10, 4),
    )
    assert parse_period("For the period of December 29-January 2, 2026") == (
        date(2025, 12, 29),
        date(2026, 1, 2),
    )
    assert parse_period("no period here") is None


def test_real_da_weekly_text_parses_into_priced_rows():
    period, rows = parse_weekly_text(fixture("da_weekly_oct_5_11_2026.txt"))
    assert period == (date(2026, 10, 5), date(2026, 10, 11))
    by = {(r["category"], r["item"]): r for r in rows}
    well = by[("LOCAL COMMERCIAL RICE", "Well Milled 1-19% bran streak")]
    assert well["price"] == 48.42 and well["unit"] == "kg"
    assert by[("OTHER BASIC COMMODITIES", "Sugar (Refined)")]["price"] == 81.24
    assert by[("OTHER BASIC COMMODITIES", "Cooking Oil (Palm) 1 Liter/bottle")]["unit"] == "L"
    assert by[("LOCAL COMMERCIAL RICE", "Basmati")]["price"] is None  # "-" means not sold
    assert len(rows) > 90  # the whole table, not just the first page


def test_da_staging_maps_items_and_prefers_revised(lake_dir):
    lake = Lake(lake_dir)
    text = fixture("da_weekly_oct_5_11_2026.txt")
    put(
        lake,
        "da_prices",
        "weekly_ncr",
        {"text": text},
        at=NOW,
        request={"url": "https://x/Weekly-Average-Prices-1.pdf"},
    )
    revised = text.replace("Sugar (Refined) kg 81.24", "Sugar (Refined) kg 80.00")
    put(
        lake,
        "da_prices",
        "weekly_ncr",
        {"text": revised},
        at=NOW - timedelta(days=1),
        request={"url": "https://x/Revised-Weekly-Average-Price-1.pdf"},
    )
    stage_all(lake)
    con = lake.connect()
    sugar = con.execute("SELECT price FROM staging_price_weekly WHERE item_id='sugar_refined'").fetchall()
    assert sugar == [(80.0,)]  # the Revised edition wins even though it was fetched earlier
    ids = {r[0] for r in con.execute("SELECT DISTINCT item_id FROM staging_price_weekly").fetchall()}
    assert {
        "rice_regular",
        "rice_wellmilled",
        "sugar_refined",
        "cooking_oil_palm_1l",
        "egg_white_medium",
    } <= ids
    assert (
        "rice_imported_wellmilled" in ids
        and con.execute("SELECT price FROM staging_price_weekly WHERE item_id='rice_regular'").fetchone()[0]
        == 45.09
    )


def test_gdacs_point_time_infers_year_across_new_year():
    issued = "2026-12-30T12:00:00"
    assert point_time("31/12 06:00 UTC", issued) == datetime(2026, 12, 31, 6, tzinfo=UTC)
    assert point_time("02/01 00:00 UTC", issued) == datetime(2027, 1, 2, 0, tzinfo=UTC)
    assert point_time("Uncertainty Cones", issued) is None


def test_gdacs_staging_extracts_track_points(lake_dir):
    from nightfall.sources.weather.gdacs import slim_feature

    lake = Lake(lake_dir)
    raw = fixture("gdacs_map_raw_small.json")["features"]
    put(lake, "gdacs", "tc_current", [f for f in map(slim_feature, raw) if f["geometry"]])
    stage_all(lake)
    con = lake.connect()
    pts = con.execute(
        "SELECT name, lat, lon, radius_km, point_time FROM staging_storm_points ORDER BY point_time"
    ).fetchall()
    assert len(pts) >= 2 and pts[0][0] == "CHAMPI-26" and pts[0][3] > 0
    assert pts[0][4] < pts[-1][4]
    assert con.execute("SELECT count(*) FROM staging_storm_segments").fetchone()[0] >= 1


def test_ports_staging_is_dense_and_typed(lake_dir):
    lake = Lake(lake_dir)
    seed_ports(lake, days=30)
    stage_all(lake)
    con = lake.connect()
    n, lo, hi = con.execute(
        "SELECT count(*), min(date), max(date) FROM staging_port_daily WHERE portid='port694'"
    ).fetchone()
    assert n == 30 and (hi - lo).days == 29
    assert con.execute(
        "SELECT max(available_on - date), min(available_on - date) FROM staging_port_daily"
    ).fetchone() == (7, 7)
    assert con.execute("SELECT count(*) FROM staging_port_ref").fetchone()[0] == 2
    assert con.execute("SELECT count(*) FROM staging_chokepoint_daily").fetchone()[0] == 30


def test_open_meteo_staging_flattens_hourly_rows(lake_dir):
    from tests.helpers import seed_route_forecast

    lake = Lake(lake_dir)
    seed_route_forecast(lake, route_ids=["matnog-allen"], wave=3.2)
    stage_all(lake)
    con = lake.connect()
    n, wave = con.execute(
        "SELECT count(*), max(wave_m) FROM staging_route_forecast WHERE route_id='matnog-allen'"
    ).fetchone()
    assert n > 100 and wave == 3.2


def test_staging_is_rerunnable(lake_dir):
    lake = Lake(lake_dir)
    seed_fuel(lake)
    stage_all(lake)
    first = stage_all(lake)
    assert first["eia_spot"] == 240  # 4 products x 60 business days, unchanged on re-run


def test_staging_handles_empty_lake(lake_dir):
    counts = stage_all(Lake(lake_dir))
    assert counts["eia_spot"] == 0 and counts["port_daily"] == 0
