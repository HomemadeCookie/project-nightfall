"""The single UTC/Asia-Manila conversion boundary.

Invariant 6: timestamps are timezone-aware UTC everywhere in storage and interchange, and are
converted to Asia/Manila only for presentation. Naive datetimes are rejected rather than
guessed at, because a silent local-time assumption would shift every seasonal window the
product produces.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

PH_TZ = ZoneInfo("Asia/Manila")


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def require_utc(value: datetime) -> datetime:
    """Assert a datetime is timezone-aware and in UTC."""
    if value.tzinfo is None:
        raise ValueError(f"naive datetime is not allowed: {value!r}")
    if value.utcoffset() != UTC.utcoffset(None):
        raise ValueError(f"expected UTC, got offset {value.utcoffset()!r}")
    return value


def from_unix(seconds: float) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


def to_manila(value: datetime) -> datetime:
    """Convert to Philippine local time. Presentation only."""
    return require_utc(value).astimezone(PH_TZ)


def isoformat_z(value: datetime) -> str:
    """RFC 3339 with a literal Z, which is what the manifest and artifacts carry."""
    return require_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")
