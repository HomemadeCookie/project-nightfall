"""Command line entry point.

Each subcommand is one pipeline stage and one GitHub Actions job. They share nothing at
runtime except the landing zone and the curated directory, which is what lets a failed
collector degrade freshness without breaking the deployment.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from pathlib import Path

from nightfall.bake import bake
from nightfall.clock import utc_now
from nightfall.config import Settings
from nightfall.health import HealthReport
from nightfall.sources import registry
from nightfall.sources.base import SourceOutageError
from nightfall.store import Archive, LocalRawStore
from nightfall.transform import DEFAULT_LOOKBACK_HOURS, partition_dates, transform

#: The dbt project lives beside the package rather than inside it, so it is located relative
#: to the repository rather than to the installed wheel.
DEFAULT_PROJECT_DIR = Path(__file__).resolve().parents[2] / "transform"

log = logging.getLogger("nightfall")


def collect(name: str, settings: Settings) -> int:
    """Run one collector.

    A source outage is reported and exits zero. The pipeline must degrade freshness, never
    fail the deployment (invariant 3), and a red cross on a scheduled job that simply found
    the sky quiet teaches everyone to ignore red crosses.
    """
    report = HealthReport(run_id=settings.run_id)
    adapter = registry.by_name(name)(LocalRawStore(settings.raw_root), settings)
    try:
        written = asyncio.run(adapter.run())
    except SourceOutageError as outage:
        report.record(source=name, state="outage", detail=str(outage))
        log.warning("source=%s state=outage detail=%s", name, outage)
    else:
        note = adapter.coverage_note()
        report.record(source=name, state="ok", objects_written=len(written), detail=note)
        log.info(
            "source=%s state=ok objects_written=%d coverage=%s",
            name,
            len(written),
            note or "complete",
        )
    report.write(settings.health_path.with_name(f"health_{name}.json"))
    return 0


def archive(settings: Settings) -> int:
    """Mirror this run's raw objects to the archive of record.

    Best effort by design. A failed upload must not fail the run: the objects are already on
    disk and the rest of the pipeline is a pure function of that directory, so the cost of an
    archive outage is a gap in history, not a broken deployment (invariant 3).
    """
    if settings.archive_repo is None:
        log.info("archive skipped: no repository configured")
        return 0
    token = settings.hf_token
    if token is None:
        log.warning("archive skipped: repository configured but no token available")
        return 0
    try:
        Archive(settings.archive_repo, token.get_secret_value()).upload(
            settings.raw_root, run_id=settings.run_id
        )
    except Exception:
        log.exception("archive upload failed; history will have a gap for run %s", settings.run_id)
        return 0
    log.info("archive updated repo=%s run_id=%s", settings.archive_repo, settings.run_id)
    return 0


def restore(settings: Settings, *, lookback_hours: int) -> int:
    """Fetch the raw partitions the transform is about to read.

    Also best effort: without it the run transforms only the window it collected itself, which
    is a shorter overlay rather than a failure.
    """
    if settings.archive_repo is None:
        log.info("restore skipped: no repository configured")
        return 0
    dates = partition_dates(utc_now(), lookback_hours=lookback_hours)
    try:
        Archive(
            settings.archive_repo,
            settings.hf_token.get_secret_value() if settings.hf_token else None,
        ).restore(settings.raw_root, dates=dates)
    except Exception:
        log.exception("restore failed; transforming only what this run collected")
        return 0
    log.info("restored partitions=%s", ",".join(dates))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nightfall", description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    collect_parser = subcommands.add_parser("collect", help="fetch one source into raw/")
    collect_parser.add_argument("source", choices=sorted(a.name for a in registry.ADAPTERS))

    transform_parser = subcommands.add_parser("transform", help="build the curated models")
    transform_parser.add_argument("--lookback-hours", type=int, default=DEFAULT_LOOKBACK_HOURS)
    transform_parser.add_argument("--project-dir", type=Path, default=DEFAULT_PROJECT_DIR)

    subcommands.add_parser("bake", help="produce the serving set")
    subcommands.add_parser("archive", help="mirror raw/ to the archive of record")

    restore_parser = subcommands.add_parser("restore", help="fetch raw/ from the archive")
    restore_parser.add_argument("--lookback-hours", type=int, default=DEFAULT_LOOKBACK_HOURS)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)sZ %(levelname)s %(name)s %(message)s",
    )
    logging.Formatter.converter = time.gmtime  # Invariant 6: UTC, including in the log.
    settings = Settings()

    if args.command == "collect":
        return collect(args.source, settings)
    if args.command == "archive":
        return archive(settings)
    if args.command == "restore":
        return restore(settings, lookback_hours=args.lookback_hours)
    if args.command == "transform":
        variables = transform(
            settings,
            project_dir=args.project_dir,
            lookback_hours=args.lookback_hours,
        )
        log.info(
            "transform complete adsb_partitions=%d ais_partitions=%d",
            len(variables["adsb_globs"]),  # type: ignore[arg-type]
            len(variables["ais_globs"]),  # type: ignore[arg-type]
        )
        return 0

    manifest = bake(settings)
    log.info(
        "bake complete layers=%d run_id=%s",
        len(manifest.layers),
        manifest.run_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
