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
from nightfall.config import Settings
from nightfall.health import HealthReport
from nightfall.sources import registry
from nightfall.sources.base import SourceOutageError
from nightfall.store import LocalRawStore
from nightfall.transform import DEFAULT_LOOKBACK_HOURS, transform

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nightfall", description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    collect_parser = subcommands.add_parser("collect", help="fetch one source into raw/")
    collect_parser.add_argument("source", choices=sorted(a.name for a in registry.ADAPTERS))

    transform_parser = subcommands.add_parser("transform", help="build the curated models")
    transform_parser.add_argument("--lookback-hours", type=int, default=DEFAULT_LOOKBACK_HOURS)
    transform_parser.add_argument("--project-dir", type=Path, default=DEFAULT_PROJECT_DIR)

    subcommands.add_parser("bake", help="produce the serving set")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)sZ %(levelname)s %(name)s %(message)s",
    )
    logging.Formatter.converter = time.gmtime  # Invariant 6: UTC, including in the log.
    settings = Settings()

    if args.command == "collect":
        return collect(args.source, settings)
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
