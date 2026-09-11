"""The shared token bucket.

Hand-rolled sleep loops are forbidden because they do not compose across the several windows
real providers publish (`.cursorrules` § 5). These tests are about that composition.
"""

from __future__ import annotations

import asyncio

import pytest

from nightfall.ratelimit import (
    ADSB_LOL_QUOTA,
    AISSTREAM_QUOTA,
    OPEN_METEO_QUOTA,
    Quota,
    TokenBucket,
    Window,
)


class FakeClock:
    """A clock the test advances, so a rate-limit test does not take a rate-limited amount of
    time to run."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_window_rejects_nonsense() -> None:
    with pytest.raises(ValueError, match="capacity must be positive"):
        Window(capacity=0, seconds=1.0)
    with pytest.raises(ValueError, match="seconds must be positive"):
        Window(capacity=1, seconds=0.0)


def test_quota_needs_a_window() -> None:
    with pytest.raises(ValueError, match="at least one window"):
        Quota(windows=())


def test_the_most_restrictive_window_governs() -> None:
    """A per-hour allowance must not be spendable in the first second of the hour."""
    clock = FakeClock()
    quota = Quota(windows=(Window(capacity=10, seconds=1.0), Window(capacity=2, seconds=60.0)))
    bucket = TokenBucket(quota, monotonic=clock)

    asyncio.run(bucket.acquire())
    asyncio.run(bucket.acquire())
    # The per-second window still has tokens; the per-minute one does not.
    assert bucket._wait_seconds() > 0.0


def test_tokens_refill_over_time() -> None:
    clock = FakeClock()
    bucket = TokenBucket(Quota(windows=(Window(capacity=1, seconds=1.0),)), monotonic=clock)

    asyncio.run(bucket.acquire())
    assert bucket._wait_seconds() == pytest.approx(1.0)
    clock.now += 1.0
    assert bucket._wait_seconds() == 0.0


def test_published_quotas_are_transcribed_with_their_source() -> None:
    """Each number here changes real behaviour, so it must say where it came from."""
    for quota in (ADSB_LOL_QUOTA, AISSTREAM_QUOTA, OPEN_METEO_QUOTA):
        assert quota.source, "a quota without a documented source cannot be reviewed"
        assert quota.windows
