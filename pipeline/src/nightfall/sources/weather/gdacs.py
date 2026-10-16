"""GDACS tropical cyclones: current storms with past and forecast track points."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from nightfall.core.envelope import Envelope
from nightfall.core.license import License
from nightfall.sources.base import Source
from nightfall.sources.registry import register

URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP"
KEEP_PROPS = [
    "eventid",
    "eventname",
    "alertlevel",
    "episodeid",
    "fromdate",
    "todate",
    "datemodified",
    "polygondate",
    "polygonlabel",
    "Class",
    "severitydata",
    "source",
    "iscurrent",
]


def slim_feature(f: dict) -> dict:
    """Drop icons and links; keep geometry only where we use it (points and tracks)."""
    props = {k: f["properties"].get(k) for k in KEEP_PROPS}
    geom = f["geometry"]
    cls = props["Class"] or ""
    if cls.startswith("Point_Polygon_Point"):
        ring = geom["coordinates"][0]
        lon0, lat0 = ring[0]
        # Wind-radius polygon: radius is the farthest vertex from the centre, in degrees.
        radius_deg = max(((x - lon0) ** 2 + (y - lat0) ** 2) ** 0.5 for x, y in ring)
        geom = {"type": "Point", "coordinates": [lon0, lat0], "radius_deg": round(radius_deg, 3)}
    elif cls == "Poly_Cones":
        geom = None
    return {"properties": props, "geometry": geom}


@register
class Gdacs(Source):
    name = "gdacs"
    license = [License.UNCLEAR]
    cadence = "hourly"
    attribution = "Global Disaster Alert and Coordination System (GDACS)"

    def fetch(self, now: datetime) -> Iterator[Envelope]:
        body = self.http.get_json(URL, params={"eventtype": "TC"})
        feats = [slim_feature(f) for f in body["features"] if f["properties"].get("iscurrent") == "true"]
        feats = [f for f in feats if f["geometry"] is not None]
        yield self.envelope("tc_current", feats, now=now, request={"eventtype": "TC"})
