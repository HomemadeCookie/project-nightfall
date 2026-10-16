"""GDELT DOC 2.0 article search: headlines and links about supply-chain topics in the Philippines.

Only metadata (title, URL, domain, date) is stored. GDELT asks for one request per 5 seconds.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from nightfall.core.envelope import Envelope
from nightfall.core.license import License
from nightfall.sources.base import Source
from nightfall.sources.registry import register

URL = "https://api.gdeltproject.org/api/v2/doc/doc"
QUERIES = {
    "typhoon": '(Philippines OR PAGASA) (typhoon OR "tropical storm" OR "wind signal")',
    "sea_trips": '(Philippines) ("sea trips" OR "coast guard" OR ferry OR RoRo) (suspended OR cancelled)',
    "fuel": '(Philippines) (diesel OR gasoline OR "oil price") (rollback OR hike OR "price adjustment")',
    "ports": '(Philippines) (port OR "Manila port" OR "Batangas port" OR container) (congestion OR delay)',
    "staples": '(Philippines) (rice OR sugar OR "cooking oil" OR LPG) (price OR shortage OR import)',
}


@register
class Gdelt(Source):
    name = "gdelt"
    license = [License.ATTRIBUTION]
    cadence = "hourly"
    attribution = "GDELT Project (headlines and links only)"

    def __init__(self, http, **kw):
        super().__init__(http, **kw)
        http._min_interval["api.gdeltproject.org"] = 5.5

    def fetch(self, now: datetime) -> Iterator[Envelope]:
        for topic, query in QUERIES.items():
            params = {
                "query": query,
                "mode": "artlist",
                "maxrecords": "75",
                "format": "json",
                "timespan": "24h",
                "sort": "datedesc",
            }
            resp = self.http.get(URL, params=params)
            try:
                articles = resp.json().get("articles", [])
            except ValueError:  # GDELT returns plain-text notices when throttling
                continue
            slim = [
                {k: a.get(k) for k in ("url", "title", "seendate", "domain", "language", "sourcecountry")}
                for a in articles
            ]
            yield self.envelope(
                "articles",
                {"topic": topic, "articles": slim},
                now=now,
                request={"topic": topic, "timespan": "24h"},
            )
