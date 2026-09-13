"""AISStream.io vessel positions, collected as a bounded sampling window.

The zero-cost constraint forbids a long-lived process, so this is not a live consumer: it
connects, subscribes to the Philippine AOI, reads for a fixed number of seconds, and exits.
What reaches storage is therefore a *sample* of vessel traffic, never a complete voyage, and
everything downstream must treat it that way (README § Risks, coverage sparsity).

Four provider constraints shape this module:
  * browser connections are forbidden, so the key lives here and never reaches the client;
  * at most three subscribed connections per account and per originating IP, so one per run;
  * a complete subscription must arrive within three seconds of connecting, and an *invalid*
    subscription is answered with silence rather than an error — so the confirmation frame is
    checked, otherwise a rejected key would be recorded as "no vessel traffic";
  * messages are dropped if the client reads slowly, so frames are buffered in memory and
    written once at the end rather than uploaded during the window.

Each stored line wraps the verbatim upstream frame in a one-field envelope carrying the
collector's receive time. This is not a transformation: the frame bytes are spliced in
unparsed. It is necessary because nothing in an AIS position carries an absolute time —
`PositionReport.Timestamp` is the UTC *second of the minute* of the fix (0-59, with 60-63
reserved as status codes), and `MetaData` carries no date. Without the receive time no
sampled position could be placed in time at all.

The schema is beta and explicitly unstable, so every field is treated as optional.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Sequence

import websockets

from nightfall.clock import utc_now
from nightfall.config import Settings
from nightfall.geo import PH_AOI
from nightfall.ratelimit import AISSTREAM_QUOTA, TokenBucket
from nightfall.sources.base import (
    CommercialUse,
    Licence,
    RawRecord,
    SourceAdapter,
    SourceOutageError,
    as_integer,
    as_number,
    as_text,
)
from nightfall.store import RawStore

WS_ENDPOINT = "wss://stream.aisstream.io/v0/stream"

#: Message types worth the bandwidth. A narrow filter is the provider's own recommendation for
#: avoiding dropped frames. `ShipStaticData` is requested for vessel names and types; it
#: carries no position and is retained in `raw/` for later enrichment.
MESSAGE_TYPES = ("PositionReport", "ShipStaticData")

#: The provider closes the connection if a complete subscription has not arrived within three
#: seconds, and answers an invalid one with silence.
SUBSCRIBE_DEADLINE_S = 3.0
CONFIRMATION_TIMEOUT_S = 10.0

DEFAULT_WINDOW_S = 180.0

#: AIS `Timestamp` values at or above this are status codes, not seconds of the minute.
AIS_TIMESTAMP_UNAVAILABLE = 60


class AisStreamAdapter(SourceAdapter):
    name = "aisstream"
    licence = Licence(
        name="AISStream.io terms of use",
        url="https://aisstream.io/",
        commercial_use=CommercialUse.PROHIBITED,
        attribution="Vessel positions © aisstream.io",
    )
    quota = AISSTREAM_QUOTA

    def __init__(
        self,
        store: RawStore,
        settings: Settings,
        *,
        bucket: TokenBucket | None = None,
    ) -> None:
        super().__init__(store, settings, bucket=bucket)
        self._window_s = settings.ais_window_s
        key = settings.aisstream_api_key
        self._api_key = key.get_secret_value() if key is not None else None

    @property
    def window_s(self) -> float:
        return self._window_s

    def subscription(self) -> dict[str, object]:
        """The subscribe frame. Bounding boxes are [[lat, lon], [lat, lon]] pairs, not lon/lat."""
        if not self._api_key:
            raise SourceOutageError("AISSTREAM_API_KEY is not configured")
        return {
            "APIKey": self._api_key,
            "BoundingBoxes": [
                [[PH_AOI.south, PH_AOI.west], [PH_AOI.north, PH_AOI.east]],
            ],
            "FilterMessageTypes": list(MESSAGE_TYPES),
        }

    def request_key(self) -> str:
        return f"stream/ph/{self._window_s:.0f}s"

    async def collect(self) -> Sequence[RawRecord]:
        lines = await self._read_window()
        if not lines:
            raise SourceOutageError(
                f"aisstream delivered no frames in a {self._window_s:.0f}s window; "
                "recorded as a coverage gap rather than zero traffic"
            )
        return [
            RawRecord(
                source=self.name,
                request_key=self.request_key(),
                body=b"\n".join(lines) + b"\n",
                content_type="application/x-ndjson",
                # The object is stamped with the moment the window closed, which is what the
                # transform subtracts the declared window length from to bound the sample.
                observed_at=utc_now(),
            )
        ]

    async def _read_window(self) -> list[bytes]:
        subscribe = json.dumps(self.subscription()).encode("utf-8")
        await self._bucket.acquire()
        lines: list[bytes] = []
        try:
            async with websockets.connect(
                WS_ENDPOINT,
                compression="deflate",
                open_timeout=SUBSCRIBE_DEADLINE_S,
                user_agent_header=self._settings.user_agent,
            ) as socket:
                await socket.send(subscribe)

                # A rejected subscription produces no error frame, only silence, so the
                # timeout is the only signal available. Failing here is what stops a bad key
                # from being recorded as an empty ocean. Data frames that arrive before the
                # confirmation are kept, not discarded.
                confirmed = False
                with contextlib.suppress(TimeoutError):
                    async with asyncio.timeout(CONFIRMATION_TIMEOUT_S):
                        async for frame in socket:
                            raw = _as_bytes(frame)
                            if _is_confirmation(raw):
                                confirmed = True
                                break
                            lines.append(_envelope(raw))
                if not confirmed:
                    raise SourceOutageError(
                        "aisstream sent no SubscriptionConfirmation within "
                        f"{CONFIRMATION_TIMEOUT_S:.0f}s; the subscription or key was rejected, "
                        "which the provider signals by silence"
                    )

                with contextlib.suppress(TimeoutError):
                    async with asyncio.timeout(self._window_s):
                        async for frame in socket:
                            lines.append(_envelope(_as_bytes(frame)))
        except (OSError, websockets.WebSocketException) as exc:
            if not lines:
                raise SourceOutageError(f"aisstream connection failed: {exc}") from exc
            # A mid-window disconnect still yields a usable, shorter sample.
        return lines


def _is_confirmation(frame: bytes) -> bool:
    try:
        payload = json.loads(frame)
    except json.JSONDecodeError:
        return False
    return bool(payload.get("MessageType") == "SubscriptionConfirmation")


def _as_bytes(frame: str | bytes) -> bytes:
    """The service sends binary frames holding UTF-8 JSON; tolerate text frames as well."""
    return frame.encode("utf-8") if isinstance(frame, str) else frame


def _envelope(frame: bytes) -> bytes:
    """Splice the verbatim frame into a receive-time envelope without parsing it."""
    received = utc_now().timestamp()
    return b'{"received_unix":' + f"{received:.3f}".encode() + b',"frame":' + frame + b"}"


def normalise(payload: bytes) -> list[dict[str, object]]:
    """Flatten stored AISStream lines into position rows.

    Only `PositionReport` carries a position. Static data frames stay in `raw/` for later
    vessel-name enrichment and are skipped here.
    """
    rows: list[dict[str, object]] = []
    for line in payload.decode("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError:
            continue  # Beta feed: a malformed frame must not fail the batch.
        frame = envelope.get("frame") or {}
        if frame.get("MessageType") != "PositionReport":
            continue
        report = (frame.get("Message") or {}).get("PositionReport") or {}
        metadata = frame.get("MetaData") or {}
        lat = as_number(report.get("Latitude", metadata.get("Latitude")))
        lon = as_number(report.get("Longitude", metadata.get("Longitude")))
        if lon is None or lat is None:
            continue
        mmsi = as_text(report.get("UserID", metadata.get("MMSI")))
        if mmsi is None:
            continue  # A position with no vessel identity cannot join into a track.
        fix_second = as_integer(report.get("Timestamp"))
        rows.append(
            {
                "entity_id": mmsi,
                "label": as_text(metadata.get("ShipName")),
                "lon": lon,
                "lat": lat,
                "speed_kt": as_number(report.get("Sog")),
                "track_deg": as_number(report.get("Cog")),
                "nav_status": as_integer(report.get("NavigationalStatus")),
                # Absolute time comes from the envelope; the AIS field is a second of the
                # minute and is kept only so a fix can be aged against its receive time.
                "received_unix": as_number(envelope.get("received_unix")),
                "fix_second": (
                    fix_second
                    if fix_second is not None and fix_second < AIS_TIMESTAMP_UNAVAILABLE
                    else None
                ),
            }
        )
    return rows
