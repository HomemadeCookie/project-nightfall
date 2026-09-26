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
from datetime import datetime
from enum import StrEnum

from nightfall.config import Settings
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


class SourceFamily(StrEnum):
    """What a source is for, which decides whether it may appear on the Phase 1 map.

    Mobility adapters feed the overlay. Statistics adapters land official tables for
    later analysis; they must not show up as 'not configured' on a map that does not
    draw them (README § Milestones, Phase 3).
    """

    MOBILITY = "mobility"
    STATISTICS = "statistics"


@dataclass(frozen=True, slots=True)
class Licence:
    name: str
    url: str
    commercial_use: CommercialUse
    attribution: str


@dataclass(frozen=True, slots=True)
class RawRecord:
    """One raw upstream response, on its way to the immutable landing zone.

    `observed_at` is set by the adapter at fetch time rather than by the store at write time.
    A collector that sweeps repeatedly within one job produces many records per run, and
    stamping them all with the moment the run finished would collapse the timeline the sweeps
    exist to capture.
    """

    source: str
    request_key: str
    body: bytes
    content_type: str
    observed_at: datetime


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


class SourceOutageError(Exception):
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
    family: SourceFamily = SourceFamily.MOBILITY

    #: Documented ceiling on consecutive upstream failures before the circuit opens.
    max_attempts: int = 4

    def __init__(
        self,
        store: RawStore,
        settings: Settings,
        *,
        bucket: TokenBucket | None = None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._bucket = bucket if bucket is not None else TokenBucket(self.quota)

    @property
    def headers(self) -> dict[str, str]:
        """Headers every outbound request carries.

        The User-Agent is mandatory, not polite: adsb.lol answers a generic one with HTTP 403,
        and these are free services that need a way to reach whoever is generating the load.
        """
        return {
            "user-agent": self._settings.user_agent,
            "accept": "application/json",
        }

    @abstractmethod
    async def collect(self) -> Sequence[RawRecord]:
        """Fetch from upstream. Implementations must not parse or transform."""

    def coverage_note(self) -> str | None:
        """What this collection failed to observe, in words, or None if it observed it all.

        Reported even on a successful run, and carried through to the manifest the browser
        reads. A run that quietly observed two thirds of the area of interest is not a
        successful run, it is a partial one, and the difference has to be visible (invariant 7).
        """
        return None

    async def run(self) -> list[str]:
        """Collect and persist. Returns the landing-zone paths written."""
        records = await self.collect()
        return [
            self._store.put(
                source=record.source,
                request_key=record.request_key,
                body=record.body,
                observed_at=record.observed_at,
                content_type=record.content_type,
            )
            for record in records
        ]

    async def _backoff(self, attempt: int, *, retry_after: float | None = None) -> None:
        """Exponential backoff with jitter, honouring a server-supplied Retry-After.

        Jittered over the upper half of the window rather than from zero. Full jitter can
        return almost immediately, which against a provider that has just refused the request
        means retrying inside the very interval it objected to — the retries then fail
        identically and the attempt budget is spent without ever having waited.
        """
        if retry_after is not None:
            await asyncio.sleep(retry_after)
            return
        ceiling = min(2.0**attempt, 60.0)
        floor = min(ceiling, max(ceiling / 2.0, self.quota.min_interval_s))
        await asyncio.sleep(random.uniform(floor, ceiling))
