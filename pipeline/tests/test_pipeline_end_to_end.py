"""Collect through bake, on recorded data, with no network.

This is the test that would catch a stage boundary breaking: a suffix the transform cannot
read, a timestamp unit that puts every row outside the window, a sentinel row reaching the
browser. Each of those has a unit test too, but only the whole run proves they compose.
"""

from __future__ import annotations

import itertools
from datetime import timedelta
from pathlib import Path

import pyarrow as pa
import pytest

from nightfall.bake import BudgetExceededError, bake
from nightfall.bake.manifest import freshness
from nightfall.config import Settings
from nightfall.transform import transform
from tests.conftest import FIXTURE_AT, seed_ais_window, seed_window

PROJECT_DIR = Path(__file__).resolve().parents[1] / "transform"


@pytest.fixture
def baked(settings: Settings, adsb_document: dict[str, object]) -> Settings:
    """Both sources, through every stage.

    Seeding air and sea together is the point: the two staging models meet in
    `int_positions`, and a type or column mismatch between them is invisible to any test that
    exercises one source alone.
    """
    seed_window(settings, adsb_document, sweeps=6, interval_s=20.0)
    seed_ais_window(settings)
    transform(settings, project_dir=PROJECT_DIR, now=FIXTURE_AT + timedelta(minutes=5))
    return settings


def _read(path: Path) -> pa.Table:
    with pa.memory_map(str(path)) as source:
        return pa.ipc.open_file(source).read_all()


def test_a_sampling_window_becomes_tracks(baked: Settings) -> None:
    manifest = bake(baked, now=FIXTURE_AT + timedelta(minutes=10))
    tracks = next(layer for layer in manifest.layers if layer.kind == "tracks")
    assert tracks.feature_count > 0
    assert tracks.budget.path_vertices > tracks.feature_count  # every track is a path

    table = _read(baked.serving_dir / tracks.url)
    assert table.num_rows == tracks.feature_count
    offsets = table.column("path").combine_chunks().offsets.to_pylist()
    assert offsets[-1] == tracks.budget.path_vertices


def test_both_modes_reach_the_serving_set(baked: Settings) -> None:
    """Air and sea travel through one pipeline and one artifact, distinguished by `mode`.

    The two staging models meet in `int_positions`, so this is where a column they disagree
    about — a type, a name, a unit — stops being a silent loss of one source.
    """
    manifest = bake(baked, now=FIXTURE_AT + timedelta(minutes=10))
    tracks = next(layer for layer in manifest.layers if layer.kind == "tracks")
    table = _read(baked.serving_dir / tracks.url)
    assert set(table.column("mode").to_pylist()) == {"air", "sea"}
    assert set(table.column("source").to_pylist()) == {"adsb_lol", "aisstream"}
    # A vessel has a name from AIS metadata; losing it would strip every hover label at sea.
    labels = {
        label
        for label, mode in zip(
            table.column("label").to_pylist(), table.column("mode").to_pylist(), strict=True
        )
        if mode == "sea"
    }
    assert any(label and label.startswith("MV FIXTURE") for label in labels)


def test_static_ais_frames_do_not_become_positions(baked: Settings) -> None:
    """`ShipStaticData` carries no position; untyped it would moor a vessel at 0°N 0°E."""
    bake(baked, now=FIXTURE_AT + timedelta(minutes=10))
    import duckdb

    connection = duckdb.connect()
    connection.execute("SET TimeZone = 'UTC'")
    row = connection.execute(
        "select count(*) from read_parquet(?, hive_partitioning = true) "
        "where abs(lon) < 0.001 and abs(lat) < 0.001",
        [str(baked.curated_dir / "v1" / "positions" / "**" / "*.parquet")],
    ).fetchone()
    assert row is not None and row[0] == 0


def test_grounded_aircraft_survive_the_whole_pipeline(baked: Settings) -> None:
    """Aircraft on the surface arrive with `alt_baro` as the string "ground". A cast that
    failed here would drop every taxiing aircraft at exactly the airports the product cares
    about most."""
    bake(baked, now=FIXTURE_AT + timedelta(minutes=10))
    import duckdb

    connection = duckdb.connect()
    connection.execute("SET TimeZone = 'UTC'")
    grounded = connection.execute(
        "select count(*) from read_parquet(?, hive_partitioning = true) where on_ground",
        [str(baked.curated_dir / "v1" / "positions" / "**" / "*.parquet")],
    ).fetchone()
    assert grounded is not None and grounded[0] > 0


def test_coarser_zoom_tier_has_fewer_vertices(baked: Settings) -> None:
    manifest = bake(baked, now=FIXTURE_AT + timedelta(minutes=10))
    tiers = sorted(
        (layer for layer in manifest.layers if layer.kind == "tracks"),
        key=lambda layer: layer.min_zoom,
    )
    assert len(tiers) >= 2
    assert tiers[0].budget.path_vertices <= tiers[-1].budget.path_vertices


