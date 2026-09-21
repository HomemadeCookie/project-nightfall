"""Turn observed positions into render-ready track segments.

Two rules govern everything here.

The first is that a segment may only span time we actually observed. Both sources are sampled
in bounded windows, so consecutive fixes of the same aircraft or vessel can be minutes apart
across a window boundary. Joining those would draw a line through hundreds of kilometres
nobody watched, which is interpolation across a coverage gap. A gap longer than
`MAX_TRACK_GAP_S` therefore ends the segment; the break is left as a break and the UI says so.

The second is the frame budget. Simplification happens here, once, at a tolerance derived from
the zoom the artifact will be drawn at — never in the browser (`.cursorrules` § 6).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

#: Longest gap between consecutive fixes that may still be joined. Both collectors sweep every
#: twenty seconds inside their window, so this is three consecutive missed observations: long
#: enough to ride out a dropped frame, short enough that the straight line between the two
#: fixes stays a fair account of the path taken.
MAX_TRACK_GAP_S = 90.0

#: A segment needs at least this many vertices to be a path rather than a point.
MIN_SEGMENT_POINTS = 2

#: Web Mercator ground resolution at zoom 0 in metres per pixel at the equator.
EQUATOR_METRES_PER_PIXEL_Z0 = 156_543.033_928_041

#: Simplification tolerance in screen pixels. One pixel is the point at which removing a vertex
#: cannot change what is drawn.
TOLERANCE_PX = 1.0

#: Zoom tiers the tracks are baked for. Individual tracks are only shown at zoom 9 and above
#: (`.cursorrules` § 6), so the coarser tier is the one that governs the budget.
ZOOM_TIERS = (9, 12)


@dataclass(frozen=True, slots=True)
class Fix:
    """One observed position of one entity."""

    lon: float
    lat: float
    epoch_s: float


@dataclass(frozen=True, slots=True)
class Track:
    """A contiguous run of observations of one entity, with no unobserved gap inside it."""

    source: str
    mode: str
    entity_id: str
    label: str | None
    fixes: tuple[Fix, ...]

    @property
    def start_s(self) -> float:
        return self.fixes[0].epoch_s

    @property
    def end_s(self) -> float:
        return self.fixes[-1].epoch_s


def tolerance_degrees(zoom: int, latitude: float) -> float:
    """`TOLERANCE_PX` at `zoom`, expressed in degrees of longitude at `latitude`.

    Simplification runs on lon/lat because that is how the fixes are stored, but the tolerance
    has to mean the same thing on screen everywhere, and a degree of longitude shrinks towards
    the poles. Over the Philippines the correction is small; doing it anyway keeps the
    tolerance honest if the AOI ever moves.
    """
    metres_per_pixel = EQUATOR_METRES_PER_PIXEL_Z0 * math.cos(math.radians(latitude)) / 2.0**zoom
    metres_per_degree_lon = 111_319.490_793 * math.cos(math.radians(latitude))
    return TOLERANCE_PX * metres_per_pixel / metres_per_degree_lon


def segment(
    fixes: Sequence[Fix],
    *,
    max_gap_s: float = MAX_TRACK_GAP_S,
) -> list[tuple[Fix, ...]]:
    """Split a time-ordered run of fixes wherever observation lapsed."""
    if not fixes:
        return []
    segments: list[tuple[Fix, ...]] = []
    current: list[Fix] = [fixes[0]]
    for previous, fix in itertools.pairwise(fixes):
        if fix.epoch_s - previous.epoch_s > max_gap_s:
            segments.append(tuple(current))
            current = [fix]
        else:
            current.append(fix)
    segments.append(tuple(current))
    return segments


def douglas_peucker(points: Sequence[tuple[float, float]], tolerance: float) -> list[int]:
    """Indices of the points to keep. Iterative, so a long track cannot blow the stack.

    Returns indices rather than points so a caller can carry per-vertex attributes —
    timestamps, here — through the simplification without re-deriving them.
    """
    if len(points) <= MIN_SEGMENT_POINTS:
        return list(range(len(points)))

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        furthest, greatest = first, -1.0
        for index in range(first + 1, last):
            distance = _perpendicular_distance(points[index], points[first], points[last])
            if distance > greatest:
                furthest, greatest = index, distance
        if greatest > tolerance:
            keep[furthest] = True
            stack.append((first, furthest))
            stack.append((furthest, last))
    return [index for index, kept in enumerate(keep) if kept]


def _perpendicular_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """Distance from `point` to the segment `start`-`end`, in the units of the inputs."""
    (px, py), (ax, ay), (bx, by) = point, start, end
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    # Clamped projection: a fix beyond either end of the chord is measured to that end, not to
    # the infinite line, otherwise a doubling-back track reads as closer than it is.
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def thin_fixes(fixes: Sequence[Fix], min_interval_s: float) -> tuple[Fix, ...]:
    """Keep observed endpoints and any fix at least `min_interval_s` after the last kept one.

    Dropping intermediate observations is not interpolation: every surviving vertex was
    measured. Used when a day's traces would otherwise breach the frame budget. The first and
    last fix always remain, so a thinned track still spans the time we actually watched.
    """
    if min_interval_s <= 0.0 or len(fixes) <= MIN_SEGMENT_POINTS:
        return tuple(fixes)
    kept: list[Fix] = [fixes[0]]
    last = fixes[-1]
    for fix in fixes[1:-1]:
        if fix.epoch_s - kept[-1].epoch_s >= min_interval_s:
            kept.append(fix)
    if kept[-1] is not last:
        kept.append(last)
    return tuple(kept)


def thin_tracks(tracks: Sequence[Track], min_interval_s: float) -> list[Track]:
    """Apply `thin_fixes` to every track, preserving identity and source."""
    return [
        Track(
            source=track.source,
            mode=track.mode,
            entity_id=track.entity_id,
            label=track.label,
            fixes=thin_fixes(track.fixes, min_interval_s),
        )
        for track in tracks
    ]


def simplify(track: Track, zoom: int) -> Track:
    """Drop vertices that cannot change what is drawn at `zoom`."""
    if len(track.fixes) <= MIN_SEGMENT_POINTS:
        return track
    latitude = sum(fix.lat for fix in track.fixes) / len(track.fixes)
    tolerance = tolerance_degrees(zoom, latitude)
    kept = douglas_peucker([(fix.lon, fix.lat) for fix in track.fixes], tolerance)
    return Track(
        source=track.source,
        mode=track.mode,
        entity_id=track.entity_id,
        label=track.label,
        fixes=tuple(track.fixes[index] for index in kept),
    )


def build_tracks(
    rows: Iterable[tuple[str, str, str, str | None, float, float, float]],
    *,
    max_gap_s: float = MAX_TRACK_GAP_S,
) -> tuple[list[Track], list[tuple[str, str, str, str | None, Fix]]]:
    """Group observations into tracks and isolated fixes.

    `rows` must arrive ordered by (source, entity_id, observed_at) as
    (source, mode, entity_id, label, lon, lat, epoch_s) — the curated store is written in that
    order, so no sort happens here.

    Returns the multi-point tracks and, separately, the observations that stand alone. A
    single fix is not a path and must not be drawn as one; it is a sighting, and the points
    layer renders it as exactly that.
    """
    tracks: list[Track] = []
    singles: list[tuple[str, str, str, str | None, Fix]] = []
    for source, mode, entity_id, label, fixes in _grouped(rows):
        for part in segment(fixes, max_gap_s=max_gap_s):
            if len(part) < MIN_SEGMENT_POINTS:
                singles.append((source, mode, entity_id, label, part[0]))
            else:
                tracks.append(
                    Track(
                        source=source,
                        mode=mode,
                        entity_id=entity_id,
                        label=label,
                        fixes=part,
                    )
                )
    return tracks, singles


def _grouped(
    rows: Iterable[tuple[str, str, str, str | None, float, float, float]],
) -> Iterator[tuple[str, str, str, str | None, list[Fix]]]:
    key: tuple[str, str] | None = None
    mode = ""
    label: str | None = None
    fixes: list[Fix] = []
    for source, row_mode, entity_id, row_label, lon, lat, epoch_s in rows:
        if key != (source, entity_id):
            if key is not None:
                yield key[0], mode, key[1], label, fixes
            key, mode, label, fixes = (source, entity_id), row_mode, row_label, []
        # The most recent non-empty label wins: callsigns and vessel names arrive
        # intermittently, and an entity that reported one at any point in the window has one.
        label = row_label or label
        fixes.append(Fix(lon=lon, lat=lat, epoch_s=epoch_s))
    if key is not None:
        yield key[0], mode, key[1], label, fixes
