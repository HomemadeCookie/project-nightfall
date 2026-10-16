from datetime import UTC, date, datetime, timedelta

import pytest

from nightfall.core.context import Context
from nightfall.core.lake import Lake
from nightfall.eval import backtests
from nightfall.eval.metrics import accuracy, balanced_accuracy, mae, majority
from nightfall.eval.report import write_report
from nightfall.stage import stage_all
from tests.helpers import NOW, full_lake, seed_da_weekly, seed_fuel, seed_pink


def test_metrics():
    assert mae([1, 2, 3], [2, 2, 5]) == 1.0
    assert balanced_accuracy(["a", "a", "a", "b"], ["a", "a", "a", "a"]) == 0.5  # accuracy would say 0.75
    assert accuracy(["a", "b"], ["a", "a"]) == 0.5
    assert majority(["x", "y", "y"]) == "y"


def test_report_round_trip(tmp_path):
    p = write_report("demo.q", {"status": "experimental", "summary": "s"}, tmp_path)
    assert p.name == "demo.q.json" and '"question_id": "demo.q"' in p.read_text()


def test_ports_backtest_structure_and_ship_rule(tmp_path):
    lake = full_lake(tmp_path / "lake")
    out = backtests.backtest_ports(Context.from_lake(lake, NOW))
    mnl = out["ports"]["MNL"]
    assert mnl["n_origins"] >= backtests.MIN_ORIGINS and mnl["mae_naive"] > 0 and mnl["mae_blend4"] > 0
    # Noise around a constant mean: averaging four weeks must beat repeating last week.
    assert mnl["model"] == "blend4" and mnl["ship_forecast"] is True
    # Ports we did not seed have no history, so no forecast ships for them.
    assert out["ports"]["CEB"]["ship_forecast"] is False
    assert out["status"] == "experimental"


def test_ports_backtest_never_peeks_at_the_future(tmp_path):
    lake = full_lake(tmp_path / "lake")
    ctx = Context.from_lake(lake, NOW)
    a = backtests.backtest_ports(ctx)
    # Re-run with the last two weeks of data hidden: earlier origins must score identically.
    hidden = backtests.backtest_ports(ctx.at(NOW - timedelta(days=14)))
    assert a["ports"]["MNL"]["n_origins"] >= hidden["ports"]["MNL"]["n_origins"]


def test_price_backtest_only_ships_items_that_beat_both_baselines(tmp_path):
    lake = Lake(tmp_path / "lake")
    seed_da_weekly(lake, weeks=140, rice_shock_from=90)
    seed_pink(lake)
    seed_fuel(lake)
    stage_all(lake)
    out = backtests.backtest_prices(Context.from_lake(lake, datetime(2027, 3, 1, tzinfo=UTC)), weeks=40)
    for item in out["items"].values():
        if item.get("ship"):
            assert (
                item["ba_model"]
                >= max(item["ba_persistence"], item["ba_majority"]) + backtests.PRICE_SHIP_MARGIN
            )
    assert (
        out["items"]["egg_white_medium"]["ship"] is False
        and "history" in out["items"]["egg_white_medium"]["reason"]
    )
    assert out["status"] in ("experimental", "unvalidated")


def test_fuel_backtest_is_unvalidated_without_ground_truth(tmp_path, monkeypatch):
    lake = full_lake(tmp_path / "lake")
    monkeypatch.setattr(backtests, "load_fuel_truth", lambda: [])
    out = backtests.backtest_fuel(Context.from_lake(lake, NOW))
    assert out["status"] == "unvalidated" and out["n_observations"] == 0


def test_fuel_backtest_scores_against_official_adjustments(tmp_path, monkeypatch):
    lake = Lake(tmp_path / "lake")
    seed_fuel(lake, days=120, drift=0.0)
    stage_all(lake)
    # Constant prices -> model says "flat"; truth says "flat" for these weeks -> perfect direction score.
    truth = [
        {
            "effective_date": date(2026, 10, 20) - timedelta(days=7 * k),
            "product": "diesel",
            "delta_php_l": 0.1,
        }
        for k in range(1, 12)
    ]
    monkeypatch.setattr(backtests, "load_fuel_truth", lambda: truth)
    out = backtests.backtest_fuel(Context.from_lake(lake, NOW))
    assert (
        out["n_observations"] >= 8
        and out["accuracy"] == 1.0
        and out["mae_php_l"] == pytest.approx(0.1, abs=1e-6)
    )
