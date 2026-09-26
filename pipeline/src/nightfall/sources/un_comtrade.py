"""UN Comtrade public preview — Philippine merchandise trade.

Keyless preview endpoint, 500 rows per call, no pagination. Queries are narrowed to stay
under that cap: HS chapter x World for several years, and TOTAL x partners for recent
years. A response that returns exactly 500 rows is treated as truncated.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from nightfall.clock import utc_now
from nightfall.config import Settings
from nightfall.ratelimit import COMTRADE_QUOTA, TokenBucket
from nightfall.sources.base import (
    CommercialUse,
    Licence,
    RawRecord,
    SourceAdapter,
    SourceFamily,
    SourceOutageError,
)
from nightfall.store import RawStore

API_ROOT = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
PH_REPORTER = "608"
PREVIEW_CAP = 500
YEARS_HS2 = ("2019", "2020", "2021", "2022", "2023", "2024")
YEARS_PARTNERS = ("2023", "2024")
FLOWS = ("M", "X")


@dataclass(frozen=True, slots=True)
class ComtradeRow:
    year: int
    flow: str
    partner_code: int
    cmd_code: str
    value_usd: float | None
    netweight_kg: float | None
    truncated: bool


class UnComtradeAdapter(SourceAdapter):
    name = "un_comtrade"
    family = SourceFamily.STATISTICS
    licence = Licence(
        name="UN Comtrade terms of use",
        url="https://comtrade.un.org/",
        commercial_use=CommercialUse.PERMITTED,
        attribution="Merchandise trade © UN Comtrade, reporter Philippines (608)",
    )
    quota = COMTRADE_QUOTA

    def __init__(
        self,
        store: RawStore,
        settings: Settings,
        *,
        bucket: TokenBucket | None = None,
        timeout_s: float = 45.0,
    ) -> None:
        super().__init__(store, settings, bucket=bucket)
        self._timeout_s = timeout_s
        self._truncated: list[str] = []

    def coverage_note(self) -> str | None:
        if not self._truncated:
            return None
        return (
            "UN Comtrade preview returned the 500-row cap for: "
            + ", ".join(self._truncated)
            + ". Those extracts are truncated, not complete."
        )

    async def collect(self) -> Sequence[RawRecord]:
        records: list[RawRecord] = []
        async with httpx.AsyncClient(timeout=self._timeout_s, headers=self.headers) as client:
            for year in YEARS_HS2:
                for flow in FLOWS:
                    records.append(
                        await self._one(
                            client,
                            request_key=f"hs2/world/{year}/{flow}",
                            params={
                                "reporterCode": PH_REPORTER,
                                "period": year,
                                "partnerCode": "0",
                                "cmdCode": "AG2",
                                "flowCode": flow,
                                "maxRecords": str(PREVIEW_CAP),
                            },
                        )
                    )
            for year in YEARS_PARTNERS:
                for flow in FLOWS:
                    records.append(
                        await self._one(
                            client,
                            request_key=f"total/partners/{year}/{flow}",
                            params={
                                "reporterCode": PH_REPORTER,
                                "period": year,
                                "cmdCode": "TOTAL",
                                "flowCode": flow,
                                "maxRecords": str(PREVIEW_CAP),
                            },
                        )
                    )
        return records

    async def _one(
        self,
        client: httpx.AsyncClient,
        *,
        request_key: str,
        params: dict[str, str],
    ) -> RawRecord:
        body = await self._fetch(client, params)
        document = json.loads(body)
        count = int(document.get("count") or 0)
        if count >= PREVIEW_CAP:
            self._truncated.append(request_key)
        return RawRecord(
            source=self.name,
            request_key=request_key,
            body=body,
            content_type="application/json",
            observed_at=utc_now(),
        )

    async def _fetch(self, client: httpx.AsyncClient, params: dict[str, str]) -> bytes:
        url = f"{API_ROOT}?{urlencode(params)}"
        for attempt in range(self.max_attempts):
            await self._bucket.acquire()
            try:
                response = await client.get(API_ROOT, params=params)
            except httpx.HTTPError as exc:
                if attempt == self.max_attempts - 1:
                    raise SourceOutageError(f"comtradeapi.un.org unreachable: {exc}") from exc
                await self._backoff(attempt)
                continue
            if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                await self._backoff(attempt, retry_after=_retry_after(response))
                continue
            if httpx.codes.BAD_REQUEST <= response.status_code < httpx.codes.INTERNAL_SERVER_ERROR:
                raise SourceOutageError(
                    f"comtradeapi.un.org rejected {url}: HTTP {response.status_code}"
                )
            if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
                if attempt == self.max_attempts - 1:
                    raise SourceOutageError(
                        f"comtradeapi.un.org failing: HTTP {response.status_code}"
                    )
                await self._backoff(attempt)
                continue
            return response.content
        raise SourceOutageError(f"comtradeapi.un.org exhausted attempts for {url}")


def tidy_preview(body: bytes) -> list[ComtradeRow]:
    document = json.loads(body)
    count = int(document.get("count") or 0)
    truncated = count >= PREVIEW_CAP
    rows: list[ComtradeRow] = []
    for item in document.get("data") or []:
        if not isinstance(item, dict):
            continue
        year = _as_int(item.get("refYear") or item.get("period"))
        partner = _as_int(item.get("partnerCode"))
        cmd = str(item.get("cmdCode") or "")
        flow = {"M": "imports", "X": "exports"}.get(
            str(item.get("flowCode")), str(item.get("flowCode"))
        )
        if year is None or partner is None or not cmd:
            continue
        rows.append(
            ComtradeRow(
                year=year,
                flow=flow,
                partner_code=partner,
                cmd_code=cmd,
                value_usd=_as_float(
                    item.get("primaryValue") or item.get("cifvalue") or item.get("fobvalue")
                ),
                netweight_kg=_as_float(item.get("netWgt") or item.get("netweight")),
                truncated=truncated,
            )
        )
    return rows


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
