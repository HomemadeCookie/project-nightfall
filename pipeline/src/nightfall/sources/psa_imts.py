"""PSA OpenSTAT International Merchandise Trade Statistics.

Official Philippine trade totals, compiled from Bureau of Customs declarations and
published through PX-Web. This is the machine-readable form of what BOC collects;
the BOC Trade Data Platform itself has no bulk extract.

json-stat2 on this table returns a sparse stub. The PX-Web `json` format returns every
cell as `{key, values}`, which is what we store and tidy.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from nightfall.clock import utc_now
from nightfall.config import Settings
from nightfall.ratelimit import PSA_QUOTA, TokenBucket
from nightfall.sources.base import (
    CommercialUse,
    Licence,
    RawRecord,
    SourceAdapter,
    SourceFamily,
    SourceOutageError,
)
from nightfall.store import RawStore

API_ROOT = "https://openstat.psa.gov.ph/PXWeb/api/v1/en"

#: Monthly totals 1991-present. Compact enough to take whole.
TOTAL_TRADE_TABLE = "DB/2L/IMT/SUM/0012L4DFTS0.px"

PX_JSON_QUERY = {"query": [], "response": {"format": "json"}}


@dataclass(frozen=True, slots=True)
class TradeCell:
    source: str
    table: str
    year: int
    period: str
    partner: str | None
    flow: str
    value: float
    unit: str


class PsaImtsAdapter(SourceAdapter):
    name = "psa_imts"
    family = SourceFamily.STATISTICS
    licence = Licence(
        name="PSA OpenSTAT terms",
        url="https://openstat.psa.gov.ph/",
        commercial_use=CommercialUse.PERMITTED,
        attribution="Merchandise trade statistics © Philippine Statistics Authority",
    )
    quota = PSA_QUOTA

    def __init__(
        self,
        store: RawStore,
        settings: Settings,
        *,
        bucket: TokenBucket | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        super().__init__(store, settings, bucket=bucket)
        self._timeout_s = timeout_s

    async def collect(self) -> Sequence[RawRecord]:
        records: list[RawRecord] = []
        async with httpx.AsyncClient(timeout=self._timeout_s, headers=self.headers) as client:
            metadata = await self._get(client, TOTAL_TRADE_TABLE)
            records.append(
                RawRecord(
                    source=self.name,
                    request_key="imts/total-trade-monthly/meta",
                    body=metadata,
                    content_type="application/json",
                    observed_at=utc_now(),
                )
            )
            totals = await self._post(client, TOTAL_TRADE_TABLE, PX_JSON_QUERY)
            records.append(
                RawRecord(
                    source=self.name,
                    request_key="imts/total-trade-monthly",
                    body=totals,
                    content_type="application/json",
                    observed_at=utc_now(),
                )
            )
        return records

    async def _get(self, client: httpx.AsyncClient, table: str) -> bytes:
        return await self._request(client, "GET", f"{API_ROOT}/{table}", json_body=None)

    async def _post(self, client: httpx.AsyncClient, table: str, payload: dict[str, Any]) -> bytes:
        return await self._request(client, "POST", f"{API_ROOT}/{table}", json_body=payload)

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        json_body: dict[str, Any] | None,
    ) -> bytes:
        for attempt in range(self.max_attempts):
            await self._bucket.acquire()
            try:
                response = await client.request(method, url, json=json_body)
            except httpx.HTTPError as exc:
                if attempt == self.max_attempts - 1:
                    raise SourceOutageError(f"openstat.psa.gov.ph unreachable: {exc}") from exc
                await self._backoff(attempt)
                continue
            if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                await self._backoff(attempt)
                continue
            if httpx.codes.BAD_REQUEST <= response.status_code < httpx.codes.INTERNAL_SERVER_ERROR:
                raise SourceOutageError(
                    f"openstat.psa.gov.ph rejected {url}: HTTP {response.status_code}"
                )
            if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
                if attempt == self.max_attempts - 1:
                    raise SourceOutageError(
                        f"openstat.psa.gov.ph failing: HTTP {response.status_code}"
                    )
                await self._backoff(attempt)
                continue
            return response.content
        raise SourceOutageError(f"openstat.psa.gov.ph exhausted attempts for {url}")


def tidy_pxjson(body: bytes, *, table: str) -> list[TradeCell]:
    document = json.loads(body)
    columns = [str(col.get("code") or col.get("text")) for col in document.get("columns") or []]
    comments_title = next(
        (str(col.get("text")) for col in document.get("columns") or [] if col.get("type") == "c"),
        table,
    )
    unit = "million_usd" if "Total Trade" in comments_title or "IMTS" in table else "usd"
    # Metadata for code→label is not in the json extract; year 0 = 1991 on both SUM tables.
    cells: list[TradeCell] = []
    for row in document.get("data") or []:
        key = [str(part) for part in row.get("key") or []]
        values = row.get("values") or []
        if not key or not values:
            continue
        number = _as_float(values[0])
        if number is None:
            continue
        year, period, partner, flow = _decode_key(key, columns)
        cells.append(
            TradeCell(
                source="psa_imts",
                table=table,
                year=year,
                period=period,
                partner=partner,
                flow=flow,
                value=number,
                unit=unit,
            )
        )
    return cells


def _decode_key(key: Sequence[str], columns: Sequence[str]) -> tuple[int, str, str | None, str]:
    names = [name.lower() for name in columns]
    year = 1991 + int(key[0])
    period = "annual"
    partner: str | None = None
    flow = "unknown"
    for index, name in enumerate(names[:-1]):
        if index >= len(key):
            break
        code = key[index]
        if name == "month":
            period = _month_label(code)
        elif name == "country":
            partner = code
        elif name in {"variables", "item"}:
            flow = _flow_label(code, name)
        elif name == "year":
            year = 1991 + int(code)
    return year, period, partner, flow


def _month_label(code: str) -> str:
    months = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
        "annual",
    )
    index = int(code)
    return months[index] if 0 <= index < len(months) else code


def _flow_label(code: str, column: str) -> str:
    if column == "variables":
        return {"0": "exports", "1": "imports", "2": "balance", "3": "total"}.get(code, code)
    return {"0": "total", "1": "imports", "2": "exports", "3": "balance"}.get(code, code)


def _as_float(value: object) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None
