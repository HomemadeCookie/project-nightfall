"""USD/PHP reference rate (ECB reference rates via Frankfurter). No key."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

from nightfall.core.envelope import Envelope
from nightfall.core.license import License
from nightfall.sources.base import Source
from nightfall.sources.registry import register


@register
class Frankfurter(Source):
    name = "frankfurter"
    license = [License.ATTRIBUTION]
    cadence = "daily"
    attribution = "European Central Bank reference rates via Frankfurter"
    lookback_days = 45

    def fetch(self, now: datetime) -> Iterator[Envelope]:
        start = (now - timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")
        url = f"https://api.frankfurter.dev/v1/{start}.."
        body = self.http.get_json(url, params={"base": "USD", "symbols": "PHP"})
        yield self.envelope("usd_php", body, now=now, request={"start": start})
