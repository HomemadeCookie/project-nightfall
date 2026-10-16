import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest

from nightfall.core.context import Context
from nightfall.core.lake import Lake
from nightfall.detect.ais import BERTH_KM, Fix, PortCall, detect_port_calls
from nightfall.detect.text_events import extract_fuel_adjustments, extract_sea_trip_notices
from nightfall.indicators.waits import port_waits
from nightfall.sources.ships import aisstream
from nightfall.stage import stage_all
from tests.helpers import NOW, put

T0 = datetime(2026, 10, 10, 0, 0, tzinfo=UTC)
PORT = (14.5916, 120.8724)  # Manila
OFFSHORE = (14.5916, 120.7)  # ~18 km west: outside the anchorage ring
ANCHORAGE = (14.5916, 120.82)  # ~5.6 km west: inside the ring, outside the berth zone


def track(mmsi, legs):
    """legs: [(minutes_from_T0, (lat, lon), sog)] -> Fix list."""
    return [Fix(mmsi, T0 + timedelta(minutes=m), pos[0], pos[1], sog) for m, pos, sog in legs]


def test_vessel_that_anchors_then_berths_has_a_wait():
    fixes = track(
        "111",
        [
            (0, OFFSHORE, 12),
            (60, ANCHORAGE, 0.3),
            (240, ANCHORAGE, 0.2),
            (600, PORT, 0.1),
            (900, PORT, 0.0),
            (1000, OFFSHORE, 12),
        ],
    )
    (call,) = detect_port_calls(fixes, "MNL", PORT)
    assert call.arrived_anchorage == T0 + timedelta(minutes=60)
    assert call.berth_start == T0 + timedelta(minutes=600)
    assert call.wait_hours == 9.0
    assert call.departed == T0 + timedelta(minutes=1000)


def test_direct_berthing_has_no_wait_but_is_a_call():
    fixes = track(
        "222",
        [
            (0, OFFSHORE, 10),
            (30, (14.592, 120.86), 6),
            (60, PORT, 0.2),
            (400, PORT, 0.1),
            (500, OFFSHORE, 11),
        ],
    )
    (call,) = detect_port_calls(fixes, "MNL", PORT)
    assert call.arrived_anchorage is None and call.wait_hours is None and call.berth_start


def test_flybys_are_not_calls():
    fixes = track("333", [(0, OFFSHORE, 14), (20, (14.60, 120.80), 12), (40, OFFSHORE, 14)])
    assert detect_port_calls(fixes, "MNL", PORT) == []
    brief = track("334", [(0, OFFSHORE, 14), (10, PORT, 0.2), (20, PORT, 0.2), (30, OFFSHORE, 14)])
    assert detect_port_calls(brief, "MNL", PORT) == []  # 10 minutes alongside is below the dwell floor


def test_ships_are_tracked_independently_and_repeat_visits_split_on_gaps():
    a = track(
        "A",
        [(0, OFFSHORE, 10), (30, ANCHORAGE, 0.2), (200, PORT, 0.1), (400, PORT, 0.0), (500, OFFSHORE, 10)],
    )
    b = track("B", [(0, OFFSHORE, 10), (30, ANCHORAGE, 0.2), (360, ANCHORAGE, 0.1), (400, OFFSHORE, 9)])
    again = track(
        "A",
        [
            (60 * 24 * 3, ANCHORAGE, 0.2),
            (60 * 24 * 3 + 120, ANCHORAGE, 0.2),
            (60 * 24 * 3 + 200, PORT, 0.1),
            (60 * 24 * 3 + 400, PORT, 0.1),
            (60 * 24 * 3 + 500, OFFSHORE, 10),
        ],
    )
    calls = detect_port_calls(a + b + again, "MNL", PORT)
    assert sorted(c.mmsi for c in calls) == ["A", "A", "B"]
    assert next(c for c in calls if c.mmsi == "B").berth_start is None  # anchored then left


