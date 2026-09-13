"""Stage 5 — BAKE: curated GeoParquet in, serving set out.

This is the performance and budget boundary. Everything the browser will do is decided here:
which observations are in scope, how tracks are broken and simplified, and whether the result
fits the declared frame budget. Nothing downstream may recover from a mistake made here,
because there is nothing downstream — stage 6 is a directory of files.

The budget is a limit, not a target. When an artifact exceeds it the build fails; the fix is a
smaller artifact, never a larger budget (`.cursorrules` § 6).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

from nightfall.bake.artifacts import (
    count_vertices,
    points_table,
    rename_to_hashed,
    tracks_table,
    write_ipc,
)
from nightfall.bake.manifest import (
    FRESH_AFTER,
    Attribution,
    Budget,
    Layer,
    Manifest,
    SourceHealth,
    freshness,
)
from nightfall.bake.tracks import ZOOM_TIERS, Track, build_tracks, simplify
from nightfall.clock import from_unix, isoformat_z, require_utc, utc_now
from nightfall.config import SCHEMA_VERSION, Settings
from nightfall.geo import (
    DEFAULT_VIEW_LAT,
    DEFAULT_VIEW_LON,
    DEFAULT_VIEW_ZOOM,
    PH_AOI,
)
from nightfall.sources import registry

#: Frame budget (README § Risks, browser performance). Enforced, not aspirational.
MAX_PATH_VERTICES = 300_000
MAX_POINTS = 500_000

#: GitHub Pages refuses a site over 1 GB. Asserted with headroom so growth fails a pull
#: request rather than a deployment.
MAX_SERVING_BYTES = 900 * 1024 * 1024

#: How much of the recent past the overlay shows. Longer would mean more vertices for movement
#: nobody is looking at.
DEFAULT_WINDOW = timedelta(hours=6)

SAMPLING_NOTICE = (
    "Positions are sampled in short scheduled windows, not streamed. A line is drawn only "
    "between consecutive observations of the same aircraft or vessel; where observation "
    "lapsed the track is broken rather than joined. Absence of a track means absence of "
    "observation, which is not the same as absence of movement."
)

_POSITIONS_QUERY = """
select
    source,
    mode,
    entity_id,
    label,
    lon,
    lat,
    epoch(observed_at) as epoch_s
from read_parquet($pattern, hive_partitioning = true)
where entity_id is not null
    and observed_at >= $since
