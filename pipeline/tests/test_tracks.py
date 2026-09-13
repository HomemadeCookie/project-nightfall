"""Segmentation and simplification.

The rules under test are product rules, not implementation details: a segment may only span
time that was observed, and simplification may not change what is drawn.
"""

from __future__ import annotations

import pytest

from nightfall.bake.tracks import (
    MAX_TRACK_GAP_S,
    Fix,
    Track,
    build_tracks,
    douglas_peucker,
    segment,
    simplify,
    tolerance_degrees,
)


def _fixes(*offsets: float) -> list[Fix]:
    return [
        Fix(lon=121.0 + index * 0.01, lat=14.5, epoch_s=offset)
        for index, offset in enumerate(offsets)
    ]


def test_a_gap_ends_the_segment() -> None:
    """Consecutive observations minutes apart cannot be joined.

    Both sources are sampled in bounded windows, so a cross-window pair would otherwise draw a
    straight line through hundreds of kilometres nobody watched.
    """
    parts = segment(_fixes(0.0, 20.0, 40.0, 40.0 + MAX_TRACK_GAP_S + 1.0, 1000.0))
    assert [len(part) for part in parts] == [3, 1, 1]


def test_a_gap_exactly_at_the_threshold_is_kept() -> None:
    parts = segment(_fixes(0.0, MAX_TRACK_GAP_S))
    assert len(parts) == 1


def test_empty_input_yields_no_segments() -> None:
    assert segment([]) == []


def test_douglas_peucker_drops_collinear_points() -> None:
    straight = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]
    assert douglas_peucker(straight, 0.001) == [0, 3]


def test_douglas_peucker_keeps_a_real_corner() -> None:
    cornered = [(0.0, 0.0), (1.0, 0.0), (2.0, 5.0)]
    assert douglas_peucker(cornered, 0.001) == [0, 1, 2]


def test_douglas_peucker_returns_indices_not_points() -> None:
    """Indices, so per-vertex timestamps survive simplification without being re-derived."""
    kept = douglas_peucker([(0.0, 0.0), (1.0, 0.1), (2.0, 0.0)], 1.0)
    assert all(isinstance(index, int) for index in kept)


def test_a_doubling_back_track_is_measured_to_the_chord_end() -> None:
    """An unclamped projection onto the infinite line reads a reversal as closer than it is,
    and would flatten a holding pattern into a straight line."""
    out_and_back = [(0.0, 0.0), (5.0, 0.0), (0.0, 0.0)]
    assert 1 in douglas_peucker(out_and_back, 0.5)


def test_simplification_keeps_timestamps_aligned_with_vertices() -> None:
    track = Track(
        source="adsb_lol",
        mode="air",
        entity_id="abc123",
        label="PAL400",
        fixes=tuple(
            Fix(lon=121.0 + index * 0.5, lat=14.5, epoch_s=float(index)) for index in range(6)
        ),
    )
    reduced = simplify(track, zoom=9)
    assert len(reduced.fixes) < len(track.fixes)
    # Every surviving vertex keeps the time it was observed at, not an interpolated one.
    original = {(fix.lon, fix.lat): fix.epoch_s for fix in track.fixes}
    assert all(original[(fix.lon, fix.lat)] == fix.epoch_s for fix in reduced.fixes)
    assert reduced.fixes[0] == track.fixes[0]
    assert reduced.fixes[-1] == track.fixes[-1]


def test_tolerance_tightens_as_zoom_increases() -> None:
    assert tolerance_degrees(12, 14.5) < tolerance_degrees(9, 14.5)


def test_tolerance_is_latitude_corrected() -> None:
    assert tolerance_degrees(9, 60.0) == pytest.approx(tolerance_degrees(9, 0.0))


def test_build_tracks_separates_single_sightings() -> None:
    """One fix is a sighting, not a path, and must not be drawn as one."""
    rows = [
        ("adsb_lol", "air", "aaa", "ONE", 121.0, 14.5, 0.0),
        ("adsb_lol", "air", "aaa", None, 121.1, 14.5, 20.0),
        ("aisstream", "sea", "bbb", "SHIP", 120.0, 13.0, 5.0),
    ]
    tracks, singles = build_tracks(rows)
    assert [track.entity_id for track in tracks] == ["aaa"]
    assert [entity for _, _, entity, _, _ in singles] == ["bbb"]


def test_a_label_reported_once_is_kept() -> None:
    """Callsigns and vessel names arrive intermittently; an entity that gave one has one."""
    rows = [
        ("adsb_lol", "air", "aaa", None, 121.0, 14.5, 0.0),
        ("adsb_lol", "air", "aaa", "PAL400", 121.1, 14.5, 20.0),
    ]
    tracks, _ = build_tracks(rows)
    assert tracks[0].label == "PAL400"


def test_entities_are_not_merged() -> None:
    rows = [
        ("adsb_lol", "air", "aaa", None, 121.0, 14.5, 0.0),
        ("adsb_lol", "air", "aaa", None, 121.1, 14.5, 20.0),
        ("adsb_lol", "air", "bbb", None, 122.0, 15.5, 0.0),
        ("adsb_lol", "air", "bbb", None, 122.1, 15.5, 20.0),
    ]
    tracks, singles = build_tracks(rows)
    assert sorted(track.entity_id for track in tracks) == ["aaa", "bbb"]
    assert singles == []
