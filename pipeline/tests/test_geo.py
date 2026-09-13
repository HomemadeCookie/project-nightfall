"""Geometry and the coverage tiling."""

from __future__ import annotations

import pytest

from nightfall.geo import (
    BASEMAP_BBOX,
    PH_AOI,
    VIEW_PAN_MARGIN_DEG,
    BoundingBox,
    coverage_circles,
    haversine_km,
)


def test_bounding_box_rejects_an_inverted_span() -> None:
    with pytest.raises(ValueError, match="longitude span"):
        BoundingBox(west=127.0, south=4.0, east=116.0, north=21.5)
    with pytest.raises(ValueError, match="latitude span"):
        BoundingBox(west=116.0, south=21.5, east=127.0, north=4.0)


def test_growing_a_box_clamps_to_valid_coordinates() -> None:
    """A margin must not produce a box that cannot exist.

    The basemap bbox is the AOI plus the map's pan margin, and a future AOI near a pole or the
    antimeridian would otherwise construct an invalid box — which `BoundingBox` rejects, so the
    failure would be an exception in the middle of a scheduled run rather than a clamp.
    """
    assert PH_AOI.grown(0.0) == PH_AOI
    polar = BoundingBox(west=-179.0, south=-89.0, east=179.0, north=89.0).grown(5.0)
    assert (polar.west, polar.south, polar.east, polar.north) == (-180.0, -90.0, 180.0, 90.0)


def test_the_basemap_covers_everywhere_the_map_can_be_panned() -> None:
    """The extract is cut to the pan limit, so a mismatch shows as a visible tile edge."""
    assert PH_AOI.grown(VIEW_PAN_MARGIN_DEG) == BASEMAP_BBOX
    assert BASEMAP_BBOX.west < PH_AOI.west
    assert BASEMAP_BBOX.north > PH_AOI.north


def test_haversine_against_a_known_distance() -> None:
    # Manila to Cebu, roughly 570 km great-circle.
    distance = haversine_km(120.98, 14.60, 123.89, 10.32)
    assert 560.0 < distance < 580.0


def test_coverage_circles_leave_no_gap() -> None:
    """The tiling must actually cover the AOI, not merely look like it does.

    A gap here would present as missing aircraft in a band of the archipelago, which is the
    failure mode hardest to notice and most damaging: absence of data rendered as absence of
    traffic.
    """
    radius_nm = 250.0
    circles = coverage_circles(PH_AOI, radius_nm)
    radius_km = radius_nm * 1.852

    steps = 60
    for row in range(steps + 1):
        lat = PH_AOI.south + (PH_AOI.north - PH_AOI.south) * row / steps
        for column in range(steps + 1):
            lon = PH_AOI.west + (PH_AOI.east - PH_AOI.west) * column / steps
            covered = any(
                haversine_km(lon, lat, circle.lon, circle.lat) <= radius_km for circle in circles
            )
            assert covered, f"({lon:.3f}, {lat:.3f}) is inside the AOI but outside every circle"


def test_coverage_circles_are_deterministic() -> None:
    """Request keys are derived from the circles, so unstable ordering would fragment the
    landing zone into paths that never dedupe."""
    assert coverage_circles(PH_AOI, 250.0) == coverage_circles(PH_AOI, 250.0)


def test_coverage_circles_reject_a_nonsense_radius() -> None:
    with pytest.raises(ValueError, match="radius must be positive"):
        coverage_circles(PH_AOI, 0.0)
