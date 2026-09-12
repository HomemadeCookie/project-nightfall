"""Geometry helpers and the Philippine area of interest.

Invariant 5: coordinates are stored and interchanged in EPSG:4326, display uses EPSG:3857,
and anything area-normalized goes through H3. Nothing here computes an area in degrees.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0088
NM_TO_KM = 1.852

#: H3 resolution for mobility coverage aggregation. Res 6 averages ~36 km^2 per cell, which
#: is fine enough to distinguish a port approach from open water and coarse enough that a
#: sampled feed still puts several observations in a populated cell.
COVERAGE_H3_RESOLUTION = 6


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """An EPSG:4326 bounding box. Degrees, west/south/east/north."""

    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        if not -180.0 <= self.west < self.east <= 180.0:
            raise ValueError(f"invalid longitude span: {self.west}..{self.east}")
        if not -90.0 <= self.south < self.north <= 90.0:
            raise ValueError(f"invalid latitude span: {self.south}..{self.north}")

    def contains(self, lon: float, lat: float) -> bool:
        return self.west <= lon <= self.east and self.south <= lat <= self.north

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.west + self.east) / 2.0, (self.south + self.north) / 2.0)

    def grown(self, degrees: float) -> BoundingBox:
        """The same box with a margin on every side, clamped to valid coordinates."""
        return BoundingBox(
            west=max(-180.0, self.west - degrees),
            south=max(-90.0, self.south - degrees),
            east=min(180.0, self.east + degrees),
            north=min(90.0, self.north + degrees),
        )


#: The Philippine Area of Responsibility, trimmed to the landmass and its shipping approaches.
#: Deliberately wider than the archipelago so that vessels and aircraft are captured before
#: they arrive, which is what makes an approach visible rather than a sudden appearance.
PH_AOI = BoundingBox(west=116.0, south=4.0, east=127.0, north=21.5)

#: Default map view: Manila Bay and the Batangas corridor, the densest convergence of port,
#: air, and population activity in the country.
#:
#: The zoom is not a framing preference. Individual tracks are drawn from zoom 9 up, and area
#: aggregates — the right representation below that — arrive in a later phase, so opening any
#: wider would present an empty map as the product's first impression and make an absence of
#: rendering indistinguishable from an absence of traffic.
DEFAULT_VIEW_LON = 120.98
DEFAULT_VIEW_LAT = 14.58
DEFAULT_VIEW_ZOOM = 9.0

#: How far outside the area of interest the map lets you pan. The app applies the same margin
#: to the manifest's bounds; the two must agree, because the basemap is cut to this box and
#: panning further would reach the edge of the tiles.
VIEW_PAN_MARGIN_DEG = 2.0

#: The basemap extract. Cut to exactly what the map can be panned to — no further, since every
#: tile is transfer someone else pays for, and no less, since the edge would be visible.
BASEMAP_BBOX = PH_AOI.grown(VIEW_PAN_MARGIN_DEG)

#: Zoom ceiling for the basemap. The overlay draws individual tracks from zoom 9, and at zoom
#: 10 the basemap is already a legible coastline-and-roads reference. Carrying it to 14 would
#: multiply the extract by more than an order of magnitude for detail this product never asks a
#: question about; MapLibre scales vector geometry past the ceiling, so zooming in stays sharp.
BASEMAP_MAX_ZOOM = 10


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


@dataclass(frozen=True, slots=True)
class Circle:
    """A query circle. adsb.lol takes a centre and a radius, not a bounding box."""

    lon: float
    lat: float
    radius_nm: float

    @property
    def radius_km(self) -> float:
        return self.radius_nm * NM_TO_KM


def coverage_circles(aoi: BoundingBox, radius_nm: float) -> tuple[Circle, ...]:
    """Tile `aoi` with the fewest circles of `radius_nm` that still cover it completely.

    Centres are spaced at radius * sqrt(2), the widest spacing at which a square grid of
    circles leaves no gap at the cell corners. Longitude spacing is computed at the latitude
    where meridians are closest together within the box, so the grid stays gap-free at the
    poleward edge instead of only at the centre.

    Deterministic: the same AOI and radius always produce the same circles in the same order,
    which keeps the request keys in the landing zone stable across runs.
    """
    if radius_nm <= 0:
        raise ValueError("radius must be positive")

    spacing_km = radius_nm * NM_TO_KM * math.sqrt(2.0)
    lat_step = math.degrees(spacing_km / EARTH_RADIUS_KM)

    worst_lat = max(abs(aoi.south), abs(aoi.north))
    lon_km_per_degree = math.cos(math.radians(worst_lat)) * math.pi * EARTH_RADIUS_KM / 180.0
    lon_step = spacing_km / lon_km_per_degree

    circles: list[Circle] = []
    rows = max(1, math.ceil((aoi.north - aoi.south) / lat_step))
    cols = max(1, math.ceil((aoi.east - aoi.west) / lon_step))
    for row in range(rows):
        lat = aoi.south + (row + 0.5) * (aoi.north - aoi.south) / rows
        for col in range(cols):
            lon = aoi.west + (col + 0.5) * (aoi.east - aoi.west) / cols
            circles.append(Circle(lon=round(lon, 4), lat=round(lat, 4), radius_nm=radius_nm))
    return tuple(circles)
