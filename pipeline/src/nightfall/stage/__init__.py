"""Staging: typed, deduplicated tables built from the raw lake. Re-runnable at any time."""

from __future__ import annotations

from collections.abc import Callable

import pyarrow as pa

from nightfall.core.lake import Lake
from nightfall.stage.markets import stage_da_weekly, stage_eia, stage_fx, stage_pink_sheet
from nightfall.stage.ports import stage_ports
from nightfall.stage.text import stage_aircraft, stage_ais, stage_news
from nightfall.stage.weather import stage_gdacs, stage_ibtracs, stage_route_forecast

STAGERS: list[Callable[[Lake], dict[str, pa.Table]]] = [
    stage_eia,
    stage_fx,
    stage_pink_sheet,
    stage_da_weekly,
    stage_ports,
    stage_gdacs,
    stage_ibtracs,
    stage_route_forecast,
    stage_news,
    stage_aircraft,
    stage_ais,
]


def stage_all(lake: Lake) -> dict[str, int]:
    """Run every stager; returns table name -> row count."""
    counts: dict[str, int] = {}
    for fn in STAGERS:
        for name, table in fn(lake).items():
            lake.write_table("staging", name, table)
            counts[name] = table.num_rows
    return counts
