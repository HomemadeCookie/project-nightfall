"""Shared token-bucket limiter.

Every adapter routes its requests through this, configured to the provider's published
limits. Hand-rolled sleep loops are forbidden: they do not compose across the multiple
windows (per second, per hour, per day) that real providers publish.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Window:
    """A published rate limit: `capacity` requests per `seconds`."""

    capacity: int
    seconds: float

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        if self.seconds <= 0:
            raise ValueError("seconds must be positive")

    @property
    def refill_per_second(self) -> float:
        return self.capacity / self.seconds


@dataclass(frozen=True, slots=True)
class Quota:
    """The full set of windows a provider documents, plus its concurrency ceiling."""

    windows: tuple[Window, ...]
    max_concurrent: int = 1
    source: str = ""

    def __post_init__(self) -> None:
        if not self.windows:
            raise ValueError("a quota must declare at least one window")
        if self.max_concurrent <= 0:
            raise ValueError("max_concurrent must be positive")


@dataclass
class _Bucket:
    window: Window
    tokens: float
    updated_at: float = field(default=0.0)


class TokenBucket:
    """Enforces every window in a quota simultaneously.

    A request waits until all windows have a token available, so the effective rate is the
    most restrictive window rather than whichever one happened to be checked.
    """

    def __init__(self, quota: Quota, *, monotonic: object = None) -> None:
        self._quota = quota
        self._now = asyncio.get_event_loop().time if monotonic is None else monotonic  # type: ignore[assignment]
        start = self._clock()
        self._buckets = [
            _Bucket(window=w, tokens=float(w.capacity), updated_at=start) for w in quota.windows
        ]
        self._semaphore = asyncio.Semaphore(quota.max_concurrent)

    def _clock(self) -> float:
        try:
            return float(self._now())  # type: ignore[operator]
        except RuntimeError:
            # No running loop yet (construction outside async context); start the clock at 0.
            return 0.0

    def _refill(self, now: float) -> None:
        for bucket in self._buckets:
            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(
                float(bucket.window.capacity),
                bucket.tokens + elapsed * bucket.window.refill_per_second,
            )
            bucket.updated_at = now

    def _wait_seconds(self) -> float:
        """Seconds until every window can supply one token. Zero means proceed now."""
        now = self._clock()
        self._refill(now)
        waits = [
            (1.0 - b.tokens) / b.window.refill_per_second for b in self._buckets if b.tokens < 1.0
        ]
        return max(waits) if waits else 0.0

    def _consume(self) -> None:
        for bucket in self._buckets:
            bucket.tokens -= 1.0

    async def acquire(self) -> None:
        """Block until a request may proceed, then consume one token from every window."""
        async with self._semaphore:
            while True:
                wait = self._wait_seconds()
                if wait <= 0.0:
                    self._consume()
                    return
                await asyncio.sleep(wait)


# Published limits, transcribed from provider documentation. Changing a number here changes
# real behaviour, so each carries its source.
ADSB_LOL_QUOTA = Quota(
    windows=(Window(capacity=1, seconds=1.0),),
    max_concurrent=1,
    source="adsb.lol documents ~1 request per second",
)

AISSTREAM_QUOTA = Quota(
    windows=(Window(capacity=1, seconds=1.0),),
    max_concurrent=3,
    source=(
        "aisstream.io: 3 subscribed connections per account and per originating IP; "
        "1 subscription message per second per connection"
    ),
)

OPEN_METEO_QUOTA = Quota(
    windows=(
        Window(capacity=600, seconds=60.0),
        Window(capacity=5_000, seconds=3_600.0),
        Window(capacity=10_000, seconds=86_400.0),
    ),
    max_concurrent=4,
    source="open-meteo free tier: 600/min, 5000/hour, 10000/day",
)
