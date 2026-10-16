"""Shared helpers for staging: typed Arrow tables and 'latest wins' deduplication."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pyarrow as pa

TYPES = {
    "str": pa.string(),
    "date": pa.date32(),
    "f": pa.float64(),
    "i": pa.int64(),
    "ts": pa.timestamp("us", tz="UTC"),
    "b": pa.bool_(),
}

# Days between the date a value describes and the date we can first know it. Backfilled history
# has no honest fetch time, so as-of logic uses available_on = date + lag instead of known_at.
PUBLICATION_LAG_DAYS = {"eia": 1, "fx": 1, "portwatch": 7, "pink_sheet": 40, "da_weekly": 3}


def make_table(rows: list[dict], cols: dict[str, str]) -> pa.Table:
    schema = pa.schema([(k, TYPES[v]) for k, v in cols.items()])
    return pa.Table.from_pylist(rows, schema=schema)


def parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def available_on(d: date, source: str) -> date:
    return d + timedelta(days=PUBLICATION_LAG_DAYS[source])


def num(value) -> float | None:
    try:
        return None if value in (None, "", " ") else float(value)
    except (TypeError, ValueError):
        return None


def as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
