"""adsb.lol response parsing, against the recorded response."""

from __future__ import annotations

import json

import pytest

from nightfall.sources import adsb_lol


def test_now_is_read_as_milliseconds(adsb_document: dict[str, object]) -> None:
    seconds = adsb_lol.response_unix(adsb_document)
    assert 1_700_000_000.0 < seconds < 1_900_000_000.0


def test_now_in_seconds_is_rejected(adsb_document: dict[str, object]) -> None:
    """A provider that switched to seconds must fail the collection, not shift the data.

    Without this, every timestamp lands in 1970, the rows never intersect the window the UI
    asks for, and the layer looks empty for a reason nothing reports.
    """
    document = {**adsb_document, "now": 1_789_147_749.5}
    with pytest.raises(ValueError, match="not milliseconds"):
        adsb_lol.response_unix(document)


def test_missing_now_falls_back_then_raises(adsb_document: dict[str, object]) -> None:
    document = {key: value for key, value in adsb_document.items() if key != "now"}
    assert adsb_lol.response_unix(document, 42.0) == 42.0
    with pytest.raises(ValueError, match="no usable"):
        adsb_lol.response_unix(document)


def test_normalise_reads_the_recorded_response(adsb_payload: bytes) -> None:
    rows = adsb_lol.normalise(adsb_payload)
    assert len(rows) == 12
    assert all(isinstance(row["lon"], float) for row in rows)
    # Every observation predates the response instant, because each is aged by its own fix.
    response_s = adsb_lol.response_unix(json.loads(adsb_payload))
    assert all(float(row["observed_unix"]) <= response_s for row in rows)  # type: ignore[arg-type]


def test_grounded_aircraft_has_no_altitude(adsb_payload: bytes) -> None:
    """`alt_baro` is the string "ground" on the surface, which is not an altitude."""
    document = json.loads(adsb_payload)
    grounded = dict(document["ac"][0])
    grounded.update({"hex": "abc123", "alt_baro": "ground", "gs": 0.0})
    payload = json.dumps({**document, "ac": [grounded]}).encode()

    row = adsb_lol.normalise(payload)[0]
    assert row["on_ground"] is True
    assert row["altitude_ft"] is None


def test_callsign_is_unpadded(adsb_payload: bytes) -> None:
    """`flight` is space-padded on the wire; untrimmed it would not match between polls."""
    document = json.loads(adsb_payload)
    padded = {**document["ac"][0], "flight": "PAL400  "}
    row = adsb_lol.normalise(json.dumps({**document, "ac": [padded]}).encode())[0]
    assert row["callsign"] == "PAL400"


def test_fix_age_is_subtracted(adsb_payload: bytes) -> None:
    document = json.loads(adsb_payload)
    aircraft = {**document["ac"][0], "seen_pos": 30.0}
    row = adsb_lol.normalise(json.dumps({**document, "ac": [aircraft]}).encode())[0]
    assert float(row["observed_unix"]) == pytest.approx(  # type: ignore[arg-type]
        adsb_lol.response_unix(document) - 30.0
    )


def test_positionless_aircraft_are_dropped(adsb_payload: bytes) -> None:
    document = json.loads(adsb_payload)
    aircraft = {key: value for key, value in document["ac"][0].items() if key not in {"lat", "lon"}}
    assert adsb_lol.normalise(json.dumps({**document, "ac": [aircraft]}).encode()) == []


def test_coverage_circles_stay_within_the_provider_limit() -> None:
    from nightfall.config import Settings
    from nightfall.store import LocalRawStore

    adapter = adsb_lol.AdsbLolAdapter(LocalRawStore.__new__(LocalRawStore), Settings())
    assert adapter.circles
    assert all(circle.radius_nm <= adsb_lol.MAX_RADIUS_NM for circle in adapter.circles)
    # Distinct request keys, or one sweep would collide with itself in the landing zone.
    keys = {adapter.request_key(circle) for circle in adapter.circles}
    assert len(keys) == len(adapter.circles)


def test_sweep_count_follows_the_window() -> None:
    from nightfall.config import Settings
    from nightfall.store import LocalRawStore

    settings = Settings(adsb_window_s=180.0, adsb_sweep_interval_s=20.0)
    adapter = adsb_lol.AdsbLolAdapter(LocalRawStore.__new__(LocalRawStore), settings)
    assert adapter.sweep_count == 9
