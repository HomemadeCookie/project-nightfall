"""The source adapter contract.

An adapter turns one external API into envelopes. It does no cleaning beyond
splitting a response into sensible records; typing and dedup happen in staging.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime
from typing import ClassVar

from nightfall.core.envelope import Envelope
from nightfall.core.http import Http
from nightfall.core.license import License


class Source(ABC):
    name: ClassVar[str]
    license: ClassVar[list[License]]
    cadence: ClassVar[str] = "daily"  # hourly | daily | weekly | stream
    attribution: ClassVar[str] = ""
    needs_secret: ClassVar[str | None] = None  # env var name, if a free key is required

    lookback_days: ClassVar[int] = 21
    snapshot: ClassVar[bool] = False  # whole-file source: skip a fetch whose payload is unchanged
    incremental: ClassVar[tuple[str, str] | None] = None  # (dataset, request key) to skip on re-runs

    def __init__(self, http: Http, *, lookback_days: int | None = None, known: set[str] | None = None):
        self.http = http
        if lookback_days is not None:
            self.lookback_days = lookback_days
        self.known = known or set()  # request keys already in the lake, for incremental sources

    @abstractmethod
    def fetch(self, now: datetime) -> Iterator[Envelope]:
        """Yield envelopes for everything new as of ``now``."""

    def envelope(self, dataset: str, payload, *, now: datetime, request=None, event_time=None):
        return Envelope(
            source=self.name,
            dataset=dataset,
            license=list(self.license),
            fetched_at=now,
            event_time=event_time,
            request=request or {},
            payload=payload,
        )
