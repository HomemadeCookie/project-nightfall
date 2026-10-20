"""Scene catalog for the flood squares.

Microsoft Planetary Computer serves Copernicus Sentinel-1 RTC, Sentinel-2 L2A, and
Copernicus DEM as a public STAC catalog. This adapter stores scene records only.
Pixels stay at the catalog until a later job cuts a chip window.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

from nightfall.core.envelope import Envelope
from nightfall.core.license import License
from nightfall.core.reference import flood_chips
from nightfall.core.time import parse_iso
from nightfall.sources.base import Source
from nightfall.sources.registry import register

SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
ITEM = "https://planetarycomputer.microsoft.com/api/stac/v1/collections/{collection}/items/{item_id}"

# (collection, whether the search is limited to the lookback window)
COLLECTIONS = (
    ("sentinel-1-rtc", True),
    ("sentinel-2-l2a", True),
    ("cop-dem-glo-30", False),
)


def slim_item(feature: dict, chip: dict) -> dict:
    """Catalog fields only. Asset URLs, signatures, and pixels are dropped."""
    props = feature.get("properties") or {}
    sensing = props.get("datetime") or props.get("start_datetime")
    collection = feature.get("collection")
    item_id = feature["id"]
    return {
        "seen_key": f"{chip['chip_id']}:{item_id}",
        "chip_id": chip["chip_id"],
        "item_id": item_id,
        "collection": collection,
        "sensing_time": sensing,
        "cloud_cover": props.get("eo:cloud_cover"),
        "west": chip["west"],
        "south": chip["south"],
        "east": chip["east"],
        "north": chip["north"],
        "item_href": ITEM.format(collection=collection, item_id=item_id),
    }


@register
class PlanetaryStac(Source):
    name = "planetary_stac"
    license = [License.ATTRIBUTION]
    cadence = "daily"
    attribution = (
        "Contains modified Copernicus Sentinel data (2026) and Copernicus DEM, "
        "processed by ESA. Catalog access via Microsoft Planetary Computer."
    )
    lookback_days = 21
    incremental = ("scenes", "seen_key")

    def fetch(self, now: datetime) -> Iterator[Envelope]:
        start = (now - timedelta(days=self.lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        window = f"{start}/{end}"
        for chip in flood_chips():
            bbox = f"{chip['west']},{chip['south']},{chip['east']},{chip['north']}"
            for collection, timed in COLLECTIONS:
                params = {"collections": collection, "bbox": bbox, "limit": "100"}
                if timed:
                    params["datetime"] = window
                body = self.http.get_json(SEARCH, params=params)
                for feature in body.get("features") or []:
                    if not feature.get("id"):
                        continue
                    slim = slim_item(feature, chip)
                    if not slim["sensing_time"] or slim["seen_key"] in self.known:
                        continue
                    yield self.envelope(
                        "scenes",
                        slim,
                        now=now,
                        request={"seen_key": slim["seen_key"], "chip_id": chip["chip_id"]},
                        event_time=parse_iso(slim["sensing_time"]),
                    )
