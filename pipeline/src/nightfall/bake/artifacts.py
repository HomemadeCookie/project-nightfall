"""Arrow IPC artifacts, shaped so the browser never has to rebuild them.

Invariant 4 is binary end to end: nothing between here and the GPU may parse geometry. The
layouts below are chosen so that deck.gl's binary attribute form falls out of the Arrow
buffers directly.

A track's path is `list<fixed_size_list<double>[2]>`. Arrow stores that as one flat
`Float64Array` of interleaved lon/lat plus an offsets buffer counting *points*, which is
precisely deck.gl's `attributes.getPath.value` and `startIndices`. The worker hands both
straight to the layer with no copy and no loop.

Timestamps are `list<float32>` sharing the same offsets, seconds relative to the artifact's
epoch. Relative, because float32 cannot hold a Unix timestamp to better than about two
minutes — enough to make an animation stutter visibly while looking perfectly reasonable in
the data.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

import pyarrow as pa
from pyarrow import ipc

from nightfall.bake.tracks import Fix, Track

#: Arrow types, defined once so the reader and the writer cannot disagree.
POINT_TYPE = pa.list_(pa.float64(), 2)
PATH_TYPE = pa.list_(POINT_TYPE)
TIMESTAMPS_TYPE = pa.list_(pa.float32())

TRACKS_SCHEMA = pa.schema(
    [
        pa.field("source", pa.string(), nullable=False),
        pa.field("mode", pa.string(), nullable=False),
        pa.field("entity_id", pa.string(), nullable=False),
        pa.field("label", pa.string()),
        pa.field("path", PATH_TYPE, nullable=False),
        pa.field("timestamps", TIMESTAMPS_TYPE, nullable=False),
    ]
)

POINTS_SCHEMA = pa.schema(
    [
        pa.field("source", pa.string(), nullable=False),
        pa.field("mode", pa.string(), nullable=False),
        pa.field("entity_id", pa.string(), nullable=False),
        pa.field("label", pa.string()),
        pa.field("position", POINT_TYPE, nullable=False),
        pa.field("timestamp", pa.float32(), nullable=False),
    ]
)


def tracks_table(tracks: Sequence[Track], *, epoch_s: float) -> pa.Table:
    paths = [[[fix.lon, fix.lat] for fix in track.fixes] for track in tracks]
    stamps = [[fix.epoch_s - epoch_s for fix in track.fixes] for track in tracks]
    return pa.Table.from_arrays(
        [
            pa.array([track.source for track in tracks], pa.string()),
            pa.array([track.mode for track in tracks], pa.string()),
            pa.array([track.entity_id for track in tracks], pa.string()),
            pa.array([track.label for track in tracks], pa.string()),
            pa.array(paths, PATH_TYPE),
            pa.array(stamps, TIMESTAMPS_TYPE),
        ],
        schema=TRACKS_SCHEMA,
    )


def points_table(
    singles: Sequence[tuple[str, str, str, str | None, Fix]],
    *,
    epoch_s: float,
) -> pa.Table:
    return pa.Table.from_arrays(
        [
            pa.array([source for source, _, _, _, _ in singles], pa.string()),
            pa.array([mode for _, mode, _, _, _ in singles], pa.string()),
            pa.array([entity for _, _, entity, _, _ in singles], pa.string()),
            pa.array([label for _, _, _, label, _ in singles], pa.string()),
            pa.array([[fix.lon, fix.lat] for *_, fix in singles], POINT_TYPE),
            pa.array([fix.epoch_s - epoch_s for *_, fix in singles], pa.float32()),
        ],
        schema=POINTS_SCHEMA,
    )


def write_ipc(table: pa.Table, path: Path) -> int:
    """Write an uncompressed Arrow IPC file. Returns the byte size.

    Uncompressed on purpose: the Pages CDN already serves these gzipped over the wire, and an
    Arrow-level codec would force the worker to decompress into a second buffer, which is
    exactly the copy this format exists to avoid.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with pa.OSFile(str(path), "wb") as sink, ipc.new_file(sink, table.schema) as writer:
        writer.write_table(table)
    return path.stat().st_size


def content_hash(path: Path) -> str:
    """Short digest of a file's bytes, used to make artifact URLs immutable.

    Content-hashed names let the CDN cache an artifact forever and let a stale manifest be
    detected rather than silently served: a URL either exists with exactly these bytes or does
    not exist.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()[:12]


def rename_to_hashed(path: Path) -> Path:
    """Rename an artifact to include its content hash, returning the new path."""
    target = path.with_name(f"{path.stem}.{content_hash(path)}{path.suffix}")
    path.replace(target)
    return target


def count_vertices(tracks: Sequence[Track]) -> int:
    return sum(len(track.fixes) for track in tracks)
