"""AISStream frame parsing.

The stored format is the provider's verbatim frame inside a receive-time envelope, because no
AIS position carries an absolute time of its own.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from nightfall.config import Settings
from nightfall.sources import aisstream
from nightfall.sources.base import SourceOutageError
from nightfall.store import LocalRawStore


def _envelope(frame: Mapping[str, object], received: float = 1_789_147_749.5) -> bytes:
    return json.dumps({"received_unix": received, "frame": frame}).encode()


def _position(**overrides: object) -> dict[str, object]:
    report: dict[str, object] = {
        "MessageID": 1,
        "UserID": 368207620,
        "Valid": True,
        "NavigationalStatus": 0,
        "Sog": 12.4,
        "Cog": 86.7,
        "Longitude": 120.98,
        "Latitude": 14.58,
        "TrueHeading": 87,
        "Timestamp": 42,
    }
    report.update(overrides)
    return {
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": 368207620, "ShipName": " EXAMPLE VESSEL "},
        "Message": {"PositionReport": report},
    }


def test_position_report_is_read() -> None:
    row = aisstream.normalise(_envelope(_position()))[0]
    assert row["entity_id"] == "368207620"
    assert row["label"] == "EXAMPLE VESSEL"
    assert row["lon"] == 120.98
    assert row["speed_kt"] == 12.4
    assert row["received_unix"] == 1_789_147_749.5
    assert row["fix_second"] == 42


def test_static_data_carries_no_position() -> None:
    frame = {"MessageType": "ShipStaticData", "MetaData": {}, "Message": {"ShipStaticData": {}}}
    assert aisstream.normalise(_envelope(frame)) == []


def test_malformed_line_does_not_fail_the_batch() -> None:
    payload = b"not json\n" + _envelope(_position()) + b"\n\n"
    assert len(aisstream.normalise(payload)) == 1


def test_unavailable_fix_second_is_dropped() -> None:
    """AIS `Timestamp` 60 and above are status codes, not seconds of the minute."""
    row = aisstream.normalise(_envelope(_position(Timestamp=60)))[0]
    assert row["fix_second"] is None


def test_position_without_identity_is_dropped() -> None:
    frame = _position()
    frame["MetaData"] = {}
    report = frame["Message"]["PositionReport"]  # type: ignore[index]
    del report["UserID"]
    assert aisstream.normalise(_envelope(frame)) == []


def test_subscription_bounding_box_is_latitude_first() -> None:
    settings = Settings(aisstream_api_key="test-key")
    adapter = aisstream.AisStreamAdapter(LocalRawStore.__new__(LocalRawStore), settings)
    box = adapter.subscription()["BoundingBoxes"][0]  # type: ignore[index]
    (south, west), (north, east) = box
    assert south < north
    assert west < east
    # Latitudes are bounded by 90; a lon/lat ordering would put 116 in the first slot.
    assert abs(south) <= 90.0 and abs(north) <= 90.0


def test_missing_key_is_an_outage_not_a_crash() -> None:
    adapter = aisstream.AisStreamAdapter(LocalRawStore.__new__(LocalRawStore), Settings())
    try:
        adapter.subscription()
    except SourceOutageError as outage:
        assert "AISSTREAM_API_KEY" in str(outage)
    else:  # pragma: no cover - the assertion below reports the real failure
        raise AssertionError("a missing key must be reported as an outage")


def test_confirmation_frame_is_recognised() -> None:
    confirmation = json.dumps(
        {"MessageType": "SubscriptionConfirmation", "Message": {"CompressionEnabled": True}}
    ).encode()
    assert aisstream._is_confirmation(confirmation) is True
    assert aisstream._is_confirmation(json.dumps(_position()).encode()) is False
    assert aisstream._is_confirmation(b"{broken") is False
