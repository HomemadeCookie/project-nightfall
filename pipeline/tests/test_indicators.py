from datetime import UTC, date, datetime, timedelta

import pytest

from nightfall.core.context import Context
from nightfall.core.lake import Lake
from nightfall.indicators import arrivals, chokepoints, fuel, ports, prices, storms
from nightfall.stage import stage_all
from tests.helpers import NOW, put, seed_da_weekly, seed_fuel, seed_ports, seed_storm

LITRES = 3.78541


def ctx_for(lake_dir, seed, as_of=NOW):
    lake = Lake(lake_dir)
    seed(lake)
    stage_all(lake)
    return Context.from_lake(lake, as_of)


# -- fuel --------------------------------------------------------------------------------------
def test_flat_prices_give_zero_change(lake_dir):
    sig = fuel.fuel_signal(ctx_for(lake_dir, lambda l: seed_fuel(l)), "diesel")
    assert sig.delta_php_l == pytest.approx(0.0, abs=1e-9)
    assert sig.current.php_per_l == pytest.approx(2.50 * 58 / LITRES)


def test_rising_prices_give_the_expected_peso_change(lake_dir):
    # 4 trading days this week (Mon-Thu) vs 5 last week: mean index gap is 4.5 steps of $0.02.
    sig = fuel.fuel_signal(ctx_for(lake_dir, lambda l: seed_fuel(l, drift=0.02)), "diesel")
    assert sig.delta_php_l == pytest.approx(4.5 * 0.02 * 58 / LITRES, rel=1e-6)
    assert sig.current.n_days == 4 and sig.previous.n_days == 5
    assert sig.data_through == date(2026, 10, 15)


def test_fuel_signal_needs_two_weeks(lake_dir):
    assert fuel.fuel_signal(ctx_for(lake_dir, lambda l: seed_fuel(l, days=3)), "diesel") is None


def test_fuel_uses_only_prices_available_at_as_of(lake_dir):
    c = ctx_for(lake_dir, lambda l: seed_fuel(l, drift=0.02))
    early = c.at(datetime(2026, 10, 13, 12, tzinfo=UTC))  # Tuesday: only Monday's price is public
    assert fuel.fuel_signal(early, "diesel").current.n_days == 1


# -- ports -------------------------------------------------------------------------------------
def test_pressure_flags_a_surge_and_a_lull(lake_dir):
    surge = ports.pressure(ctx_for(lake_dir / "a", lambda l: seed_ports(l, shock_last_week=2.0)), "port694")
    lull = ports.pressure(ctx_for(lake_dir / "b", lambda l: seed_ports(l, shock_last_week=0.4)), "port694")
    calm = ports.pressure(ctx_for(lake_dir / "c", lambda l: seed_ports(l)), "port694")
    assert surge.z > 2 and lull.z < -2 and abs(calm.z) < 2
    assert surge.data_through == date(2026, 10, 9) and surge.weeks_of_history >= 50
    assert calm.yoy_ratio is not None and 0.8 < calm.yoy_ratio < 1.2


def test_pressure_needs_history(lake_dir):
    assert ports.pressure(ctx_for(lake_dir, lambda l: seed_ports(l, days=20)), "port694") is None


def test_weekly_sums_align_to_the_latest_day():
    assert ports.weekly_sums([1] * 3 + [2] * 7 + [3] * 7) == [14, 21]


def test_forecast_models():
    vals = [10.0] * 21 + [20.0] * 7
    assert ports.forecast_next_week(vals, "naive") == 140.0
    assert ports.forecast_next_week(vals, "blend4") == pytest.approx((70 * 3 + 140) / 4)
    with pytest.raises(ValueError):
        ports.forecast_next_week(vals, "nope")


# -- arrivals & chokepoints ----------------------------------------------------------------------
def test_arrivals_detects_a_28_day_surge_in_dry_bulk(lake_dir):
    a = arrivals.arrivals(ctx_for(lake_dir, seed_ports), "dry_bulk")
    assert 0.3 < a.pct_vs_norm < 0.5 and a.pct_vs_last_year is not None
    t = arrivals.arrivals(ctx_for(lake_dir / "t", seed_ports), "tanker")
    assert abs(t.pct_vs_norm) < 0.1


def test_arrivals_can_be_limited_to_ports(lake_dir):
    c = ctx_for(lake_dir, seed_ports)
    one = arrivals.arrivals(c, "tanker", ["port125"])
    both = arrivals.arrivals(c, "tanker")
    assert one.tonnes_28d < both.tonnes_28d


