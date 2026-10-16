from datetime import UTC, date, datetime, timedelta

import pytest

from nightfall.core.context import ASOF_COLUMN, Context
from nightfall.core.lake import Lake
from nightfall.stage import stage_all
from tests.helpers import NOW, seed_ports


def test_rows_never_include_data_published_after_as_of(lake_dir):
    lake = Lake(lake_dir)
    seed_ports(lake, end=date(2026, 10, 9), days=40)
    stage_all(lake)
    # PortWatch lags 7 days: on Oct 12 we can only know Oct 5 and earlier.
    ctx = Context.from_lake(lake, datetime(2026, 10, 12, 12, tzinfo=UTC))
    dates = [r["date"] for r in ctx.rows("port_daily", "portid='port694'", order="date")]
    assert dates[-1] == date(2026, 10, 5)
    later = ctx.at(datetime(2026, 10, 16, 12, tzinfo=UTC))
    assert [r["date"] for r in later.rows("port_daily", "portid='port694'", order="date")][-1] == date(
        2026, 10, 9
    )


def test_forecast_tables_filter_on_issue_time(lake_dir):
    from tests.helpers import seed_route_forecast

    lake = Lake(lake_dir)
    seed_route_forecast(lake, at=NOW, route_ids=["matnog-allen"])
    seed_route_forecast(lake, at=NOW + timedelta(hours=6), route_ids=["matnog-allen"], wave=4.0)
    stage_all(lake)
    ctx = Context.from_lake(lake, NOW + timedelta(hours=1))
    assert ctx.latest_issue("route_forecast") == NOW  # the 06:00 issue is still in the future
    assert ctx.at(NOW + timedelta(hours=7)).latest_issue("route_forecast") == NOW + timedelta(hours=6)


def test_unknown_table_without_an_asof_rule_is_an_error(lake_dir):
    import pyarrow as pa

    lake = Lake(lake_dir)
    lake.write_table("staging", "mystery", pa.table({"a": [1]}))
    ctx = Context.from_lake(lake, NOW)
    with pytest.raises(KeyError, match="as-of"):
        ctx.rows("mystery")


def test_missing_table_returns_empty(lake_dir):
    assert Context.from_lake(Lake(lake_dir), NOW).rows("eia_spot") == []


def test_every_staged_table_has_an_asof_rule_or_is_reference(lake_dir):
    from nightfall.core.context import UNVERSIONED

    counts = stage_all(Lake(lake_dir))
    missing = set(counts) - set(ASOF_COLUMN) - UNVERSIONED
    assert missing == set(), f"add an as-of rule for: {sorted(missing)}"
