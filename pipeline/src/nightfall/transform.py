"""Stage 2 — STORE: drive the dbt-duckdb models over the landing zone.

Python's job here is to decide *which* raw objects the run should read and to hand dbt the
numbers that must not be duplicated between Python and SQL. All transformation logic is SQL
models under `transform/` (`.cursorrules` § 4); nothing in this module transforms anything.

The lookback window exists because the landing zone grows without bound while the overlay only
ever shows recent movement. Rebuilding from the whole archive would still be correct — every
stage is a pure function of `raw/` plus pinned code — but it would get slower every day for no
gain. History lives in the Hugging Face archive and is rebuilt on demand, not on every run.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from nightfall.clock import require_utc, utc_now
from nightfall.config import SCHEMA_VERSION, Settings
from nightfall.geo import COVERAGE_H3_RESOLUTION, PH_AOI
from nightfall.store import SUFFIX_BY_CONTENT_TYPE

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Default span of landing-zone history each transform reads.
DEFAULT_LOOKBACK_HOURS = 48

#: H3 resolution used to partition curated Parquet. Coarse on purpose: partitioning at the
#: coverage resolution would scatter one run across thousands of sub-megabyte files, costing
#: more in HTTP round trips and Pages file count than it saves in bytes scanned.
PARTITION_H3_RESOLUTION = 3

#: Aggregation bucket for coverage. Must be a DuckDB interval literal.
TIME_BUCKET = "1 hour"

#: Ceiling on how far back one adsb.lol response is credited with having observed. The real
#: horizon is measured per response from the oldest fix it reported, because the provider
#: documents none; this only stops an anomalous response from claiming an implausible span.
ADSB_SNAPSHOT_HORIZON_MAX_S = 60.0

#: adsb.lol reports the response instant in milliseconds while per-aircraft ages in the same
#: document are in seconds. Kept beside the SQL that divides by it.
ADSB_NOW_UNITS_PER_SECOND = 1000.0

#: Wire format of each source's stored objects, which decides the glob suffix.
CONTENT_TYPE_BY_SOURCE = {
    "adsb_lol": "application/json",
    "aisstream": "application/x-ndjson",
}


def _partition_dates(since: datetime, until: datetime) -> Iterator[str]:
    """Every `dt=` partition name the window touches, inclusive of both ends."""
    day = require_utc(since).date()
    last = require_utc(until).date()
    while day <= last:
        yield day.isoformat()
        day += timedelta(days=1)


def raw_globs(
    raw_root: Path,
    source: str,
    *,
    since: datetime,
    until: datetime,
) -> list[str]:
    """Globs for the partitions that exist in the window.

    Only existing directories are returned. DuckDB raises on a glob that matches nothing, so
    handing it a partition that was never collected would turn a quiet night into a failed
    pipeline run.
    """
    suffix = SUFFIX_BY_CONTENT_TYPE[CONTENT_TYPE_BY_SOURCE[source]]
    globs = []
    for date in _partition_dates(since, until):
        directory = raw_root / "raw" / source / f"dt={date}"
        if directory.is_dir() and any(directory.glob(f"*{suffix}")):
            globs.append(str(directory / f"*{suffix}"))
    return globs


def dbt_vars(
    settings: Settings,
    *,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    now: datetime | None = None,
) -> dict[str, object]:
    """The full variable set for a transform run.

    Every value that appears in both Python and SQL is defined once, here. The defaults in
    `dbt_project.yml` exist so the project is runnable by hand; this is what production uses.
    """
    until = require_utc(now) if now is not None else utc_now()
    since = until - timedelta(hours=lookback_hours)
    # Absolute: dbt resolves relative paths against its own working directory, which is not
    # necessarily the one the job was launched from.
    root = settings.raw_root.resolve()
    return {
        "raw_root": str(root),
        "curated_root": str(settings.curated_dir.resolve()),
        "schema_version": SCHEMA_VERSION,
        "run_id": settings.run_id,
        "adsb_globs": raw_globs(root, "adsb_lol", since=since, until=until),
        "ais_globs": raw_globs(root, "aisstream", since=since, until=until),
        "aoi_west": PH_AOI.west,
        "aoi_south": PH_AOI.south,
        "aoi_east": PH_AOI.east,
        "aoi_north": PH_AOI.north,
        "coverage_h3_resolution": COVERAGE_H3_RESOLUTION,
        "partition_h3_resolution": PARTITION_H3_RESOLUTION,
        "time_bucket": TIME_BUCKET,
        "adsb_snapshot_horizon_max_s": ADSB_SNAPSHOT_HORIZON_MAX_S,
        "ais_window_s": settings.ais_window_s,
        "adsb_now_units_per_second": ADSB_NOW_UNITS_PER_SECOND,
    }


class TransformFailed(RuntimeError):
    """dbt returned a failure. Raised rather than logged so the job exits non-zero."""


def run_dbt(
    command: Sequence[str],
    *,
    project_dir: Path,
    variables: Mapping[str, object] | None = None,
) -> None:
    """Invoke dbt in-process.

    In-process rather than as a subprocess because dbt then reports failures as structured
    results instead of a parsed exit code, and because there is no second interpreter to keep
    in sync with the locked environment.
    """
    import json

    from dbt.cli.main import dbtRunner

    args = [
        *command,
        "--project-dir",
        str(project_dir),
        "--profiles-dir",
        str(project_dir),
    ]
    if variables:
        args += ["--vars", json.dumps(variables, default=str)]

    result = dbtRunner().invoke(list(args))
    if not result.success:
        detail = str(result.exception) if result.exception else "see dbt output above"
        raise TransformFailed(f"dbt {' '.join(command)} failed: {detail}")


def transform(
    settings: Settings,
    *,
    project_dir: Path,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    now: datetime | None = None,
) -> dict[str, object]:
    """Build the curated models, then test them. Returns the variables used, for the log."""
    variables = dbt_vars(settings, lookback_hours=lookback_hours, now=now)
    # DuckDB's COPY will not create intermediate directories, so the versioned root has to
    # exist before dbt writes into it.
    Path(str(variables["curated_root"]), f"v{SCHEMA_VERSION}").mkdir(parents=True, exist_ok=True)
    run_dbt(["build"], project_dir=project_dir, variables=variables)
    return variables
