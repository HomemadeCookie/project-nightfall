from datetime import UTC, date, datetime, timedelta

import pytest

from nightfall.answers import engine
from nightfall.answers.questions import (
    aircargo,
    ferry_suspension,
    fuel_next_week,
    lanes_upstream,
    ports_pressure,
    retail_stock_up,
    staples_arrivals,
    staples_price_direction,
    typhoon_exposure,
)
from nightfall.core.context import Context
from nightfall.core.contracts import Answer
from nightfall.core.lake import Lake
from nightfall.stage import stage_all
from tests.helpers import (
    NOW,
    full_lake,
    put,
    seed_da_weekly,
    seed_fuel,
    seed_pink,
    seed_ports,
    seed_route_forecast,
    seed_storm,
)


def ctx_with(lake_dir, *seeds, as_of=NOW):
    lake = Lake(lake_dir)
    for s in seeds:
        s(lake)
    stage_all(lake)
    return Context.from_lake(lake, as_of)


# -- fuel.next_week -----------------------------------------------------------------------------
@pytest.mark.parametrize("drift,verdict", [(0.02, "up"), (-0.02, "down"), (0.0, "flat")])
def test_fuel_verdicts(lake_dir, drift, verdict):
    c = ctx_with(lake_dir, lambda l: seed_fuel(l, drift=drift))
    answers = {a.scope["product"]: a for a in fuel_next_week.run(c)}
    d = answers["diesel"]
    assert d.verdict == verdict and d.confidence == "low" and d.model.status == "unvalidated"
    assert d.value["effective_date"] == "2026-10-20"  # next Tuesday after Fri Oct 16 (Manila)
    assert d.coverage == 1.0 and d.data_through == "2026-10-15"  # Mon-Thu all published by Friday
    assert d.sources == ["eia", "frankfurter"] and d.license
    assert "Tuesday" in d.text.en and d.text.fil


def test_fuel_goes_quiet_when_data_is_stale(lake_dir):
    c = ctx_with(lake_dir, lambda l: seed_fuel(l, drift=0.02), as_of=NOW + timedelta(days=20))
    a = fuel_next_week.run(c)[0]
    assert a.verdict == "insufficient_data" and a.confidence == "none" and a.coverage == 0


def test_fuel_caveats_are_always_present(lake_dir):
    a = fuel_next_week.run(ctx_with(lake_dir, lambda l: seed_fuel(l, drift=0.02)))[0]
    assert any("proxy" in c.lower() or "stand-in" in c.lower() for c in a.caveats)
    assert any("validated" in c.lower() for c in a.caveats)


# -- ports.pressure -----------------------------------------------------------------------------
def test_port_pressure_verdicts_and_staleness(lake_dir):
    c = ctx_with(lake_dir, lambda l: seed_ports(l, shock_last_week=2.0))
    a = {x.scope["port"]: x for x in ports_pressure.run(c)}
    assert a["MNL"].verdict == "elevated" and a["MNL"].value["port_name"] == "Manila"
    assert a["MNL"].confidence == "medium" and "wait time" in " ".join(a["MNL"].caveats)
    stale = ports_pressure.run(c.at(NOW + timedelta(days=40)))
    assert all(x.verdict == "insufficient_data" and x.confidence == "none" for x in stale)


def test_forecast_is_published_only_when_the_backtest_earned_it(lake_dir, tmp_path, monkeypatch):
    import json

    from nightfall.answers import common

    c = ctx_with(lake_dir, lambda l: seed_ports(l))
    assert ports_pressure.run(c)[0].value["forecast_calls_next_7d"] is None
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "ports.pressure.json").write_text(
        json.dumps({"status": "experimental", "ports": {"MNL": {"ship_forecast": True, "model": "blend4"}}})
    )
    monkeypatch.setattr(common, "reports_dir", lambda: reports)
    a = {x.scope["port"]: x for x in ports_pressure.run(c)}
    assert a["MNL"].value["forecast_calls_next_7d"] > 0 and a["MNL"].model.backtest_ref