order by source, entity_id, observed_at
"""


def _connect() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    connection.execute("INSTALL spatial; LOAD spatial;")
    connection.execute("SET TimeZone = 'UTC';")
    return connection


def read_positions(
    curated_dir: Path,
    *,
    since: datetime,
) -> list[tuple[str, str, str, str | None, float, float, float]]:
    """Curated positions in the window, ordered for `build_tracks`.

    The `entity_id is not null` filter removes dbt-duckdb's empty-model sentinel row. On a
    cold start that row is the entire file, and without the filter it would reach the browser
    as an observation with no position, no time, and no provenance.
    """
    root = curated_dir / f"v{SCHEMA_VERSION}" / "positions"
    if not any(root.rglob("*.parquet")):
        return []
    pattern = str(root / "**" / "*.parquet")
    connection = _connect()
    try:
        return connection.execute(
            _POSITIONS_QUERY,
            {"pattern": pattern, "since": require_utc(since)},
        ).fetchall()
    finally:
        connection.close()


def _read_health(settings: Settings) -> list[SourceHealth]:
    """Collector outcomes, one file per collector, written by the collect jobs."""
    reports: list[SourceHealth] = []
    for path in sorted(settings.serving_dir.glob("health_*.json")):
        document = json.loads(path.read_text())
        for entry in document.get("sources", []):
            reports.append(
                SourceHealth(
                    source=entry["source"],
                    state=entry["state"],
                    observed_at=entry.get("observed_at"),
                    detail=entry.get("detail"),
                )
            )
    known = {report.source for report in reports}
    for adapter in registry.ADAPTERS:
        if adapter.name not in known:
            reports.append(SourceHealth(source=adapter.name, state="not_configured"))
    return sorted(reports, key=lambda report: report.source)


class BudgetExceededError(RuntimeError):
    """An artifact is larger than the frame budget allows."""


def bake(
    settings: Settings,
    *,
    window: timedelta = DEFAULT_WINDOW,
    now: datetime | None = None,
) -> Manifest:
    """Build the serving set and its manifest."""
    moment = require_utc(now) if now is not None else utc_now()
    since = moment - window
    rows = read_positions(settings.curated_dir, since=since)
    tracks, singles = build_tracks(rows)

    first_seen = [track.start_s for track in tracks] + [fix.epoch_s for *_, fix in singles]
    last_seen = [track.end_s for track in tracks] + [fix.epoch_s for *_, fix in singles]
    # With nothing collected, the epoch falls back to the window start so timestamps stay
    # meaningful, and `observed_at` stays absent so the UI reports no observation rather than
    # an observation of nothing.
    epoch_s = min(first_seen, default=since.timestamp())
    observed_at = from_unix(max(last_seen)) if last_seen else None

    settings.serving_dir.mkdir(parents=True, exist_ok=True)
    # Content-hashed names never collide, so a rerun would otherwise leave every previous
    # artifact behind and count it against the Pages ceiling.
    for stale in settings.serving_dir.glob("*.arrow"):
        stale.unlink()
    layers: list[Layer] = []

    for index, zoom in enumerate(ZOOM_TIERS):
        simplified = [simplify(track, zoom) for track in tracks]
        vertices = count_vertices(simplified)
        if vertices > MAX_PATH_VERTICES:
            raise BudgetExceededError(
                f"tracks at zoom {zoom} hold {vertices} vertices, over the "
                f"{MAX_PATH_VERTICES} budget. Shorten the window or coarsen the tier; "
                "raising the budget is not the fix."
            )
        path = write_tier(settings, simplified, zoom=zoom, epoch_s=epoch_s)
        layers.append(
            Layer(
                id=f"mobility-tracks-z{zoom}",
                kind="tracks",
                url=path.name,
                schema_version=SCHEMA_VERSION,
                min_zoom=zoom,
                max_zoom=ZOOM_TIERS[index + 1] - 1 if index + 1 < len(ZOOM_TIERS) else 24,
                epoch=isoformat_z(from_unix(epoch_s)),
                observed_from=isoformat_z(since),
                observed_at=isoformat_z(observed_at) if observed_at else None,
                freshness=freshness(observed_at, now=moment),
                feature_count=len(simplified),
                budget=Budget(
                    path_vertices=vertices,
                    path_vertex_limit=MAX_PATH_VERTICES,
                    points=0,
                    point_limit=MAX_POINTS,
                    bytes=path.stat().st_size,
                ),
            )
        )

    if len(singles) > MAX_POINTS:
        raise BudgetExceededError(
            f"{len(singles)} isolated observations exceed the {MAX_POINTS} point budget"
        )
    staged_points = settings.serving_dir / "mobility_points.arrow"
    write_ipc(points_table(singles, epoch_s=epoch_s), staged_points)
    points_path = rename_to_hashed(staged_points)
    layers.append(
        Layer(
            id="mobility-points",
            kind="points",
            url=points_path.name,
            schema_version=SCHEMA_VERSION,
            min_zoom=0,
            max_zoom=24,
            epoch=isoformat_z(from_unix(epoch_s)),
            observed_from=isoformat_z(since),
            observed_at=isoformat_z(observed_at) if observed_at else None,
            freshness=freshness(observed_at, now=moment),
            feature_count=len(singles),
            budget=Budget(
                path_vertices=0,
                path_vertex_limit=MAX_PATH_VERTICES,
                points=len(singles),
                point_limit=MAX_POINTS,
                bytes=points_path.stat().st_size,
            ),
        )
    )

    manifest = Manifest(
        schema_version=SCHEMA_VERSION,
        run_id=settings.run_id,
        generated_at=isoformat_z(moment),
        bounds=(PH_AOI.west, PH_AOI.south, PH_AOI.east, PH_AOI.north),
        initial_view={
            "longitude": DEFAULT_VIEW_LON,
            "latitude": DEFAULT_VIEW_LAT,
            "zoom": DEFAULT_VIEW_ZOOM,
        },
        layers=layers,
        # Credit only what this build actually serves; see `registry.attributions`.
        attributions=[
            Attribution(**entry) for entry in registry.attributions({row[0] for row in rows})
        ],
        sources=_read_health(settings),
        sampling_notice=SAMPLING_NOTICE,
    )
    assert_serving_size(settings.serving_dir)
    settings.manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n")
    return manifest


def write_tier(
    settings: Settings,
    tracks: Sequence[Track],
    *,
    zoom: int,
    epoch_s: float,
) -> Path:
    staged = settings.serving_dir / f"mobility_tracks_z{zoom}.arrow"
    write_ipc(tracks_table(tracks, epoch_s=epoch_s), staged)
    return rename_to_hashed(staged)


def assert_serving_size(serving_dir: Path) -> int:
    """Fail the build before the serving set can exceed the Pages ceiling."""
    total = sum(path.stat().st_size for path in serving_dir.rglob("*") if path.is_file())
    if total > MAX_SERVING_BYTES:
        raise BudgetExceededError(
            f"serving set is {total} bytes, over the {MAX_SERVING_BYTES} ceiling. "
            "Growth belongs in the Hugging Face archive, not against the Pages limit."
        )
    return total


__all__ = ["FRESH_AFTER", "BudgetExceededError", "Manifest", "bake"]
