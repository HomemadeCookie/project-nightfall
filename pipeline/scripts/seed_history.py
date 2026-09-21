"""Bake the densest honest mobility window this project can serve at $0.00.

Year A-B is not fillable: see README Historical mobility window. This script downloads one
adsb.lol globe_history day (ODbL, no payment method), keeps traces that intersect the
Philippine AOI, and — because no free AIS archive covers those waters — plants fixture
vessel windows on that same calendar day so both modes can be exercised. The manifest labels
each source honestly.

    uv run --project pipeline python pipeline/scripts/seed_history.py --date 2026-09-12

Pass `--skip-download` when `raw/adsb_lol/` already holds that day's traces.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT))

from tests.conftest import seed_ais_windows

from nightfall.bake import bake
from nightfall.config import Settings
from nightfall.health import HealthReport
from nightfall.sources.adsb_history import collect_globe_history, default_history_day
from nightfall.store import LocalRawStore
from nightfall.transform import transform

log = logging.getLogger("nightfall.history")

LOG_FORMAT = "%(asctime)sZ %(levelname)s %(name)s %(message)s"

AIS_ORIGIN = (120.62, 14.40)
AIS_SPACING = (0.07, 0.05)
AIS_VESSELS = 40
AIS_REPORTS = 20
AIS_INTERVAL_S = 20.0
AIS_WINDOW_S = 400.0
# Four windows at different times of day, so a fixed offset cannot alias the fixture the way
# a single 03:00 sample would (README § Risks, coverage sparsity).
AIS_HOUR_OFFSETS = (1, 7, 13, 19)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    logging.Formatter.converter = time.gmtime

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Reuse traces already in the landing zone instead of fetching globe_history.",
    )
    args = parser.parse_args()

    day = args.date or default_history_day()
    settings = Settings(data_root=PIPELINE_ROOT.parent / "build", run_id="history")
    store = LocalRawStore(settings.raw_root)

    if not args.skip_download:
        written = collect_globe_history(store, day=day, user_agent=settings.user_agent)
        log.info("globe_history day=%s traces_kept=%d", day.isoformat(), len(written))
    else:
        partition = settings.raw_root / "raw" / "adsb_lol" / f"dt={day.isoformat()}"
        existing = list(partition.glob("*.json.gz"))
        if not existing:
            raise SystemExit(
                f"no traces in raw/adsb_lol/dt={day.isoformat()}/; omit --skip-download"
            )
        log.info("reusing %d existing traces for %s", len(existing), day.isoformat())

    starts = [
        datetime(day.year, day.month, day.day, hour, 0, tzinfo=UTC) for hour in AIS_HOUR_OFFSETS
    ]
    seed_ais_windows(
        settings,
        starts,
        window_s=AIS_WINDOW_S,
        origin=AIS_ORIGIN,
        spacing=AIS_SPACING,
        vessels=AIS_VESSELS,
        reports=AIS_REPORTS,
        interval_s=AIS_INTERVAL_S,
    )
    _write_health(settings, day)

    since = datetime(day.year, day.month, day.day, tzinfo=UTC)
    until = since + timedelta(days=1)
    transform(
        settings,
        project_dir=PIPELINE_ROOT / "transform",
        since=since,
        until=until,
        now=until,
    )
    manifest = bake(
        settings,
        now=until,
        window_start=since,
        window_end=until,
        require_observations=True,
    )
    log.info(
        "census air unique=%d fixes=%d segments=%d isolated=%d | "
        "sea unique=%d fixes=%d segments=%d isolated=%d | kind=%s window=%s..%s",
        manifest.census.air.unique_entities,
        manifest.census.air.position_fixes,
        manifest.census.air.track_segments,
        manifest.census.air.isolated_points,
        manifest.census.sea.unique_entities,
        manifest.census.sea.position_fixes,
        manifest.census.sea.track_segments,
        manifest.census.sea.isolated_points,
        manifest.observation_kind,
        manifest.available_from,
        manifest.available_until,
    )
    for layer in manifest.layers:
        log.info(
            "%-22s zoom %2d-%-2d features=%4d vertices=%6d %s",
            layer.id,
            layer.min_zoom,
            layer.max_zoom,
            layer.feature_count,
            layer.budget.path_vertices,
            layer.freshness,
        )
    return 0


def _write_health(settings: Settings, day: date) -> None:
    air = HealthReport(run_id=settings.run_id)
    air.record(
        source="adsb_lol",
        state="archive",
        detail=f"adsb.lol globe_history {day.isoformat()}, Philippine AOI only",
    )
    air.write(settings.health_path.with_name("health_adsb_lol.json"))
    sea = HealthReport(run_id=settings.run_id)
    sea.record(
        source="aisstream",
        state="fixture",
        objects_written=len(AIS_HOUR_OFFSETS),
        detail=(
            "No free historical AIS archive covers Philippine waters. These are schema-built "
            "fixture windows on the same calendar day, not observed voyages."
        ),
    )
    sea.write(settings.health_path.with_name("health_aisstream.json"))


if __name__ == "__main__":
    raise SystemExit(main())
