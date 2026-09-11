"""Shared fixtures.

No test in this suite touches the network (`.cursorrules` § 5). The adsb.lol fixture is a real
response captured near Manila; the AIS fixture is built from the provider's published schema
because the stream needs a key, and it is named so that nobody mistakes it for a capture.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nightfall.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"

#: The instant the recorded adsb.lol response was assembled, in Unix seconds.
FIXTURE_EPOCH_S = 1_789_147_749.5
FIXTURE_AT = datetime.fromtimestamp(FIXTURE_EPOCH_S, tz=UTC)


@pytest.fixture
def adsb_payload() -> bytes:
    return (FIXTURES / "adsb_lol_point_manila.json").read_bytes()


@pytest.fixture
def adsb_document(adsb_payload: bytes) -> dict[str, object]:
    document: dict[str, object] = json.loads(adsb_payload)
    return document


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_root=tmp_path, run_id="test-run")


def sweep_payload(document: dict[str, object], *, sweep: int, interval_s: float) -> bytes:
    """One synthetic later sweep of the recorded response.

    Advances the response instant and flies every airborne aircraft forward at its reported
    ground speed, along a gently curving course. This is the shape a real collection window
    has — the same aircraft seen repeatedly, seconds apart — and it is the only way to
    exercise segmentation and simplification without either a live upstream or a hand-drawn
    path that proves nothing about either.

    The course curves rather than running dead straight because a straight line simplifies to
    its two endpoints at every tolerance, which would make the zoom tiers indistinguishable
    and hide a broken tolerance calculation.
    """
    import math

    moved = json.loads(json.dumps(document))
    elapsed = sweep * interval_s
    moved["now"] = float(document["now"]) + elapsed * 1000.0  # type: ignore[arg-type]
    for aircraft in moved["ac"]:
        speed_kt = aircraft.get("gs")
        track_deg = aircraft.get("track")
        if not isinstance(speed_kt, int | float) or not isinstance(track_deg, int | float):
            continue
        # Deterministic per-aircraft turn rate, within the 3 deg/s of a standard rate turn.
        turn_rate = ((int(str(aircraft.get("hex", "0")), 16) % 7) - 3) * 0.4
        lat, lon = aircraft["lat"], aircraft["lon"]
        for step in range(sweep):
            bearing = math.radians(track_deg + turn_rate * step * interval_s)
            leg_nm = speed_kt * (interval_s / 3600.0)
            lat += (leg_nm / 60.0) * math.cos(bearing)
            lon += (leg_nm / 60.0) * math.sin(bearing) / math.cos(math.radians(lat))
        aircraft["lat"], aircraft["lon"] = lat, lon
        aircraft["seen_pos"] = 0.5
    return json.dumps(moved).encode("utf-8")


def ais_frames(
    *,
    vessels: int = 3,
    reports: int = 5,
    interval_s: float = 30.0,
    start: datetime = FIXTURE_AT,
) -> bytes:
    """A window of enveloped AISStream frames, in the landing zone's newline-delimited form.

    Built from the provider's published schema rather than captured, because the stream needs
    a key. Each vessel drifts north-east at a steady few knots, which is enough to exercise
    segmentation without pretending to be a real voyage.

    One `ShipStaticData` frame is included: it carries no position and must be filtered out
    rather than becoming a vessel parked at 0°N 0°E.
    """
    lines: list[bytes] = []
    for vessel in range(vessels):
        mmsi = 548_000_000 + vessel
        for report in range(reports):
            received = start.timestamp() + report * interval_s
            frame = {
                "MessageType": "PositionReport",
                "MetaData": {
                    "MMSI": mmsi,
                    "ShipName": f"MV FIXTURE {vessel}",
                    "latitude": 12.0 + vessel * 0.2,
                    "longitude": 121.0 + vessel * 0.2,
                },
                "Message": {
                    "PositionReport": {
                        "UserID": mmsi,
                        "Latitude": 12.0 + vessel * 0.2 + report * 0.01,
                        "Longitude": 121.0 + vessel * 0.2 + report * 0.012,
                        "Sog": 9.5,
                        "Cog": 48.0,
                        "NavigationalStatus": 0,
                        "Timestamp": int(received) % 60,
                    }
                },
            }
            lines.append(
                b'{"received_unix":'
                + f"{received:.3f}".encode()
                + b',"frame":'
                + json.dumps(frame).encode()
                + b"}"
            )
    static = {
        "MessageType": "ShipStaticData",
        "MetaData": {"MMSI": 548_000_000, "ShipName": "MV FIXTURE 0"},
        "Message": {"ShipStaticData": {"UserID": 548_000_000, "Name": "MV FIXTURE 0"}},
    }
    lines.append(
        b'{"received_unix":'
        + f"{start.timestamp():.3f}".encode()
        + b',"frame":'
        + json.dumps(static).encode()
        + b"}"
    )
    return b"\n".join(lines) + b"\n"


def seed_ais_window(settings: Settings, *, window_s: float = 180.0) -> str:
    """Write one AIS sampling window into the landing zone."""
    from nightfall.store import LocalRawStore

    return LocalRawStore(settings.raw_root).put(
        source="aisstream",
        request_key=f"stream/ph/{window_s:.0f}s",
        body=ais_frames(),
        # The object is stamped with the moment the window closed, which is what the transform
        # subtracts the declared window length from.
        observed_at=FIXTURE_AT + timedelta(seconds=window_s),
        content_type="application/x-ndjson",
    )


def seed_window(
    settings: Settings,
    document: dict[str, object],
    *,
    sweeps: int = 6,
    interval_s: float = 20.0,
) -> list[str]:
    """Fill the landing zone as a full ADS-B sampling window would."""
    from nightfall.store import LocalRawStore

    store = LocalRawStore(settings.raw_root)
    written = []
    for sweep in range(sweeps):
        written.append(
            store.put(
                source="adsb_lol",
                request_key="point/14.5/121.0/250",
                body=sweep_payload(document, sweep=sweep, interval_s=interval_s),
                observed_at=FIXTURE_AT + timedelta(seconds=sweep * interval_s),
                content_type="application/json",
            )
        )
    return written
