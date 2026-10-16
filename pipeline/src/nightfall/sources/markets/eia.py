"""EIA daily spot prices: Brent, WTI, NY Harbor ULSD and conventional gasoline.

Public domain. Works with the shared DEMO_KEY; set EIA_API_KEY (free signup) for headroom.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime, timedelta

from nightfall.core.envelope import Envelope
from nightfall.core.license import License
from nightfall.sources.base import Source
from nightfall.sources.registry import register

URL = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
PRODUCTS = ["EPCBRENT", "EPCWTI", "EPD2DXL0", "EPMRU"]


@register
class Eia(Source):
    name = "eia"
    license = [License.PUBLIC_DOMAIN]
    cadence = "daily"
    attribution = "U.S. Energy Information Administration"
    lookback_days = 30

    def fetch(self, now: datetime) -> Iterator[Envelope]:
        start = (now - timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")
        params = {
            "api_key": os.environ.get("EIA_API_KEY", "DEMO_KEY"),
            "frequency": "daily",
            "data[0]": "value",
            "facets[product][]": PRODUCTS,
            "start": start,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "length": "5000",
        }
        body = self.http.get_json(URL, params=params)
        rows = body["response"]["data"]
        safe = {k: v for k, v in params.items() if k != "api_key"}
        yield self.envelope("spot_prices", rows, now=now, request=safe)
