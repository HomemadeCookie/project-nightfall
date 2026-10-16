from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from nightfall.core import geo
from nightfall.core.envelope import Envelope
from nightfall.core.http import Http
from nightfall.core.lake import Lake
from nightfall.core.license import License, blocking, merge
from nightfall.core.time import iso, next_weekday, parse_iso, to_manila

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


def env(payload, source="eia", dataset="spot_prices", at=NOW, request=None):
    return Envelope(
        source=source,
        dataset=dataset,
        license=[License.PUBLIC_DOMAIN],
        fetched_at=at,
        request=request or {},
        payload=payload,
    )


# -- licences -------------------------------------------------------------------------------
def test_blocking_flags_only_unsafe_licences():
    assert blocking({License.ATTRIBUTION, License.PUBLIC_DOMAIN}) == set()
    assert blocking([License.NON_COMMERCIAL, License.ATTRIBUTION]) == {License.NON_COMMERCIAL}
    assert blocking([License.UNCLEAR]) == {License.UNCLEAR}


def test_merge_is_a_stable_union():
    assert merge([License.ATTRIBUTION], [License.PUBLIC_DOMAIN, License.ATTRIBUTION]) == [
        License.ATTRIBUTION,
        License.PUBLIC_DOMAIN,
    ]


# -- time -----------------------------------------------------------------------------------
def test_time_helpers():
    assert parse_iso("2026-10-16T01:00:00Z") == datetime(2026, 10, 16, 1, tzinfo=UTC)
    assert parse_iso("2026-10-16T01:00:00").tzinfo is not None
    assert iso(datetime(2026, 10, 16, 1, 2, 3, tzinfo=UTC)) == "2026-10-16T01:02:03Z"
    assert to_manila(datetime(2026, 10, 16, 20, tzinfo=UTC)).day == 17  # UTC+8
    assert next_weekday(date(2026, 10, 16), 1) == date(2026, 10, 20)  # Friday -> next Tuesday
    assert next_weekday(date(2026, 10, 20), 1) == date(2026, 10, 27)  # strictly after


# -- envelope & lake ------------------------------------------------------------------------
def test_envelope_hash_ignores_key_order():
    assert env({"a": 1, "b": 2}).payload_sha256 == env({"b": 2, "a": 1}).payload_sha256
    assert env({"a": 1}).payload_sha256 != env({"a": 2}).payload_sha256


def test_write_raw_partitions_and_is_idempotent(lake_dir):
    lake = Lake(lake_dir)
    first = lake.write_raw([env([{"x": 1}])])
    again = lake.write_raw([env([{"x": 1}])])
    assert len(first) == 1 and again == []
    assert "source=eia/dataset=spot_prices/date=2026-10-16/hour=12" in str(first[0])
    assert lake.has_raw("eia", "spot_prices") and not lake.has_raw("eia", "nope")


def test_iter_raw_round_trips_json_oldest_first(lake_dir):
    lake = Lake(lake_dir)
    later = datetime(2026, 10, 17, 1, tzinfo=UTC)
    lake.write_raw([env({"n": 2}, at=later), env({"n": 1})])
    rows = lake.iter_raw("eia", "spot_prices")
    assert [r["payload"]["n"] for r in rows] == [1, 2]
    assert rows[0]["fetched_at"] == NOW


def test_known_requests(lake_dir):
    lake = Lake(lake_dir)
    lake.write_raw([env({"t": "a"}, request={"url": "u1"}), env({"t": "b"}, request={"url": "u2"})])
    assert lake.known_requests("eia", "spot_prices", "url") == {"u1", "u2"}
    assert lake.known_requests("eia", "missing", "url") == set()


def test_unsafe_identifiers_are_rejected(lake_dir):
    with pytest.raises(ValueError):
        Lake(lake_dir).write_raw([env({}, source="../etc")])


def test_connect_exposes_raw_and_derived_views(lake_dir):
    import pyarrow as pa

    lake = Lake(lake_dir)
    lake.write_raw([env({"k": 1})])
    lake.write_table("staging", "demo", pa.table({"a": [1, 2]}))
    con = lake.connect()
    assert con.execute('SELECT count(*) FROM "raw_eia__spot_prices"').fetchone()[0] == 1
    assert con.execute('SELECT sum(a) FROM "staging_demo"').fetchone()[0] == 3
    assert con.execute("SELECT current_setting('TimeZone')").fetchone()[0] == "UTC"


# -- http -----------------------------------------------------------------------------------
def make_http(handler, **kw):
    sleeps = []
    http = Http(transport=httpx.MockTransport(handler), sleep=sleeps.append, **kw)
    return http, sleeps


