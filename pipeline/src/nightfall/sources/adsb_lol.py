"""adsb.lol aircraft positions.

Primary flight source. Chosen over OpenSky specifically because it publishes no restriction
on hyperscaler IP ranges, and every job in this project runs on an Azure-hosted GitHub Actions
runner (see README § Risks, platform rule changes).

Licence is ODbL, so derived geometry carries share-alike obligations. Data is live-only: an
empty result means "not airborne right now", never "absent from history".
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import httpx

from nightfall.geo import PH_AOI, Circle, coverage_circles
from nightfall.ratelimit import ADSB_LOL_QUOTA
from nightfall.sources.base import (
    CommercialUse,
    Licence,
    RawRecord,
    SourceAdapter,
    SourceOutage,
    as_number,
    as_text,
)

API_ROOT = "https://api.adsb.lol/v2"

#: adsb.lol caps a point query at 250 nautical miles.
MAX_RADIUS_NM = 250.0

#: The response-level `now` field is milliseconds since the Unix epoch (the readsb
#: convention), while the per-aircraft ages in the same document (`seen`, `seen_pos`) are
#: seconds. Subtracting one from the other without converting yields timestamps tens of
#: thousands of years out, and nothing downstream would reject them, so the unit is asserted
#: below rather than assumed.
NOW_UNITS_PER_SECOND = 1000.0

#: Bounds for the asserted unit check: 2020-01-01 and 2100-01-01 as Unix seconds.
_PLAUSIBLE_UNIX_RANGE = (1_577_836_800.0, 4_102_444_800.0)


class AdsbLolAdapter(SourceAdapter):
    name = "adsb_lol"
    licence = Licence(
        name="ODbL 1.0",
        url="https://opendatacommons.org/licenses/odbl/1-0/",
        commercial_use=CommercialUse.SHARE_ALIKE,
        attribution="Aircraft positions © adsb.lol contributors, ODbL",
    )
    quota = ADSB_LOL_QUOTA

    def __init__(self, *args: object, timeout_s: float = 20.0, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._timeout_s = timeout_s
        self._circles: tuple[Circle, ...] = coverage_circles(PH_AOI, MAX_RADIUS_NM)

    @property
    def circles(self) -> tuple[Circle, ...]:
        return self._circles

    @staticmethod
    def request_key(circle: Circle) -> str:
        return f"point/{circle.lat}/{circle.lon}/{circle.radius_nm:.0f}"

    async def collect(self) -> Sequence[RawRecord]:
        """One request per coverage circle, rate-limited, raw body preserved verbatim.

        A circle that fails after its retries is skipped rather than aborting the run: partial
        coverage recorded honestly is more useful than no observation at all, and the gap is
        visible downstream through the coverage columns.
        """
        records: list[RawRecord] = []
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            for circle in self._circles:
                try:
                    body = await self._fetch(client, circle)
                except SourceOutage:
                    continue
                records.append(
                    RawRecord(
                        source=self.name,
                        request_key=self.request_key(circle),
                        body=body,
                        content_type="application/json",
                    )
                )
        if not records:
            raise SourceOutage("adsb.lol returned no usable response for any coverage circle")
        return records

    async def _fetch(self, client: httpx.AsyncClient, circle: Circle) -> bytes:
        url = f"{API_ROOT}/{self.request_key(circle)}"
        for attempt in range(self.max_attempts):
            await self._bucket.acquire()
            try:
                response = await client.get(url, headers={"accept": "application/json"})
            except httpx.HTTPError as exc:
                if attempt == self.max_attempts - 1:
                    raise SourceOutage(f"adsb.lol unreachable: {exc}") from exc
                await self._backoff(attempt)
                continue

            if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                await self._backoff(attempt, retry_after=_retry_after(response))
                continue
            # Any other 4xx is a request defect; retrying cannot fix it.
            if httpx.codes.BAD_REQUEST <= response.status_code < httpx.codes.INTERNAL_SERVER_ERROR:
                raise SourceOutage(f"adsb.lol rejected {url}: HTTP {response.status_code}")
            if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
                if attempt == self.max_attempts - 1:
                    raise SourceOutage(f"adsb.lol failing: HTTP {response.status_code}")
                await self._backoff(attempt)
                continue
            return response.content

        raise SourceOutage(f"adsb.lol exhausted {self.max_attempts} attempts for {url}")


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def response_unix(document: dict[str, object], fallback: float | None = None) -> float:
    """Response assembly time in Unix *seconds*, converted from the millisecond wire field.

    Raises if the converted value is implausible, which is what turns a provider unit change
    from a silent data corruption into a failed collection.
    """
    raw = document.get("now")
    if not isinstance(raw, int | float):
        if fallback is None:
            raise ValueError("adsb.lol response carries no usable `now` field")
        return fallback
    seconds = float(raw) / NOW_UNITS_PER_SECOND
    low, high = _PLAUSIBLE_UNIX_RANGE
    if not low <= seconds <= high:
        raise ValueError(
            f"adsb.lol `now`={raw!r} is not milliseconds since the epoch "
            f"({seconds} s is outside {low}..{high}); the wire format has changed"
        )
    return seconds


def normalise(payload: bytes, *, observed_unix: float | None = None) -> list[dict[str, object]]:
    """Flatten one raw adsb.lol response into position rows.

    Kept deliberately close to the wire format: the transform stage does the typing and the
    spatial work. Parsing here exists only so tests can assert the schema we depend on, and so
    the bake stage never has to guess at a field that the provider may rename.

    Defensive about two documented quirks: `alt_baro` is the string "ground" for an aircraft on
    the surface rather than a number, and `flight` is space-padded to eight characters.
    """
    document = json.loads(payload)
    now = response_unix(document, observed_unix)
    rows: list[dict[str, object]] = []
    for aircraft in document.get("ac") or []:
        lon, lat = aircraft.get("lon"), aircraft.get("lat")
        if not isinstance(lon, int | float) or not isinstance(lat, int | float):
            continue  # A position-less state vector is not a position.
        altitude = aircraft.get("alt_baro")
        on_ground = altitude == "ground"
        # `seen_pos` is the age of the position fix in seconds; the position was true then,
        # not when the response was assembled.
        age_s = as_number(aircraft.get("seen_pos")) or 0.0
        rows.append(
            {
                "entity_id": str(aircraft.get("hex", "")).strip().lower(),
                "callsign": as_text(aircraft.get("flight")),
                "registration": as_text(aircraft.get("r")),
                "aircraft_type": as_text(aircraft.get("t")),
                "lon": float(lon),
                "lat": float(lat),
                "altitude_ft": None if on_ground else as_number(altitude),
                "on_ground": on_ground,
                "speed_kt": as_number(aircraft.get("gs")),
                "track_deg": as_number(aircraft.get("track")),
                "observed_unix": now - age_s,
            }
        )
    return rows