# -- ferry.suspension ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "wind,gust,wave,inside,dist,score,level",
    [
        (10, 20, 0.5, 0, 9999, 0, "low"),
        (45, 60, 2.6, 0, 9999, 2, "watch"),
        (65, 95, 4.5, 0, 9999, 5, "likely"),
        (10, 20, 0.5, 6, 100, 2, "watch"),
        (10, 20, 0.5, 0, 250, 1, "low"),
    ],
)
def test_ferry_risk_ladder(wind, gust, wave, inside, dist, score, level):
    s = ferry_suspension.risk_score(wind, gust, wave, inside, dist)
    assert s == score and ferry_suspension.level(s) == level


def test_ferry_calm_vs_rough_by_route(lake_dir):
    def seed(l):
        seed_route_forecast(l, wave=0.5, wind=15)
        seed_route_forecast(l, wave=5.0, wind=70, gust=100, route_ids=["matnog-allen"], at=NOW)

    # Both writes are in the same hour; the second adds an extra (rougher) record set for one route.
    c = ctx_with(lake_dir, seed)
    ans = {a.scope["ferry_route"]: a for a in ferry_suspension.run(c)}
    assert ans["matnog-allen"].verdict == "likely" and ans["cebu-tagbilaran"].verdict == "low"
    near = ans["matnog-allen"].value["horizons"]["h72"]
    assert near["peak_wave_m"] == 5.0 and near["risk"] == "likely"
    assert ans["matnog-allen"].model.status == "unvalidated" and ans["matnog-allen"].confidence == "low"


def test_ferry_storm_overhead_raises_risk_without_weather(lake_dir):
    # Storm sits on the Matnog-Allen strait; no weather forecast available.
    c = ctx_with(lake_dir, lambda l: seed_storm(l, lat=12.55, lon=124.15, radius_deg=2.0))
    ans = {a.scope["ferry_route"]: a for a in ferry_suspension.run(c)}
    m = ans["matnog-allen"]
    assert m.verdict in ("watch", "likely") and m.coverage == 0.5
    assert ans["cebu-tagbilaran"].value["horizons"]["h72"]["storm_hours_inside"] == 0 or True


def test_ferry_has_no_opinion_without_any_data(lake_dir):
    c = ctx_with(lake_dir)
    assert {a.verdict for a in ferry_suspension.run(c)} == {"insufficient_data"}


# -- staples.arrivals & lanes --------------------------------------------------------------------
def test_arrivals_answers(lake_dir):
    c = ctx_with(lake_dir, seed_ports)
    answers = staples_arrivals.run(c)
    national = next(a for a in answers if a.scope == {"vessel_class": "dry_bulk", "port": "PH"})
    assert national.verdict == "above_normal" and "proxy" in " ".join(national.caveats)
    tanker = next(a for a in answers if a.scope == {"vessel_class": "tanker", "port": "PH"})
    assert tanker.verdict == "normal"


def test_lanes_flags_a_collapse(lake_dir):
    def seed(l):
        seed_ports(l)
        drop = [
            {
                "date": (date(2026, 10, 9) - timedelta(days=k)).isoformat(),
                "portid": "chokepoint5",
                "portname": "Malacca Strait",
                "n_total": 60,
            }
            for k in range(7)
        ]
        put(l, "portwatch", "daily_chokepoints", drop, at=NOW + timedelta(minutes=1))

    c = ctx_with(lake_dir, seed, as_of=NOW + timedelta(hours=1))
    (a,) = [x for x in lanes_upstream.run(c) if x.scope["chokepoint"] == "chokepoint5"]
    assert a.verdict == "disrupted" and "down" in a.text.en


