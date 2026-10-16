"""IBTrACS best tracks for the western North Pacific (NOAA, public domain).

Used to calibrate and backtest storm-exposure logic against history. The full CSV is ~115 MB, so
we keep only the Philippine area of responsibility and the columns we use.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import datetime

from nightfall.core.envelope import Envelope
from nightfall.core.license import License
from nightfall.sources.base import Source
from nightfall.sources.registry import register

URL = (
    "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/"
    "v04r01/access/csv/ibtracs.WP.list.v04r01.csv"
)
# Philippine area of responsibility (PAR), widened a little.
LAT_MIN, LAT_MAX, LON_MIN, LON_MAX = 3.0, 28.0, 112.0, 138.0
FROM_YEAR = 1990


def parse_ibtracs(text: str, from_year: int = FROM_YEAR) -> list[dict]:
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    next(reader)  # units row
    idx = {name: i for i, name in enumerate(header)}
    need = [
        "SID",
        "SEASON",
        "NAME",
        "ISO_TIME",
        "LAT",
        "LON",
        "USA_WIND",
        "WMO_WIND",
        "USA_R34_NE",
        "USA_R34_SE",
        "USA_R34_SW",
        "USA_R34_NW",
    ]
    out: list[dict] = []
    for row in reader:
        try:
            season = int(row[idx["SEASON"]])
            lat, lon = float(row[idx["LAT"]]), float(row[idx["LON"]])
        except ValueError:
            continue
        if season < from_year or not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
            continue
        rec = {k.lower(): row[idx[k]].strip() for k in need}
        rec["lat"], rec["lon"] = lat, lon
        out.append(rec)
    return out


@register
class Ibtracs(Source):
    name = "ibtracs"
    license = [License.PUBLIC_DOMAIN]
    cadence = "weekly"
    snapshot = True
    attribution = "NOAA NCEI IBTrACS v04r01"

    def fetch(self, now: datetime) -> Iterator[Envelope]:
        text = self.http.get(URL).text
        rows = parse_ibtracs(text)
        yield self.envelope("wp_tracks", rows, now=now, request={"url": URL, "from_year": FROM_YEAR})