def test_zoom_tiers_cover_the_range_without_overlapping(baked: Settings) -> None:
    manifest = bake(baked, now=FIXTURE_AT + timedelta(minutes=10))
    tiers = sorted(
        (layer for layer in manifest.layers if layer.kind == "tracks"),
        key=lambda layer: layer.min_zoom,
    )
    for lower, upper in itertools.pairwise(tiers):
        assert lower.max_zoom + 1 == upper.min_zoom


def test_artifacts_are_content_hashed(baked: Settings) -> None:
    manifest = bake(baked, now=FIXTURE_AT + timedelta(minutes=10))
    for layer in manifest.layers:
        assert (baked.serving_dir / layer.url).is_file()
        # `name.<12 hex>.arrow`
        stem, digest, suffix = layer.url.rsplit(".", 2)
        assert suffix == "arrow"
        assert len(digest) == 12
        assert stem


def test_manifest_carries_provenance_and_attribution(baked: Settings) -> None:
    manifest = bake(baked, now=FIXTURE_AT + timedelta(minutes=10))
    assert manifest.run_id == "test-run"
    assert manifest.sampling_notice
    assert {attribution.source for attribution in manifest.attributions} == {
        "adsb_lol",
        "aisstream",
    }
    # Attribution is generated from the licence registry, so it cannot drift out of date.
    assert all(attribution.licence and attribution.url for attribution in manifest.attributions)


def test_a_build_with_no_observations_credits_nobody(baked: Settings) -> None:
    """Credits follow the data served, not the registry, so an empty build credits no one."""
    manifest = bake(baked, now=FIXTURE_AT + timedelta(days=2))
    assert manifest.attributions == []
    # The sources themselves are still listed, because their state is what explains the gap.
    assert {source.source for source in manifest.sources} == {"adsb_lol", "aisstream"}


def test_an_unconfigured_source_is_reported_not_hidden(baked: Settings) -> None:
    manifest = bake(baked, now=FIXTURE_AT + timedelta(minutes=10))
    states = {source.source: source.state for source in manifest.sources}
    assert states["aisstream"] == "not_configured"


def test_stale_data_is_labelled_rather_than_served_as_current(baked: Settings) -> None:
    manifest = bake(baked, now=FIXTURE_AT + timedelta(days=2))
    assert {layer.freshness for layer in manifest.layers} == {"absent"}


def test_freshness_states() -> None:
    assert freshness(None) == "absent"
    assert freshness(FIXTURE_AT, now=FIXTURE_AT + timedelta(minutes=30)) == "fresh"
    assert freshness(FIXTURE_AT, now=FIXTURE_AT + timedelta(hours=3)) == "late"
    assert freshness(FIXTURE_AT, now=FIXTURE_AT + timedelta(hours=12)) == "stale"


def test_a_cold_start_bakes_an_empty_serving_set(settings: Settings) -> None:
    """An empty landing zone is a valid state — the first run, or a failed collection — and
    must produce readable empty artifacts rather than a crash or a missing file."""
    transform(settings, project_dir=PROJECT_DIR, now=FIXTURE_AT)
    manifest = bake(settings, now=FIXTURE_AT)
    assert all(layer.feature_count == 0 for layer in manifest.layers)
    assert all(layer.freshness == "absent" for layer in manifest.layers)
    for layer in manifest.layers:
        assert _read(settings.serving_dir / layer.url).num_rows == 0


def test_the_empty_model_sentinel_never_reaches_the_browser(settings: Settings) -> None:
    """dbt-duckdb writes one all-null row so an empty Parquet file still has a schema. It must
    not be rendered as an observation with no position, no time, and no provenance."""
    transform(settings, project_dir=PROJECT_DIR, now=FIXTURE_AT)
    manifest = bake(settings, now=FIXTURE_AT)
    assert sum(layer.feature_count for layer in manifest.layers) == 0


def test_the_budget_fails_the_build(baked: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """The budget is a limit, not a target. Exceeding it must stop the build."""
    monkeypatch.setattr("nightfall.bake.MAX_PATH_VERTICES", 1)
    with pytest.raises(BudgetExceededError, match="budget"):
        bake(baked, now=FIXTURE_AT + timedelta(minutes=10))


def test_the_pages_ceiling_fails_the_build(
    baked: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("nightfall.bake.MAX_SERVING_BYTES", 1)
    with pytest.raises(BudgetExceededError, match="ceiling"):
        bake(baked, now=FIXTURE_AT + timedelta(minutes=10))


def test_reruns_do_not_accumulate_artifacts(baked: Settings) -> None:
    """Content-hashed names never collide, so a stale artifact would linger forever and count
    against the Pages ceiling."""
    bake(baked, now=FIXTURE_AT + timedelta(minutes=10))
    first = {path.name for path in baked.serving_dir.glob("*.arrow")}
    bake(baked, now=FIXTURE_AT + timedelta(minutes=11))
    assert {path.name for path in baked.serving_dir.glob("*.arrow")} == first