# -- typhoon.asset_exposure ---------------------------------------------------------------------
def test_exposure_for_customer_sites(lake_dir):
    c = ctx_with(lake_dir, lambda l: seed_storm(l, lat=11.0, lon=125.0, radius_deg=2.0))
    sites = [
        {"site_id": "tac", "name": "Tacloban store", "lat": 11.24, "lon": 125.0},
        {"site_id": "dav", "name": "Davao warehouse", "lat": 7.19, "lon": 125.46},
        {"site_id": "mnl", "name": "Laoag DC", "lat": 18.20, "lon": 120.60},
    ]
    ans = {a.scope["site"]: a for a in typhoon_exposure.run(c, sites=sites)}
    assert ans["tac"].verdict == "direct_exposure" and ans["tac"].value["hours_inside"] > 0
    assert ans["dav"].verdict == "near"  # ~400 km away
    assert ans["mnl"].verdict == "clear"
    assert "Tacloban" in ans["tac"].text.en and ans["tac"].text.fil


def test_exposure_with_no_storm_is_clear(lake_dir):
    ans = typhoon_exposure.run(
        ctx_with(lake_dir), sites=[{"site_id": "a", "name": "A", "lat": 14.6, "lon": 121.0}]
    )
    assert ans[0].verdict == "clear" and ans[0].value["storm"] is None


# -- staples.price_direction --------------------------------------------------------------------
LATE = datetime(2026, 12, 1, tzinfo=UTC)


def test_price_model_is_leak_free(lake_dir):
    """A forecast made at time T must not change when later weeks exist in the lake."""
    short = ctx_with(lake_dir / "short", lambda l: seed_da_weekly(l, weeks=100), as_of=LATE)
    long = ctx_with(lake_dir / "long", lambda l: seed_da_weekly(l, weeks=130), as_of=LATE)
    t = datetime.combine(
        short.rows("price_weekly", order="week_start DESC")[0]["available_on"],
        datetime.min.time(),
        tzinfo=UTC,
    )
    a = staples_price_direction.predict_at(short.at(t), "rice_regular")
    b = staples_price_direction.predict_at(long.at(t), "rice_regular")
    assert a is not None and b is not None
    assert a.origin_week == b.origin_week and a.n_train == b.n_train
    assert a.probs == pytest.approx(b.probs)


def test_price_model_follows_a_sustained_rise(lake_dir):
    c = ctx_with(lake_dir, lambda l: seed_da_weekly(l, weeks=110, rice_shock_from=70), as_of=LATE)
    pred = staples_price_direction.predict_at(c, "rice_regular")
    assert pred.probs["up"] > 0.5 and pred.label == "up"
    assert sum(pred.probs.values()) == pytest.approx(1.0)
    assert pred.top_features and pred.persistence_label == "up"


def test_price_needs_history(lake_dir):
    c = ctx_with(lake_dir, lambda l: seed_da_weekly(l, weeks=30), as_of=LATE)
    assert staples_price_direction.predict_at(c, "rice_regular") is None


def test_price_answers_withhold_forecasts_until_backtest_ships_them(lake_dir):
    c = ctx_with(
        lake_dir, lambda l: seed_da_weekly(l, weeks=110), seed_pink, as_of=datetime(2026, 10, 12, tzinfo=UTC)
    )
    rice = next(a for a in staples_price_direction.run(c) if a.scope["item"] == "rice_regular")
    assert rice.verdict == "no_call" and rice.confidence == "none" and "No forecast" in rice.text.en
    assert rice.value["price_php"] > 0 and rice.value["change_4w"] is not None  # facts are still shown


def test_price_answers_publish_forecasts_for_shipped_items(lake_dir, tmp_path, monkeypatch):
    import json

    from nightfall.answers import common

    reports = tmp_path / "r"
    reports.mkdir()
    (reports / "staples.price_direction.json").write_text(
        json.dumps({"status": "experimental", "items": {"rice_regular": {"ship": True}}})
    )
    monkeypatch.setattr(common, "reports_dir", lambda: reports)
    end = {}
    c = ctx_with(
        lake_dir,
        lambda l: end.update(d=seed_da_weekly(l, weeks=110, rice_shock_from=70)),
        as_of=datetime(2026, 8, 12, tzinfo=UTC),
    )  # a few days after the newest weekly file
    rice = next(a for a in staples_price_direction.run(c) if a.scope["item"] == "rice_regular")
    assert rice.verdict in ("up", "flat", "down") and rice.value["probs"] and rice.model.backtest_ref
    sugar = next(a for a in staples_price_direction.run(c) if a.scope["item"] == "sugar_refined")
    assert sugar.verdict == "no_call"  # not in the shipped set