def test_chokepoint_drop_is_visible(lake_dir):
    lake = Lake(lake_dir)
    seed_ports(lake)
    drop = [
        {
            "date": (date(2026, 10, 9) - timedelta(days=k)).isoformat(),
            "portid": "chokepoint5",
            "portname": "Malacca Strait",
            "n_total": 100,
            "n_container": 0,
            "n_dry_bulk": 0,
            "n_tanker": 0,
            "n_roro": 0,
            "capacity": 1,
        }
        for k in range(7)
    ]
    put(lake, "portwatch", "daily_chokepoints", drop, at=NOW + timedelta(hours=1))
    stage_all(lake)
    p = chokepoints.pressure(Context.from_lake(lake, NOW + timedelta(hours=2)), "chokepoint5")
    assert p.pct_vs_baseline < -0.4 and p.z < -3


# -- storms ------------------------------------------------------------------------------------
def test_storm_exposure_inside_and_outside_the_wind_field(lake_dir):
    c = ctx_for(lake_dir, lambda l: seed_storm(l, lat=13.0, lon=123.0, radius_deg=2.0))
    (track,) = storms.current_tracks(c)
    assert track.name == "TESTSTORM" and len(track.points) == 7
    near = storms.exposure(track, [(13.0, 123.0)], c.as_of, 72)
    assert near.hours_inside >= 3 and near.first_inside == c.as_of and near.min_distance_km < 5
    far = storms.exposure(track, [(5.0, 140.0)], c.as_of, 72)
    assert far.hours_inside == 0 and far.min_distance_km > 1500


def test_position_interpolates_between_timed_points(lake_dir):
    c = ctx_for(lake_dir, lambda l: seed_storm(l, lat=13.0, lon=123.0))
    (track,) = storms.current_tracks(c)
    mid = storms.position_at(track, c.as_of + timedelta(hours=6))
    assert mid.lon == pytest.approx(123.0 - 0.15) and mid.lat == pytest.approx(13.0)
    assert storms.position_at(track, c.as_of - timedelta(hours=1)) is None  # before the first point
    assert storms.position_at(track, c.as_of + timedelta(hours=100)) is None  # after the last


def test_ended_and_out_of_basin_storms_are_ignored(lake_dir):
    c = ctx_for(
        lake_dir,
        lambda l: (
            seed_storm(l, name="PACIFIC", lat=13, lon=123),
            seed_storm(l, name="EASTPAC", lat=15, lon=-105),
        ),
    )
    assert {t.name for t in storms.current_tracks(c)} == {"PACIFIC", "EASTPAC"} - {"EASTPAC"}
    assert storms.current_tracks(c.at(NOW + timedelta(days=10))) == []  # storm has ended


def test_worst_exposure_picks_the_most_threatening_storm(lake_dir):
    def seed(l):
        seed_storm(l, name="NEAR", lat=13, lon=123)
        put(l, "gdacs", "tc_current", [], at=NOW)  # an empty issue must not matter

    c = ctx_for(lake_dir, seed)
    w = storms.worst_exposure(c, [(13.0, 123.0)], 48)
    assert w.name == "NEAR" and w.hours_inside > 0
    assert storms.worst_exposure(c.at(NOW - timedelta(days=1)), [(13, 123)], 48) is None


# -- prices ------------------------------------------------------------------------------------
def test_weekly_prices_and_direction_thresholds(lake_dir):
    c = ctx_for(lake_dir, lambda l: seed_da_weekly(l, weeks=30), as_of=datetime(2027, 2, 1, tzinfo=UTC))
    series = prices.weekly_prices(c, "rice_regular")
    assert len(series) == 30 and series[0].week_start == date(2024, 7, 1)
    assert (
        prices.direction(0.03) == "up"
        and prices.direction(-0.03) == "down"
        and prices.direction(0.01) == "flat"
    )
    assert prices.pct(110, 100) == pytest.approx(0.10) and prices.pct(1, 0) == 0.0


def test_features_need_twelve_weeks_of_history(lake_dir):
    c = ctx_for(lake_dir, lambda l: seed_da_weekly(l, weeks=30), as_of=datetime(2027, 2, 1, tzinfo=UTC))
    series = prices.weekly_prices(c, "rice_regular")
    assert prices.features_at(series, 5, [], [], []) is None
    f = prices.features_at(series, 20, [], [], [])
    assert len(f) == len(prices.FEATURE_NAMES) and f[3] == f[4] == f[5] == 0.0  # no world/fx/fuel data
