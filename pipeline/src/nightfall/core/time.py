"""Time helpers. Everything is stored in UTC; Manila time is for display only."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

MANILA = ZoneInfo("Asia/Manila")


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_iso(value: str) -> datetime:
    """Parse ISO-8601 (with 'Z' or no zone, which is taken as UTC)."""
    return ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def to_manila(dt: datetime) -> datetime:
    return ensure_utc(dt).astimezone(MANILA)


def iso(dt: datetime) -> str:
    return ensure_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def day_range(start: date, end: date) -> list[date]:
    n = (end - start).days
    return [start + timedelta(days=i) for i in range(n + 1)]


def next_weekday(d: date, weekday: int) -> date:
    """First date strictly after ``d`` falling on ``weekday`` (Mon=0)."""
    delta = (weekday - d.weekday()) % 7 or 7
    return d + timedelta(days=delta)