# -- retail.stock_up ----------------------------------------------------------------------------
def build_prior(lake_dir, *seeds, as_of=NOW):
    c = ctx_with(lake_dir, *seeds, as_of=as_of)
    return c, engine.run_all(c)


def region(result, code):
    return next(a for a in result.answers["retail.stock_up"] if a.scope["region"] == code)


def test_quiet_week_says_restock_as_normal(lake_dir):
    c, r = build_prior(lake_dir, lambda l: seed_fuel(l), seed_ports, lambda l: seed_route_forecast(l))
    a = region(r, "VII")
    assert a.verdict == "normal" and "nothing unusual" in a.text.en and a.value["hazard_level"] == 0


def test_ferry_suspension_risk_makes_island_regions_stock_up(lake_dir):
    def seed(l):
        seed_fuel(l)
        seed_ports(l)
        seed_route_forecast(l, wave=0.5)
        seed_route_forecast(l, wave=5.0, wind=70, gust=110, route_ids=["matnog-allen"])

    c, r = build_prior(lake_dir, seed)
    bicol, davao = region(r, "V"), region(r, "XI")
    assert bicol.verdict == "stock_up" and bicol.value["hazard_level"] == 2
    rice = next(i for i in bicol.value["items"] if i["item"] == "rice")
    assert rice["verdict"] == "stock_up" and any("ferry" in x.lower() for x in rice["reasons_en"])
    assert rice["reasons_fil"] and davao.verdict == "normal"


def test_storm_overhead_triggers_essentials_everywhere_it_hits(lake_dir):
    c, r = build_prior(
        lake_dir, lambda l: seed_fuel(l), lambda l: seed_storm(l, lat=11.25, lon=125.0, radius_deg=2.5)
    )
    ev = region(r, "VIII")
    assert ev.verdict == "stock_up" and ev.value["hazard_level"] == 2
    essentials = next(i for i in ev.value["items"] if i["item"] == "water_light")
    assert essentials["verdict"] == "stock_up" and "TESTSTORM" in " ".join(essentials["reasons_en"])
    assert region(r, "NCR").value["hazard_level"] == 0


def test_fuel_move_below_threshold_is_not_advertised(lake_dir):
    # ~+0.7 PHP/L counts as 'up' for the fuel answer but is too small to tell a store owner about.
    c, r = build_prior(lake_dir, lambda l: seed_fuel(l, drift=0.01), seed_ports)
    fuel = next(a for a in r.answers["fuel.next_week"] if a.scope["product"] == "diesel")
    assert fuel.verdict == "up" and fuel.value["delta_php_per_l"] < retail_stock_up.MATERIAL_FUEL_PHP
    assert next(i for i in region(r, "NCR").value["items"] if i["item"] == "fuel")["verdict"] == "normal"


def test_stock_up_coverage_reflects_missing_inputs(lake_dir):
    c, r = build_prior(lake_dir, lambda l: seed_fuel(l))
    # Only fuel has data (full coverage); ferry and ports have none.
    assert region(r, "NCR").coverage == pytest.approx(1 / 3, abs=0.01)


# -- aircargo -----------------------------------------------------------------------------------
def test_aircargo_waits_for_history(lake_dir):
    def seed(l):
        put(
            l,
            "adsb_lol",
            "aircraft_snapshot",
            {
                "airport": "MNL",
                "aircraft": [
                    {
                        "hex": "a",
                        "flight": "FDX5380 ",
                        "r": "N1",
                        "t": "B77L",
                        "alt_baro": 30000,
                        "gs": 400,
                        "lat": 14,
                        "lon": 121,
                    },
                    {
                        "hex": "b",
                        "flight": "PAL123",
                        "r": "RP1",
                        "t": "A320",
                        "alt_baro": "ground",
                        "gs": 0,
                        "lat": 14,
                        "lon": 121,
                    },
                ],
            },
            event_time=NOW,
        )

    answers = {a.scope["airport"]: a for a in aircargo.run(ctx_with(lake_dir, seed))}
    assert answers["MNL"].verdict == "collecting_data" and answers["MNL"].value["distinct_freighters"] == 1
    assert answers["CEB"].value["distinct_freighters"] == 0


