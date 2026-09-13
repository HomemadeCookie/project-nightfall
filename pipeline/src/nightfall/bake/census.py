"""Inventory of a baked mobility window.

These figures are counts of the curated observations that reached the bake, not insights with
an error bound. They are still published numbers (invariant 7): each one is recomputable from
the same GeoParquet plus the same segmentation rules, and the UI must not invent a different
tally.
"""

from __future__ import annotations

from collections.abc import Sequence

from nightfall.bake.tracks import Fix, Track


class ModeCensus(dict[str, int]):
    """A tiny mapping so callers can both attribute-access and serialise."""

    @property
    def unique_entities(self) -> int:
        return self["unique_entities"]

    @property
    def position_fixes(self) -> int:
        return self["position_fixes"]

    @property
    def track_segments(self) -> int:
        return self["track_segments"]

    @property
    def isolated_points(self) -> int:
        return self["isolated_points"]


def count_mode(
    *,
    entity_ids: set[str],
    fixes: int,
    segments: int,
    isolated: int,
) -> dict[str, int]:
    return {
        "unique_entities": len(entity_ids),
        "position_fixes": fixes,
        "track_segments": segments,
        "isolated_points": isolated,
    }


def census(
    rows: Sequence[tuple[str, str, str, str | None, float, float, float]],
    tracks: Sequence[Track],
    singles: Sequence[tuple[str, str, str, str | None, Fix]],
) -> dict[str, dict[str, int]]:
    """Per-mode inventory of the window about to be baked.

    `position_fixes` counts curated observations (what was seen). `track_segments` and
    `isolated_points` count what segmentation made of them, before zoom simplification.
    """
    entities: dict[str, set[str]] = {"air": set(), "sea": set()}
    fixes = {"air": 0, "sea": 0}
    for _source, mode, entity_id, _label, _lon, _lat, _epoch in rows:
        entities.setdefault(mode, set()).add(entity_id)
        fixes[mode] = fixes.get(mode, 0) + 1
    segments = {"air": 0, "sea": 0}
    for track in tracks:
        segments[track.mode] = segments.get(track.mode, 0) + 1
    isolated = {"air": 0, "sea": 0}
    for _source, mode, _entity, _label, _fix in singles:
        isolated[mode] = isolated.get(mode, 0) + 1
    return {
        "air": count_mode(
            entity_ids=entities.get("air", set()),
            fixes=fixes.get("air", 0),
            segments=segments.get("air", 0),
            isolated=isolated.get("air", 0),
        ),
        "sea": count_mode(
            entity_ids=entities.get("sea", set()),
            fixes=fixes.get("sea", 0),
            segments=segments.get("sea", 0),
            isolated=isolated.get("sea", 0),
        ),
    }
