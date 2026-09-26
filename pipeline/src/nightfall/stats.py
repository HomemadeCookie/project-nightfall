"""Turn official statistics raw objects into tidy analysis tables.

These are not map overlays. Grain is month or quarter at a port, region, or country —
the same grain the product's success metrics use (README § Success Metrics).
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from nightfall.clock import isoformat_z, utc_now
from nightfall.config import SCHEMA_VERSION, Settings
from nightfall.sources import ppa, psa_imts, un_comtrade
from nightfall.store import LocalRawStore

PPA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def compile_official_stats(settings: Settings) -> dict[str, Any]:
    """Read `raw/` for statistics sources and write parquet + an inventory sidecar."""
    store = LocalRawStore(settings.raw_root)
    out = settings.curated_dir / f"v{SCHEMA_VERSION}" / "official_stats"
    out.mkdir(parents=True, exist_ok=True)

    ppa_rows = _load_ppa(store.root)
    psa_rows = _load_psa(store.root)
    comtrade_rows = _load_comtrade(store.root)

    written: list[str] = []
    if ppa_rows:
        written.append(_write_table(out / "ppa_port_stats.parquet", ppa_rows))
    if psa_rows:
        written.append(_write_table(out / "psa_trade_monthly.parquet", psa_rows))
    if comtrade_rows:
        written.append(_write_table(out / "comtrade_hs.parquet", comtrade_rows))

    inventory = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": isoformat_z(utc_now()),
        "run_id": settings.run_id,
        "grain": "month_or_quarter",
        "not_a_map_overlay": True,
        "tables": {
            "ppa_port_stats": {
                "rows": len(ppa_rows),
                "source": "ppa",
                "note": "PPA regional quarterly throughput. Not a vessel track.",
            },
            "psa_trade_monthly": {
                "rows": len(psa_rows),
                "source": "psa_imts",
                "note": "PSA IMTS monthly totals, compiled from BOC declarations.",
            },
            "comtrade_hs": {
                "rows": len(comtrade_rows),
                "source": "un_comtrade",
                "note": "UN Comtrade preview: HS chapters vs World, TOTAL vs partners.",
            },
        },
        "boc_tdp": {
            "rows": 0,
            "note": (
                "No bulk extract. Use psa_trade_monthly as the official published form "
                "of BOC merchandise-trade declarations."
            ),
        },
        "files": written,
    }
    inventory_path = out / "inventory.json"
    inventory_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    return inventory


def _write_table(path: Path, rows: list[dict[str, Any]]) -> str:
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path, compression="zstd")
    return str(path)


def _load_ppa(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _raw_files(root, "ppa"):
        body = gzip.decompress(path.read_bytes())
        grid = ppa.rows_from_xlsx(body)
        year = _year_from_grid(grid)
        for stat in ppa.tidy_summary(grid, year=year):
            rows.append(asdict(stat))
    return rows


def _year_from_grid(grid: list[list[str]]) -> int:
    for row in grid[:8]:
        for cell in row:
            token = str(cell).strip()
            if len(token) == 4 and token.isdigit() and token.startswith("20"):
                return int(token)
    raise ValueError("PPA workbook has no publication year in its title rows")


def _load_psa(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _raw_files(root, "psa_imts"):
        if path.name.endswith(".html.gz"):
            continue
        body = gzip.decompress(path.read_bytes())
        try:
            document = json.loads(body)
        except json.JSONDecodeError:
            continue
        if "data" not in document:
            continue
        for cell in psa_imts.tidy_pxjson(body, table="total-trade-monthly"):
            rows.append(asdict(cell))
    return rows


def _load_comtrade(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _raw_files(root, "un_comtrade"):
        body = gzip.decompress(path.read_bytes())
        for row in un_comtrade.tidy_preview(body):
            rows.append(asdict(row))
    return rows


def _raw_files(root: Path, source: str) -> list[Path]:
    folder = root / "raw" / source
    if not folder.exists():
        return []
    return sorted(folder.rglob("*.gz"))
