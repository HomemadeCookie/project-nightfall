"""Port-call detection from AIS positions: anchorage arrival, berthing, departure, and the wait.

Geofences are circles around each port's position (from PortWatch): a berth zone and a wider
anchorage ring. A vessel is "waiting" when it is slow inside the anchorage ring but outside the berth
zone; "alongside" when it is stopped inside the berth zone. Circles are a deliberately simple v1:
real quay polygons can replace them without changing the output.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from nightfall.core.geo import haversine_km

BERTH_KM, ANCHORAGE_KM = 3.0, 15.0
SLOW_KT, STOPPED_KT = 1.5, 0.7
MIN_DWELL = timedelta(minutes=30)
MAX_GAP = timedelta(hours=6)  # a longer silence splits one vessel's track into two visits


@dataclass(frozen=True)
class Fix:
    mmsi: str
    t: datetime
    lat: float
    lon: float
    sog_kt: float


@dataclass(frozen=True)
class PortCall:
    mmsi: str
    port_id: str
    arrived_anchorage: datetime | None
    berth_start: datetime | None
    berth_end: datetime | None
    departed: datetime | None

    @property
    def wait_hours(self) -> float | None:
        if self.arrived_anchorage and self.berth_start and self.berth_start >= self.arrived_anchorage:
            return round((self.berth_start - self.arrived_anchorage).total_seconds() / 3600, 2)
        return None


def zone(fix: Fix, center: tuple[float, float]) -> str:
    d = haversine_km((fix.lat, fix.lon), center)
    if d <= BERTH_KM and fix.sog_kt <= STOPPED_KT:
        return "berth"
    if d <= ANCHORAGE_KM and fix.sog_kt <= SLOW_KT and d > BERTH_KM:
        return "anchorage"
    if d <= ANCHORAGE_KM:
        return "near"  # moving through the approach
    return "away"


def detect_port_calls(fixes: list[Fix], port_id: str, center: tuple[float, float]) -> list[PortCall]:
    """Calls for one port from time-ordered fixes of any number of vessels."""
    by_ship: dict[str, list[Fix]] = defaultdict(list)
    for f in fixes:
        by_ship[f.mmsi].append(f)
    calls: list[PortCall] = []
    for mmsi, track in by_ship.items():
        track.sort(key=lambda f: f.t)
        arrived = berth_start = berth_end = last_seen = None
        in_visit = False
        for prev, cur in zip([None, *track], track, strict=False):
            z = zone(cur, center)
            if in_visit and prev and cur.t - prev.t > MAX_GAP:
                calls.append(PortCall(mmsi, port_id, arrived, berth_start, berth_end, None))
                arrived = berth_start = berth_end = None
                in_visit = False
            if z == "anchorage" and arrived is None and berth_start is None:
                arrived, in_visit = cur.t, True
            elif z == "berth":
                if berth_start is None:
                    berth_start = cur.t
                berth_end, in_visit = cur.t, True
            if z != "away":
                last_seen = cur.t
            elif in_visit:
                calls.append(PortCall(mmsi, port_id, arrived, berth_start, berth_end, cur.t))
                arrived = berth_start = berth_end = None
                in_visit = False
        if in_visit:
            calls.append(PortCall(mmsi, port_id, arrived, berth_start, berth_end, None))
        del last_seen
    return [c for c in calls if _real_call(c)]


def _real_call(c: PortCall) -> bool:
    """Drop fly-bys: require a real anchorage stay or berth stay."""
    if c.berth_start and c.berth_end and c.berth_end - c.berth_start >= MIN_DWELL:
        return True
    return bool(c.arrived_anchorage and c.departed and c.departed - c.arrived_anchorage >= MIN_DWELL)
