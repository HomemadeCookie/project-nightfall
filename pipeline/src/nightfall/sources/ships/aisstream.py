"""AISStream websocket source (free API key from aisstream.io; set AISSTREAM_API_KEY).

``nightfall ingest aisstream`` listens for a bounded time and stores compact position and static
records as raw envelopes; ``nightfall collect-ais`` repeats that in chunks for long-running jobs.
Terrestrial AIS coverage around the Philippines is patchy, so answers that use AIS carry a coverage
score instead of pretending the picture is complete.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

from nightfall.core.envelope import Envelope
from nightfall.core.license import License
from nightfall.sources.base import Source
from nightfall.sources.registry import register

URL = "wss://stream.aisstream.io/v0/stream"
# [[lat, lon], [lat, lon]] corners; covers the Philippine archipelago and nearby approaches.
BOUNDING_BOX = [[[3.0, 114.0], [22.5, 128.5]]]
SOURCE = "aisstream"


def subscription(api_key: str) -> dict:
    return {
        "APIKey": api_key,
        "BoundingBoxes": BOUNDING_BOX,
        "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
    }


def compact(msg: dict) -> tuple[str, dict] | None:
    """(dataset, record) for the messages we keep, else None. Keeps payloads small."""
    kind = msg.get("MessageType")
    meta = msg.get("MetaData", {})
    body = msg.get("Message", {}).get(kind or "", {})
    if kind == "PositionReport":
        return "positions", {
            "mmsi": str(meta.get("MMSI") or body.get("UserID")),
            "t": _utc(meta.get("time_utc")),
            "lat": body.get("Latitude", meta.get("latitude")),
            "lon": body.get("Longitude", meta.get("longitude")),
            "sog": body.get("Sog"),
            "cog": body.get("Cog"),
            "nav": body.get("NavigationalStatus"),
        }
    if kind == "ShipStaticData":
        return "static", {
            "mmsi": str(meta.get("MMSI") or body.get("UserID")),
            "t": _utc(meta.get("time_utc")),
            "name": (meta.get("ShipName") or body.get("Name") or "").strip(),
            "type": body.get("Type"),
            "destination": (body.get("Destination") or "").strip(),
            "draught": body.get("MaximumStaticDraught"),
            "length": _length(body.get("Dimension")),
        }
    return None


def _length(dim: dict | None) -> float | None:
    return None if not dim else float((dim.get("A") or 0) + (dim.get("B") or 0))


def _utc(value: str | None) -> str | None:
    """AISStream stamps look like '2026-10-16 08:15:00.123456 +0000 UTC'."""
    if not value:
        return None
    try:
        return (
            datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")
            .replace(tzinfo=UTC)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )
    except ValueError:
        return None


class Buffer:
    def __init__(self) -> None:
        self.records: dict[str, list[dict]] = {"positions": [], "static": []}

    def add(self, msg: dict) -> bool:
        item = compact(msg)
        if item is None or (item[0] == "positions" and item[1].get("lat") is None):
            return False
        self.records[item[0]].append(item[1])
        return True

    def __len__(self) -> int:
        return sum(len(v) for v in self.records.values())


Connect = Callable[[], object]


async def listen(
    api_key: str,
    duration_s: float,
    *,
    connect: Connect | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> Buffer:
    """Collect messages for ``duration_s`` seconds. A dropped connection ends the window early."""
    if connect is None:
        import websockets

        def connect():
            return websockets.connect(URL)

    buf, start = Buffer(), clock()
    async with connect() as ws:
        await ws.send(json.dumps(subscription(api_key)))
        while clock() - start < duration_s:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
            except TimeoutError:
                continue
            except Exception:
                break
            try:
                buf.add(json.loads(raw))
            except (ValueError, TypeError):
                continue
    return buf


@register
class AisStream(Source):
    name = SOURCE
    license = [License.UNCLEAR]  # AISStream terms for commercial use are not verified
    cadence = "stream"
    attribution = "AIS data via aisstream.io"
    needs_secret = "AISSTREAM_API_KEY"
    listen_seconds = 120.0

    def fetch(self, now: datetime) -> Iterator[Envelope]:
        key = os.environ.get("AISSTREAM_API_KEY")
        if not key:
            return  # optional source: no key, no data (the answers report reduced coverage)
        buf = asyncio.run(listen(key, self.listen_seconds))
        for dataset, recs in buf.records.items():
            if recs:
                yield self.envelope(dataset, recs, now=now, event_time=now, request={"bbox": BOUNDING_BOX})