def test_geofence_constants_are_sane():
    assert 0 < BERTH_KM < 10
    assert PortCall("x", "p", T0, T0 + timedelta(hours=3), None, None).wait_hours == 3.0
    assert (
        PortCall("x", "p", T0 + timedelta(hours=3), T0, None, None).wait_hours is None
    )  # berth before anchorage


# -- AIS staging and the wait indicator ----------------------------------------------------------
def ais_msg(mmsi, t, lat, lon, sog):
    return {
        "MessageType": "PositionReport",
        "MetaData": {
            "MMSI": mmsi,
            "time_utc": t.strftime("%Y-%m-%d %H:%M:%S.123456 +0000 UTC"),
            "ShipName": "X",
        },
        "Message": {
            "PositionReport": {
                "Latitude": lat,
                "Longitude": lon,
                "Sog": sog,
                "Cog": 90,
                "NavigationalStatus": 1,
                "UserID": mmsi,
            }
        },
    }


def test_message_compaction():
    kind, rec = aisstream.compact(ais_msg(123, T0, 14.5, 120.9, 0.4))
    assert kind == "positions" and rec == {
        "mmsi": "123",
        "t": "2026-10-10T00:00:00Z",
        "lat": 14.5,
        "lon": 120.9,
        "sog": 0.4,
        "cog": 90,
        "nav": 1,
    }
    static = {
        "MessageType": "ShipStaticData",
        "MetaData": {"MMSI": 9, "ShipName": "MV TEST ", "time_utc": ""},
        "Message": {
            "ShipStaticData": {
                "Type": 70,
                "Destination": "PHMNL ",
                "MaximumStaticDraught": 9.5,
                "Dimension": {"A": 150, "B": 30, "C": 10, "D": 10},
            }
        },
    }
    kind, rec = aisstream.compact(static)
    assert (
        kind == "static"
        and rec["name"] == "MV TEST"
        and rec["destination"] == "PHMNL"
        and rec["length"] == 180.0
    )
    assert aisstream.compact({"MessageType": "Other"}) is None


class FakeWs:
    def __init__(self, messages):
        self.messages, self.sent = list(messages), []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def send(self, data):
        self.sent.append(json.loads(data))

    async def recv(self):
        if not self.messages:
            raise ConnectionError("closed")
        return json.dumps(self.messages.pop(0))


def test_listener_subscribes_buffers_and_survives_garbage():
    msgs = [
        ais_msg(1, T0, 14.5, 120.9, 0.3),
        "not json at all",
        {"MessageType": "Other"},
        ais_msg(2, T0, 14.6, 120.8, 5.0),
    ]
    ws = FakeWs([m if isinstance(m, dict) else m for m in msgs])
    ws.messages = [m for m in msgs]

    async def recv():
        if not ws.messages:
            raise ConnectionError
        m = ws.messages.pop(0)
        return m if isinstance(m, str) else json.dumps(m)

    ws.recv = recv
    buf = asyncio.run(aisstream.listen("KEY", 5.0, connect=lambda: ws))
    assert len(buf.records["positions"]) == 2
    assert ws.sent[0]["APIKey"] == "KEY" and ws.sent[0]["BoundingBoxes"] == aisstream.BOUNDING_BOX


def test_source_without_a_key_yields_nothing(monkeypatch):
    monkeypatch.delenv("AISSTREAM_API_KEY", raising=False)
    from nightfall.core.http import Http

    assert list(aisstream.AisStream(Http()).fetch(NOW)) == []


