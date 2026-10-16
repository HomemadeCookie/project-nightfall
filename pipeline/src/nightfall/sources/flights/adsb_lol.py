"""adsb.lol aircraft snapshots around Philippine airports (ODbL). Used for air-cargo activity."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from nightfall.core.envelope import Envelope
from nightfall.core.license import License
from nightfall.sources.base import Source
from nightfall.sources.registry import register

AIRPORTS = {
    "MNL": (14.5086, 121.0198),
    "CRK": (15.1859, 120.5602),
    "CEB": (10.3075, 123.9794),
    "DVO": (7.1255, 125.6458),
}
RADIUS_NM = 60
KEEP = ("hex", "flight", "r", "t", "alt_baro", "gs", "lat", "lon", "category")


@register
class AdsbLol(Source):
    name = "adsb_lol"
    license = [License.ATTRIBUTION, License.SHARE_ALIKE]
    cadence = "hourly"
    attribution = "adsb.lol (ODbL)"

    def __init__(self, http):
        super().__init__(http)
        http._min_interval["api.adsb.lol"] = 2.0

    def fetch(self, now: datetime) -> Iterator[Envelope]:
        for code, (lat, lon) in AIRPORTS.items():
            body = self.http.get_json(f"https://api.adsb.lol/v2/point/{lat}/{lon}/{RADIUS_NM}")
            aircraft = [{k: a.get(k) for k in KEEP} for a in body.get("ac", [])]
            yield self.envelope(
                "aircraft_snapshot",
                {"airport": code, "aircraft": aircraft},
                now=now,
                request={"airport": code, "radius_nm": RADIUS_NM},
                event_time=now,
            )
