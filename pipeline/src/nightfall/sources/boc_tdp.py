"""Bureau of Customs Trade Data Platform.

CMO 04-2024 created a public request portal, not a bulk extract. PSA IMTS is the
official published form of BOC merchandise-trade declarations. This adapter probes
the portal so a later bulk feed would be noticed, and records the gap when none exists.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from nightfall.clock import utc_now
from nightfall.config import Settings
from nightfall.ratelimit import BOC_QUOTA, TokenBucket
from nightfall.sources.base import (
    CommercialUse,
    Licence,
    RawRecord,
    SourceAdapter,
    SourceFamily,
    SourceOutageError,
)
from nightfall.store import RawStore

PORTAL_URL = "https://tradedata.customs.gov.ph/"

NO_BULK_NOTE = (
    "BOC Trade Data Platform has no machine-readable bulk extract. "
    "PSA OpenSTAT IMTS is the official published form of BOC merchandise-trade declarations."
)


class BocTdpAdapter(SourceAdapter):
    name = "boc_tdp"
    family = SourceFamily.STATISTICS
    licence = Licence(
        name="BOC Trade Data Platform / CMO 04-2024",
        url="https://tradedata.customs.gov.ph/",
        commercial_use=CommercialUse.PERMITTED,
        attribution="Customs trade transparency portal © Bureau of Customs (Philippines)",
    )
    quota = BOC_QUOTA

    def __init__(
        self,
        store: RawStore,
        settings: Settings,
        *,
        bucket: TokenBucket | None = None,
        timeout_s: float = 20.0,
    ) -> None:
        super().__init__(store, settings, bucket=bucket)
        self._timeout_s = timeout_s
        self._note = NO_BULK_NOTE

    def coverage_note(self) -> str | None:
        return self._note

    async def collect(self) -> Sequence[RawRecord]:
        await self._bucket.acquire()
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s,
                headers={**self.headers, "accept": "text/html"},
                follow_redirects=True,
            ) as client:
                response = await client.get(PORTAL_URL)
        except httpx.HTTPError as exc:
            raise SourceOutageError(f"tradedata.customs.gov.ph unreachable: {exc}") from exc
        if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise SourceOutageError(
                f"tradedata.customs.gov.ph failing: HTTP {response.status_code}"
            )
        text = response.text
        self._note = portal_note(text)
        return [
            RawRecord(
                source=self.name,
                request_key="portal",
                body=response.content,
                content_type="text/html",
                observed_at=utc_now(),
            )
        ]


def portal_note(html: str) -> str:
    if "Performing Maintenance" in html:
        return (
            "BOC Trade Data Platform is under maintenance and has no bulk extract. "
            "Use PSA OpenSTAT IMTS for official merchandise-trade totals."
        )
    if "hs code" in html.lower() or "download" in html.lower():
        return (
            "BOC Trade Data Platform responded but still has no documented bulk API. "
            "Use PSA OpenSTAT IMTS for official merchandise-trade totals."
        )
    return NO_BULK_NOTE