def test_http_retries_server_errors_then_succeeds():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json={"ok": True})

    http, sleeps = make_http(handler)
    assert http.get_json("https://x.test/a") == {"ok": True}
    assert len(calls) == 3 and len(sleeps) == 2


def test_http_429_waits_for_retry_after():
    calls = []

    def handler(req):
        calls.append(1)
        return (
            httpx.Response(429, headers={"retry-after": "9"})
            if len(calls) == 1
            else httpx.Response(200, text="ok")
        )

    http, sleeps = make_http(handler)
    assert http.get("https://x.test/a").text == "ok"
    assert sleeps == [9.0]


def test_http_gives_up_after_retries():
    http, _ = make_http(lambda req: httpx.Response(500), retries=2)
    with pytest.raises(httpx.HTTPStatusError):
        http.get("https://x.test/a")


def test_http_client_errors_are_not_retried():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(404)

    http, _ = make_http(handler)
    with pytest.raises(httpx.HTTPStatusError):
        http.get("https://x.test/a")
    assert len(calls) == 1


def test_http_spaces_requests_per_host():
    t = [0.0]
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        t[0] += s

    http = Http(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="x")),
        min_interval={"x.test": 5.0},
        sleep=sleep,
        clock=lambda: t[0],
    )
    http.get("https://x.test/1")
    http.get("https://x.test/2")
    assert sleeps == [5.0]


# -- geo ------------------------------------------------------------------------------------
def test_haversine_manila_to_cebu():
    assert 560 < geo.haversine_km((14.5995, 120.9842), (10.3157, 123.8854)) < 580


def test_point_in_polygon():
    square = [(0, 0), (0, 10), (10, 10), (10, 0)]
    assert geo.point_in_polygon((5, 5), square)
    assert not geo.point_in_polygon((11, 5), square)


def test_distance_to_polyline_uses_closest_segment():
    line = [(0.0, 0.0), (0.0, 1.0)]  # along the equator, ~111 km long
    assert geo.distance_to_polyline_km((0.5, 0.5), line) == pytest.approx(55.6, abs=1.0)
    assert geo.distance_to_polyline_km((0.0, 2.0), line) == pytest.approx(111.2, abs=1.5)  # beyond the end


def test_sample_polyline_includes_endpoints_and_spacing():
    pts = geo.sample_polyline([(0.0, 0.0), (0.0, 1.0)], step_km=25.0)
    assert pts[0] == (0.0, 0.0) and pts[-1] == (0.0, 1.0)
    assert len(pts) == 6  # ceil(111/25)=5 segments


def test_h3_cell_is_stable():
    assert geo.cell(14.6, 121.0, 7) == geo.cell(14.6, 121.0, 7)
    assert geo.cell(14.6, 121.0, 7) != geo.cell(10.3, 123.9, 7)


# -- snapshot dedup, fetch log, pruning --------------------------------------------------------------
def test_skip_known_drops_identical_payloads_only(lake_dir):
    lake = Lake(lake_dir)
    lake.write_raw([env({"big": "file"})])
    assert (
        lake.write_raw([env({"big": "file"}, at=datetime(2026, 10, 17, 3, tzinfo=UTC))], skip_known=True)
        == []
    )
    changed = lake.write_raw(
        [env({"big": "file v2"}, at=datetime(2026, 10, 17, 3, tzinfo=UTC))], skip_known=True
    )
    assert len(changed) == 1
    # without the flag, an identical payload in a new hour is still kept (forecasts legitimately repeat)
    assert len(lake.write_raw([env({"big": "file"}, at=datetime(2026, 10, 17, 9, tzinfo=UTC))])) == 1


def test_fetch_log_records_attempts_and_successes(lake_dir):
    lake = Lake(lake_dir)
    lake.record_fetch("eia", NOW)
    lake.record_fetch("eia", NOW + timedelta(hours=1), ok=False)
    entry = lake.fetch_log()["eia"]
    assert entry["last_success"] == "2026-10-16T12:00:00Z" and entry["last_attempt"] == "2026-10-16T13:00:00Z"
    assert Lake(lake_dir / "other").fetch_log() == {}


def test_prune_raw_removes_only_old_partitions(lake_dir):
    lake = Lake(lake_dir)
    old = datetime(2026, 1, 1, 5, tzinfo=UTC)
    lake.write_raw([env({"n": 1}, at=old), env({"n": 2}, at=NOW)])
    assert lake.prune_raw("eia", datetime(2026, 6, 1, tzinfo=UTC)) == 1
    assert [r["payload"]["n"] for r in lake.iter_raw("eia", "spot_prices")] == [2]
    assert not (lake_dir / "raw" / "source=eia" / "dataset=spot_prices" / "date=2026-01-01").exists()
