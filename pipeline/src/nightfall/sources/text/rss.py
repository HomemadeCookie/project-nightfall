"""Philippine news RSS: titles, links, dates and a short teaser. No article bodies are stored."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import datetime
from email.utils import parsedate_to_datetime

from nightfall.core.envelope import Envelope
from nightfall.core.license import License
from nightfall.core.time import ensure_utc, iso
from nightfall.sources.base import Source
from nightfall.sources.registry import register

FEEDS = {
    "philstar_business": "https://www.philstar.com/rss/business",
    "philstar_nation": "https://www.philstar.com/rss/nation",
    "rappler": "https://www.rappler.com/feed/",
}
TEASER_CHARS = 280
_TAG = re.compile(r"<[^>]+>")


def _text(item: ET.Element, tag: str) -> str:
    el = item.find(tag)
    return (el.text or "").strip() if el is not None else ""


def parse_feed(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = []
    for item in root.iter("item"):
        published = None
        if _text(item, "pubDate"):
            try:
                published = iso(ensure_utc(parsedate_to_datetime(_text(item, "pubDate"))))
            except (TypeError, ValueError):
                published = None
        teaser = html.unescape(_TAG.sub(" ", _text(item, "description")))
        teaser = re.sub(r"\s+", " ", teaser).strip()[:TEASER_CHARS]
        items.append(
            {
                "title": html.unescape(_text(item, "title")),
                "url": _text(item, "link"),
                "published": published,
                "teaser": teaser,
            }
        )
    return items


@register
class NewsRss(Source):
    name = "news_rss"
    license = [License.UNCLEAR]  # facts and links only; never republished
    cadence = "hourly"
    attribution = "Headlines link to their publishers"

    def fetch(self, now: datetime) -> Iterator[Envelope]:
        for feed, url in FEEDS.items():
            items = parse_feed(self.http.get(url).text)
            yield self.envelope("items", {"feed": feed, "items": items}, now=now, request={"url": url})
