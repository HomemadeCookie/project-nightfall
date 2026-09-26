"""Official port and trade statistics: parsers, fixtures, no network."""

from __future__ import annotations

import json
from pathlib import Path

from nightfall.config import Settings
from nightfall.sources import boc_tdp, ppa, psa_imts, registry, un_comtrade
from nightfall.sources.base import SourceFamily
from nightfall.stats import compile_official_stats
from nightfall.store import LocalRawStore, suffix_for

FIXTURES = Path(__file__).parent / "fixtures"


def test_statistics_adapters_are_not_mobility() -> None:
    names = {adapter.name: adapter.family for adapter in registry.ADAPTERS}
    assert names["adsb_lol"] is SourceFamily.MOBILITY
    assert names["ppa"] is SourceFamily.STATISTICS
    assert names["psa_imts"] is SourceFamily.STATISTICS
    assert names["un_comtrade"] is SourceFamily.STATISTICS
    assert names["boc_tdp"] is SourceFamily.STATISTICS
    assert {adapter.name for adapter in registry.mobility_adapters()} == {"adsb_lol", "aisstream"}


def test_xlsx_and_html_have_landing_zone_suffixes() -> None:
    assert suffix_for("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") == (
        ".xlsx.gz"
    )
    assert suffix_for("text/html") == ".html.gz"


def test_ppa_summary_unpivots_the_recorded_2024_workbook() -> None:
    body = (FIXTURES / "ppa_summary_2024.xlsx").read_bytes()
    grid = ppa.rows_from_xlsx(body)
    stats = ppa.tidy_summary(grid, year=2024)
    q1_ships = [
        row
        for row in stats
        if row.metric == "shipcalls"
        and row.breakdown == "all"
        and row.period == "Q1"
        and row.region == "PHILIPPINES"
    ]
    assert len(q1_ships) == 1
    assert q1_ships[0].value == 149224
    manila = next(
        row
        for row in stats
        if row.metric == "shipcalls"
        and row.breakdown == "all"
        and row.period == "Q1"
        and row.region == "MANILA/N. LUZON"
    )
    assert manila.value == 5167
    cargo = next(
        row
        for row in stats
        if row.metric == "cargo_throughput"
        and row.breakdown == "all"
        and row.period == "annual"
        and row.region == "PHILIPPINES"
    )
    assert cargo.unit == "metric_tons"
    assert cargo.value > 200_000_000


def test_psa_monthly_totals_decode_year_zero_as_1991() -> None:
    body = (FIXTURES / "psa_total_trade_monthly.json").read_bytes()
    cells = psa_imts.tidy_pxjson(body, table="total-trade-monthly")
    annual_total = next(cell for cell in cells if cell.period == "annual" and cell.flow == "total")
    assert annual_total.year == 2024
    assert annual_total.value == 200865
    january_exports = next(
        cell for cell in cells if cell.period == "Jan" and cell.flow == "exports"
    )
    assert january_exports.value == 6120


def test_comtrade_preview_keeps_hs_chapter_and_truncation_flag() -> None:
    body = (FIXTURES / "un_comtrade_hs2_2023_M.json").read_bytes()
    rows = un_comtrade.tidy_preview(body)
    assert {row.cmd_code for row in rows} == {"10", "27"}
    assert all(row.year == 2023 for row in rows)
    assert all(row.flow == "imports" for row in rows)
    assert all(row.truncated is False for row in rows)

    capped = json.loads(body)
    capped["count"] = 500
    flagged = un_comtrade.tidy_preview(json.dumps(capped).encode())
    assert all(row.truncated is True for row in flagged)


def test_boc_portal_note_explains_maintenance() -> None:
    html = (FIXTURES / "boc_tdp_portal.html").read_text()
    note = boc_tdp.portal_note(html)
    assert "maintenance" in note.lower()
    assert "psa" in note.lower()


def test_compile_from_fixtures(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path, run_id="trade-test")
    store = LocalRawStore(settings.raw_root)
    from tests.conftest import FIXTURE_AT

    store.put(
        source="ppa",
        request_key="summary/2024",
        body=(FIXTURES / "ppa_summary_2024.xlsx").read_bytes(),
        observed_at=FIXTURE_AT,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    store.put(
        source="psa_imts",
        request_key="imts/total-trade-monthly",
        body=(FIXTURES / "psa_total_trade_monthly.json").read_bytes(),
        observed_at=FIXTURE_AT,
        content_type="application/json",
    )
    store.put(
        source="un_comtrade",
        request_key="hs2/world/2023/M",
        body=(FIXTURES / "un_comtrade_hs2_2023_M.json").read_bytes(),
        observed_at=FIXTURE_AT,
        content_type="application/json",
    )
    inventory = compile_official_stats(settings)
    assert inventory["tables"]["ppa_port_stats"]["rows"] > 0
    assert inventory["tables"]["psa_trade_monthly"]["rows"] == 6
    assert inventory["tables"]["comtrade_hs"]["rows"] == 2
    assert inventory["not_a_map_overlay"] is True
    assert (tmp_path / "curated" / "v1" / "official_stats" / "inventory.json").is_file()
