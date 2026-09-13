"""globe_history traces, replayed from a recorded fixture. No network."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from nightfall.config import Settings
from nightfall.geo import PH_AOI
from nightfall.sources.adsb_history import (
    is_full_trace_member,
    last_observed_at,
    parse_trace,
    records_from_tar,
    release_tag,
    seed_trace,
    trace_intersects_aoi,
)
from nightfall.store import LocalRawStore

FIXTURE = Path(__file__).parent / "fixtures" / "adsb_lol_trace_manila.json"


@pytest.fixture
def trace_payload() -> bytes:
    return FIXTURE.read_bytes()


def test_parse_trace_keeps_observed_times_and_does_not_interpolate(trace_payload: bytes) -> None:
    rows = parse_trace(trace_payload)
    assert [row["entity_id"] for row in rows] == ["75832a"] * 7
    assert rows[0]["observed_unix"] == 1_757_635_200.0
    assert rows[1]["observed_unix"] == 1_757_635_220.0
    assert rows[-1]["lat"] == 1.0
    # Every surviving fix was in the file. Nothing was invented between 80s and 400s.
    assert [row["observed_unix"] for row in rows] == [
        1_757_635_200.0 + offset for offset in (0.0, 20.0, 40.0, 60.0, 80.0, 400.0, 800.0)
    ]


def test_trace_intersects_aoi_is_true_for_the_manila_fixture(trace_payload: bytes) -> None:
    assert trace_intersects_aoi(trace_payload)
    assert PH_AOI.contains(121.0198, 14.5089)


def test_a_trace_wholly_outside_the_aoi_is_rejected() -> None:
    document = {
        "icao": "abc123",
        "timestamp": 1_757_635_200.0,
        "trace": [[0.0, 51.5, -0.1, 30000, 400, 90]],
    }
    assert not trace_intersects_aoi(json.dumps(document).encode())


def test_last_observed_at_is_timezone_aware(trace_payload: bytes) -> None:
    moment = last_observed_at(trace_payload)
    assert moment.tzinfo is UTC
    assert moment == datetime(2025, 9, 12, 0, 13, 20, tzinfo=UTC)


def test_release_tag_matches_adsblol_dots_not_iso_hyphens() -> None:
    assert release_tag(date(2026, 9, 12), "planes-readsb-prod-0") == (
        "v2026.09.12-planes-readsb-prod-0"
    )


def test_full_trace_members_are_recognised() -> None:
    assert is_full_trace_member("2026/09/12/traces/75/trace_full_75832a.json")
    assert not is_full_trace_member("2026/09/12/traces/75/trace_recent_75832a.json")
    assert not is_full_trace_member("2026/09/12/heatmap/00.bin")


def test_seed_trace_writes_immutable_raw(settings: Settings, trace_payload: bytes) -> None:
    path = seed_trace(LocalRawStore(settings.raw_root), trace_payload)
    assert path.startswith("raw/adsb_lol/dt=2025-09-12/")
    written = settings.raw_root / path
    assert written.is_file()
    with pytest.raises(FileExistsError, match="immutable"):
        seed_trace(LocalRawStore(settings.raw_root), trace_payload)


def test_records_from_tar_keep_only_aoi_traces(tmp_path: Path, trace_payload: bytes) -> None:
    import io
    import tarfile

    outside = json.dumps(
        {
            "icao": "ffff01",
            "timestamp": 1_757_635_200.0,
            "trace": [[0.0, 40.7, -74.0, 30000, 400, 90]],
        }
    ).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, body in (
            ("2025/09/12/traces/75/trace_full_75832a.json", trace_payload),
            ("2025/09/12/traces/ff/trace_full_ffff01.json", outside),
            ("2025/09/12/traces/75/trace_recent_75832a.json", trace_payload),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    buffer.seek(0)
    records = records_from_tar(buffer, day=date(2025, 9, 12))
    assert len(records) == 1
    assert records[0].request_key.endswith("75832a")
    assert json.loads(records[0].body)["icao"] == "75832a"
