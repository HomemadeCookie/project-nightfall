"""Source adapter contract.

Every upstream source is reached through exactly one adapter. The adapter owns its
credentials, its quota, its licence obligations, and its response schema, and it writes the
raw upstream response before parsing it. Nothing outside an adapter may call an upstream URL.
"""

from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from nightfall.clock import utc_now
from nightfall.ratelimit import Quota, TokenBucket
from nightfall.store import RawStore


class CommercialUse(StrEnum):
    """Whether the upstream licence permits commercial use.

    Checked by CI against the call site. The project is non-commercial today; this exists so
    that becoming commercial is a deliberate, visible decision rather than a silent breach.
    """

    PERMITTED = "permitted"
    PROHIBITED = "prohibited"
    SHARE_ALIKE = "share_alike"


@dataclass(frozen=True, slots=True)
class Licence:
    name: str
    url: str
    commercial_use: CommercialUse
    attribution: str


@dataclass(frozen=True, slots=True)
class RawRecord:
    """One raw upstream response, on its way to the immutable landing zone."""

    source: str
    request_key: str
    body: bytes
    content_type: str


def as_number(value: object) -> float | None:
    """Coerce a wire value to a float, or None if it is not a number.

    Upstreams put non-numbers in numeric fields (adsb.lol sends the string "ground" in
    `alt_baro`), and `bool` is an `int` in Python, so both are excluded explicitly.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def as_integer(value: object) -> int | None:
    """Coerce a wire value to an int, or None if it is not an integral number.

    Used for AIS enumeration codes, where a float would imply a precision the code does
    not have.
    """
    number = as_number(value)
    if number is None or number != int(number):
        return None
    return int(number)


def as_text(value: object) -> str | None:
    """Coerce a wire value to trimmed text, or None if it is absent or blank.

    Padding is common: adsb.lol space-pads `flight` to eight characters, so an untrimmed
    callsign would not match the same aircraft between two polls.
    """
    if value is None:
        return None
    return str(value).strip() or None


class SourceOutage(Exception):
    """An upstream is unavailable.

    Raised rather than retried once the circuit opens. Collectors record an outage and exit
    successfully: a failed poll must degrade freshness, never break the deployment.
    """


class SourceAdapter(ABC):
    """Base class for every upstream source."""

    #: Stable identifier, used as the `raw/` prefix and the manifest key.
    name: str
    licence: Licence
    quota: Quota

    #: Documented ceiling on consecutive upstream failures before the circuit opens.
    max_attempts: int = 4

    def __init__(self, store: RawStore, *, bucket: TokenBucket | None = None) -> None:
        self._store = store
        self._bucket = bucket if bucket is not None else TokenBucket(self.quota)

    @abstractmethod
    async def collect(self) -> Sequence[RawRecord]:
        """Fetch from upstream. Implementations must not parse or transform."""

    async def run(self) -> list[str]:
        """Collect and persist. Returns the landing-zone paths written."""
        records = await self.collect()
        return [
            self._store.put(
                source=record.source,
                request_key=record.request_key,
                body=record.body,
                observed_at=utc_now(),
                content_type=record.content_type,
            )
            for record in records
        ]

    async def _backoff(self, attempt: int, *, retry_after: float | None = None) -> None:
        """Exponential backoff with full jitter, honouring a server-supplied Retry-After."""
        if retry_after is not None:
            await asyncio.sleep(retry_after)
            return
        ceiling = min(2.0**attempt, 60.0)
        await asyncio.sleep(random.uniform(0.0, ceiling))  # noqa: S311 - jitter, not crypto
