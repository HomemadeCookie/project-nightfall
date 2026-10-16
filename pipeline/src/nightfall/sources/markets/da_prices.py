"""DA Bantay Presyo: weekly average retail prices in NCR markets (PDF).

Only NCR is published at this granularity. We store the extracted text, not the PDF, so parser
fixes can be re-applied to history without re-downloading. The licence is UNCLEAR: the IP Code
(RA 8293 s.176) leaves government works uncopyrighted but requires the agency's prior approval to
exploit them for profit.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterator
from datetime import datetime

import pdfplumber

from nightfall.core.envelope import Envelope
from nightfall.core.license import License
from nightfall.sources.base import Source
from nightfall.sources.registry import register

PAGE = "https://www.da.gov.ph/price-monitoring/"
_WEEKLY = re.compile(r"https://[^\"'\s]*/(?:Revised-)?Weekly-Average-Price[s]?-[^\"'\s]*\.pdf")


def weekly_links(html: str) -> list[str]:
    """Weekly-average PDF links on the listing page (revised editions included)."""
    return sorted(set(_WEEKLY.findall(html)))


def pdf_text(content: bytes) -> str:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


@register
class DaWeeklyPrices(Source):
    name = "da_prices"
    license = [License.UNCLEAR]
    cadence = "weekly"
    attribution = "Department of Agriculture - Bantay Presyo (DA-AMAS)"
    max_new_per_run = 400
    incremental = ("weekly_ncr", "url")

    def __init__(self, http, **kw):
        super().__init__(http, **kw)
        http._min_interval["www.da.gov.ph"] = 1.0

    def fetch(self, now: datetime) -> Iterator[Envelope]:
        html = self.http.get(PAGE).text
        todo = [u for u in weekly_links(html) if u not in self.known][-self.max_new_per_run :]
        for url in todo:
            content = self.http.get(url).content
            yield self.envelope("weekly_ncr", {"text": pdf_text(content)}, now=now, request={"url": url})
