"""Collect official port and trade statistics into analysis tables.

Does not touch the map overlay. Writes tidy parquet under build/curated/ (gitignored)
from live upstreams, or from recorded fixtures when `--fixtures` is passed so CI
never calls a live API.

    uv run --project pipeline python pipeline/scripts/seed_trade.py
    uv run --project pipeline python pipeline/scripts/seed_trade.py --fixtures
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT / "src"))
sys.path.insert(0, str(PIPELINE_ROOT))

from nightfall.cli import collect
from nightfall.config import Settings
from nightfall.stats import compile_official_stats
from nightfall.store import LocalRawStore
from tests.conftest import FIXTURE_AT

log = logging.getLogger("nightfall.trade")
LOG_FORMAT = "%(asctime)sZ %(levelname)s %(name)s %(message)s"

FIXTURES = PIPELINE_ROOT / "tests" / "fixtures"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    logging.Formatter.converter = time.gmtime

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures",
        action="store_true",
        help="Land recorded fixtures instead of calling upstream (required in CI).",
    )
    args = parser.parse_args()

    settings = Settings(data_root=PIPELINE_ROOT.parent / "build", run_id="trade")
    settings.curated_dir.mkdir(parents=True, exist_ok=True)
    settings.serving_dir.mkdir(parents=True, exist_ok=True)

    if args.fixtures:
        _seed_fixtures(settings)
    else:
        for source in ("ppa", "psa_imts", "un_comtrade", "boc_tdp"):
            collect(source, settings)

    inventory = compile_official_stats(settings)
    log.info("inventory %s", json.dumps(inventory["tables"], sort_keys=True))
    log.info("wrote %s", inventory["files"])
    return 0


def _seed_fixtures(settings: Settings) -> None:
    """Copy recorded official extracts into the landing zone as if they had been collected."""
    store = LocalRawStore(settings.raw_root)
    mapping = (
        (
            "ppa",
            "summary/2024",
            "ppa_summary_2024.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (
            "psa_imts",
            "imts/total-trade-monthly",
            "psa_total_trade_monthly.json",
            "application/json",
        ),
        ("un_comtrade", "hs2/world/2023/M", "un_comtrade_hs2_2023_M.json", "application/json"),
        ("boc_tdp", "portal", "boc_tdp_portal.html", "text/html"),
    )
    for source, key, filename, content_type in mapping:
        body = (FIXTURES / filename).read_bytes()
        store.put(
            source=source,
            request_key=key,
            body=body,
            observed_at=FIXTURE_AT,
            content_type=content_type,
        )


if __name__ == "__main__":
    raise SystemExit(main())