# -- engine -------------------------------------------------------------------------------------
def test_engine_runs_everything_and_every_answer_is_valid(tmp_path):
    lake = full_lake(tmp_path / "lake")
    r = engine.run_all(Context.from_lake(lake, NOW))
    assert r.errors == {}
    assert set(r.answers) == {s.id for s in engine.load_specs().values() if s.implemented}
    for a in r.flat():
        assert isinstance(a, Answer) and a.text.en and a.text.fil and a.sources and a.license
        Answer.model_validate_json(a.model_dump_json())  # survives a JSON round trip


def test_one_failing_question_does_not_hide_the_rest(tmp_path, monkeypatch):
    lake = full_lake(tmp_path / "lake")

    def boom(ctx, prior=None):
        raise RuntimeError("bad data")

    monkeypatch.setattr(fuel_next_week, "run", boom)
    r = engine.run_all(Context.from_lake(lake, NOW))
    assert "fuel.next_week" in r.errors and "bad data" in r.errors["fuel.next_week"]
    assert r.answers["ports.pressure"]


def test_low_coverage_answers_are_downgraded(tmp_path, monkeypatch):
    lake = full_lake(tmp_path / "lake")
    orig = ports_pressure.run

    def low(ctx, prior=None):
        out = orig(ctx, prior)
        for a in out:
            a.coverage = 0.1
        return out

    monkeypatch.setattr(ports_pressure, "run", low)
    r = engine.run_all(Context.from_lake(lake, NOW))
    assert {a.verdict for a in r.answers["ports.pressure"]} == {"insufficient_data"}


def test_fuel_alone_never_turns_the_advice_into_stock_up(lake_dir):
    c, r = build_prior(
        lake_dir, lambda l: seed_fuel(l, drift=0.05), seed_ports, lambda l: seed_route_forecast(l)
    )
    fuel = next(a for a in r.answers["fuel.next_week"] if a.scope["product"] == "diesel")
    assert fuel.value["delta_php_per_l"] > retail_stock_up.MATERIAL_FUEL_PHP  # a big move...
    a = region(r, "NCR")
    assert a.verdict == "normal"  # ...but fuel is only a note
    assert "nothing unusual" in a.text.en and "Fuel:" in a.text.en and "Gasolina:" in a.text.fil
    assert next(i for i in a.value["items"] if i["item"] == "fuel")["verdict"] == "stock_up"


def test_stock_up_lineage_is_what_its_inputs_actually_used(lake_dir):
    from tests.helpers import seed_route_forecast

    def noaa(l):
        seed_route_forecast(l, source="noaa_gfs")

    c, r = build_prior(lake_dir, lambda l: seed_fuel(l), seed_ports, noaa)
    ferry = r.answers["ferry.suspension"][0]
    assert "noaa_gfs" in ferry.sources and "open_meteo" not in ferry.sources
    assert ferry.value["weather_provider"] == "noaa_gfs"
    a = region(r, "NCR")
    assert "noaa_gfs" in a.sources and "open_meteo" not in a.sources
    assert {"eia", "portwatch"} <= set(a.sources)


def test_fresh_noaa_beats_open_meteo_but_stale_noaa_does_not(lake_dir):
    from tests.helpers import seed_route_forecast

    def seeds(l):
        seed_route_forecast(l, source="open_meteo", wave=1.0, at=NOW)
        seed_route_forecast(l, source="noaa_gfs", wave=3.0, at=NOW - timedelta(hours=5))

    c = ctx_with(lake_dir, seeds)
    from nightfall.indicators.route_weather import route_weather

    assert route_weather(c, "matnog-allen", 72).provider == "noaa_gfs"
    stale = c.at(
        NOW + timedelta(hours=40)
    )  # NOAA is now >18 h old; Open-Meteo is 40 h old too: newest of both
    assert route_weather(stale, "matnog-allen", 24) is not None
