"""The Arrow layout is a contract with the browser, so it is pinned here.

The worker hands Arrow's own buffers straight to deck.gl: the child values buffer becomes
`attributes.getPath.value` and the list offsets become `startIndices`. If the layout drifts —
say the path column stops being a fixed-size list of two doubles — nothing raises, the offsets
silently mean something else, and the map draws confident nonsense.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa

from nightfall.bake.artifacts import (
    POINTS_SCHEMA,
    TRACKS_SCHEMA,
    content_hash,
    points_table,
    rename_to_hashed,
    tracks_table,
    write_ipc,
)
from nightfall.bake.tracks import Fix, Track

EPOCH_S = 1_789_147_749.0


def _track(entity_id: str, count: int) -> Track:
    return Track(
        source="adsb_lol",
        mode="air",
        entity_id=entity_id,
        label="PAL400",
        fixes=tuple(
            Fix(lon=121.0 + index * 0.1, lat=14.5, epoch_s=EPOCH_S + index * 20.0)
            for index in range(count)
        ),
    )


def test_path_is_a_list_of_two_element_double_points() -> None:
    table = tracks_table([_track("aaa", 3)], epoch_s=EPOCH_S)
    assert table.schema == TRACKS_SCHEMA
    path_type = table.schema.field("path").type
    assert pa.types.is_list(path_type)
    assert pa.types.is_fixed_size_list(path_type.value_type)
    assert path_type.value_type.list_size == 2
    assert pa.types.is_float64(path_type.value_type.value_type)


def test_offsets_count_points_not_coordinates() -> None:
    """deck.gl's `startIndices` are vertex indices. A flat list of interleaved doubles would
    make the offsets count coordinates and halve every path."""
    table = tracks_table([_track("aaa", 3), _track("bbb", 5)], epoch_s=EPOCH_S)
    column = table.column("path").combine_chunks()
    offsets = column.offsets.to_pylist()
    assert offsets == [0, 3, 8]

    flat = column.values.flatten()
    assert len(flat) == 2 * 8


def test_timestamps_share_the_path_offsets() -> None:
    """One offsets buffer serves both attributes, so a per-vertex timestamp is guaranteed to
    line up with the vertex it belongs to."""
    table = tracks_table([_track("aaa", 3), _track("bbb", 5)], epoch_s=EPOCH_S)
    paths = table.column("path").combine_chunks()
    stamps = table.column("timestamps").combine_chunks()
    assert paths.offsets.to_pylist() == stamps.offsets.to_pylist()


def test_timestamps_are_relative_to_the_epoch() -> None:
    """float32 cannot hold a Unix timestamp to better than about two minutes, which would make
    an animation stutter while the data looked perfectly reasonable."""
    table = tracks_table([_track("aaa", 3)], epoch_s=EPOCH_S)
    stamps = table.column("timestamps").combine_chunks().values.to_pylist()
    assert stamps == [0.0, 20.0, 40.0]


def test_points_table_layout() -> None:
    singles = [("aisstream", "sea", "368207620", "EXAMPLE", Fix(120.98, 14.58, EPOCH_S + 5.0))]
    table = points_table(singles, epoch_s=EPOCH_S)
    assert table.schema == POINTS_SCHEMA
    assert table.column("position").combine_chunks().flatten().to_pylist() == [120.98, 14.58]
    assert table.column("timestamp").to_pylist() == [5.0]


def test_empty_tables_are_valid(tmp_path: Path) -> None:
    """A quiet window must produce a readable, empty artifact rather than a missing file: the
    UI distinguishes "no observations" from "no data", and a 404 is neither."""
    size = write_ipc(tracks_table([], epoch_s=EPOCH_S), tmp_path / "empty.arrow")
    assert size > 0
    with pa.memory_map(str(tmp_path / "empty.arrow")) as source:
        assert pa.ipc.open_file(source).read_all().num_rows == 0


def test_round_trip_through_ipc(tmp_path: Path) -> None:
    table = tracks_table([_track("aaa", 4)], epoch_s=EPOCH_S)
    write_ipc(table, tmp_path / "t.arrow")
    with pa.memory_map(str(tmp_path / "t.arrow")) as source:
        assert pa.ipc.open_file(source).read_all().equals(table)


def test_content_hash_is_stable_and_in_the_name(tmp_path: Path) -> None:
    path = tmp_path / "a.arrow"
    path.write_bytes(b"identical")
    digest = content_hash(path)
    renamed = rename_to_hashed(path)
    assert digest in renamed.name
    assert renamed.suffix == ".arrow"

    other = tmp_path / "b.arrow"
    other.write_bytes(b"identical")
    assert content_hash(other) == digest