def seed_ais(lake, n_ships=4, wait_h=5):
    recs = []
    for i in range(n_ships):
        base = NOW - timedelta(days=2, hours=i * 6)
        legs = [
            (0, OFFSHORE, 12),
            (30, ANCHORAGE, 0.3),
            (30 + wait_h * 60, ANCHORAGE, 0.2),
            (40 + wait_h * 60, PORT, 0.1),
            (40 + wait_h * 60 + 240, PORT, 0.0),
            (40 + wait_h * 60 + 300, OFFSHORE, 12),
        ]
        # sample every 20 minutes so the track is dense
        for m in range(0, legs[-1][0] + 1, 20):
            leg = next(l for l in reversed(legs) if l[0] <= m)
            recs.append(
                {
                    "mmsi": f"9{i}",
                    "t": (base + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "lat": leg[1][0],
                    "lon": leg[1][1],
                    "sog": leg[2],
                    "cog": 0,
                    "nav": 1,
                }
            )
    put(lake, "aisstream", "positions", recs)


def test_wait_summary_from_staged_ais(lake_dir):
    lake = Lake(lake_dir)
    seed_ais(lake)
    stage_all(lake)
    w = port_waits(Context.from_lake(lake, NOW), "MNL", PORT)
    assert w.vessels_seen == 4 and w.waits_measured == 4
    assert w.median_wait_h == pytest.approx(5.0, abs=0.5)


def test_wait_summary_withholds_a_median_from_too_few_ships(lake_dir):
    lake = Lake(lake_dir)
    seed_ais(lake, n_ships=2)
    stage_all(lake)
    w = port_waits(Context.from_lake(lake, NOW), "MNL", PORT)
    assert w.waits_measured == 2 and w.median_wait_h is None


def test_ports_answer_gains_ais_wait_when_available(lake_dir):
    from nightfall.answers.questions import ports_pressure
    from tests.helpers import seed_ports

    lake = Lake(lake_dir)
    seed_ports(lake)
    seed_ais(lake)
    stage_all(lake)
    a = {x.scope["port"]: x for x in ports_pressure.run(Context.from_lake(lake, NOW))}["MNL"]
    assert a.value["ais"]["median_wait_h"] == pytest.approx(5.0, abs=0.5)
    assert "aisstream" in a.sources
    assert not any("needs live AIS" in c for c in a.caveats)
    assert ports_pressure.run(Context.from_lake(lake, NOW))[1].value["ais"] is None  # no ships near Batangas


# -- text events -----------------------------------------------------------------------------
FRI = datetime(2026, 10, 16, 2, 0, tzinfo=UTC)  # Friday 10:00 Manila


def headline(title, url="https://x/1", published=FRI):
    return {"title": title, "url": url, "published": published, "teaser": ""}


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Diesel prices to go down by P1.25 per liter next week", [("diesel", -1.25)]),
        ("Oil firms announce P0.80 per liter hike in gasoline", [("gasoline", 0.80)]),
        ("Gasoline up by P1.10/liter, diesel down P0.65/L", [("gasoline", 1.10), ("diesel", -0.65)]),
        ("Rollback of ₱2.40 per liter for diesel expected Tuesday", [("diesel", -2.40)]),
        ("Fuel prices expected to change next week", []),
        ("Diesel P1.00 per liter", []),  # no direction: not trusted
    ],
)
def test_fuel_adjustment_extraction(title, expected):
    got = [(e["product"], e["delta_php_l"]) for e in extract_fuel_adjustments([headline(title)])]
    assert got == expected


def test_effective_date_is_the_next_tuesday():
    (e,) = extract_fuel_adjustments([headline("Diesel up by P1.00 per liter")])
    assert e["effective_date"].isoformat() == "2026-10-20"
    tue = datetime(2026, 10, 20, 0, 30, tzinfo=UTC)  # Tuesday 08:30 Manila: the day it takes effect
    (e2,) = extract_fuel_adjustments([headline("Diesel up by P1.00 per liter", published=tue)])
    assert e2["effective_date"].isoformat() == "2026-10-20"


def test_sea_trip_notices_name_the_corridor():
    items = [
        headline("Sea trips suspended in Matnog as storm nears"),
        headline("PCG lifts ban; sailings resume in Batangas port"),
        headline("Peso weakens against dollar"),
        headline("Ferry fare hike approved"),
    ]
    out = extract_sea_trip_notices(items)
    assert [(e["kind"], e["routes"]) for e in out] == [
        ("suspended", ["matnog-allen"]),
        ("resumed", ["batangas-calapan"]),
    ]
