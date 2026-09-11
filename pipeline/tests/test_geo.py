"""Geometry and the coverage tiling."""

from __future__ import annotations

import pytest

from nightfall.geo import (
    PH_AOI,
    BoundingBox,
    coverage_circles,
    haversine_km,
)


def test_bounding_box_rejects_an_inverted_span() -> None:
    with pytest.raises(ValueError, match="longitude span"):
        BoundingBox(west=127.0, south=4.0, east=116.0, north=21.5)
    with pytest.raises(ValueError, match="latitude span"):
        BoundingBox(west=116.0, south=21.5, east=127.0, north=4.0)


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
