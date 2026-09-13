"""adsb.lol aircraft positions, collected as a bounded sampling window.

Primary flight source. Chosen over OpenSky specifically because it publishes no restriction
on hyperscaler IP ranges, and every job in this project runs on an Azure-hosted GitHub Actions
runner (see README § Risks, platform rule changes).

Licence is ODbL, so derived geometry carries share-alike obligations. Data is live-only: an
empty result means "not airborne right now", never "absent from history".

Like the AIS collector, this is a window rather than a single snapshot: the job sweeps the
coverage circles repeatedly at a short cadence for a few minutes, then exits. The single
snapshot that a scheduled job invites is the wrong shape for a *path* overlay, because two
fixes half an hour apart cannot be joined into a track — an airliner covers hundreds of
kilometres between them, and drawing a line across that is interpolation over unobserved
ground, which the coverage rules forbid. Sweeping densely inside a bounded window instead
produces track segments that were genuinely observed, separated by gaps that are shown as
gaps.

Nothing here outlives the job (invariant 8): the window is a few minutes of an ephemeral
GitHub Actions run, not a resident poller.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence

import httpx

from nightfall.clock import utc_now
from nightfall.config import Settings
from nightfall.geo import PH_AOI, Circle, coverage_circles
from nightfall.ratelimit import ADSB_LOL_QUOTA, TokenBucket
from nightfall.sources.base import (
    CommercialUse,
    Licence,
    RawRecord,
    SourceAdapter,
    SourceOutageError,
    as_number,
    as_text,
)
from nightfall.store import RawStore

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

#: Seconds between sweeps of the full coverage set. The AOI needs six circles and the provider
#: documents roughly one request per second, so a sweep occupies about six seconds; twenty
#: leaves ample headroom and still puts an aircraft's successive fixes close enough together
#: that the straight line between them is a fair account of where it went.
DEFAULT_SWEEP_INTERVAL_S = 20.0

#: Length of one collection window. Bounded so the job is unmistakably ephemeral, and short
#: enough that the runner time this costs stays proportionate to a scheduled data pull.
DEFAULT_WINDOW_S = 180.0

#: adsb.lol counts requests per *connection*, not per client.
#:
#: Measured, because it is documented nowhere: six coverage circles requested 1.5 s apart over
#: one keep-alive connection return 200, 200, 200 and then HTTP 429 for everything that
#: follows, while the identical sequence on a fresh connection per request returns 200
#: throughout. Reusing the socket therefore produces a permanent hole in the southeast of the
#: area of interest — the circles that happen to be swept last — which downstream would read
#: as an empty sky rather than as an unasked question.
#:
#: This is also why the behaviour survived manual testing with curl, which opens a new
#: connection for each invocation and so never reproduces it.
KEEPALIVE_LIMITS = httpx.Limits(max_keepalive_connections=0, max_connections=1)

log = logging.getLogger("nightfall")


class AdsbLolAdapter(SourceAdapter):
    name = "adsb_lol"
    licence = Licence(
        name="ODbL 1.0",
        url="https://opendatacommons.org/licenses/odbl/1-0/",
        commercial_use=CommercialUse.SHARE_ALIKE,
        attribution="Aircraft positions © adsb.lol contributors, ODbL",
    )
    quota = ADSB_LOL_QUOTA

    def __init__(
        self,
        store: RawStore,
        settings: Settings,
        *,
        bucket: TokenBucket | None = None,
        timeout_s: float = 20.0,
    ) -> None:
        super().__init__(store, settings, bucket=bucket)
        self._window_s = settings.adsb_window_s
        self._sweep_interval_s = settings.adsb_sweep_interval_s
        self._timeout_s = timeout_s
        self._circles: tuple[Circle, ...] = coverage_circles(PH_AOI, MAX_RADIUS_NM)
        #: Circles that failed at least once, and the last reason, for the coverage note.
        self._skipped: dict[str, str] = {}
        self._observed: set[str] = set()

    @property
    def circles(self) -> tuple[Circle, ...]:
        return self._circles

    @property
    def sweep_count(self) -> int:
        return max(1, int(self._window_s // self._sweep_interval_s))

    @staticmethod
    def request_key(circle: Circle) -> str:
        return f"point/{circle.lat}/{circle.lon}/{circle.radius_nm:.0f}"

    async def collect(self) -> Sequence[RawRecord]:
        """Sweep the coverage circles for the length of the window.

        A circle that fails after its retries is skipped rather than aborting the run: partial
        coverage recorded honestly is more useful than no observation at all, and the gap is
        visible downstream through the coverage columns. The window ends on schedule whatever
        happens, so a degraded upstream shortens the sample instead of hanging the job.
        """
        records: list[RawRecord] = []
        deadline = asyncio.get_running_loop().time() + self._window_s
        async with self.client() as client:
            for sweep in range(self.sweep_count):
                records.extend(await self._sweep(client))
                if sweep + 1 >= self.sweep_count:
                    break
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(self._sweep_interval_s, remaining))
        if not records:
            raise SourceOutageError("adsb.lol returned no usable response for any coverage circle")
        return records

    async def _sweep(self, client: httpx.AsyncClient) -> list[RawRecord]:
        records: list[RawRecord] = []
        for circle in self._circles:
            try:
                body = await self._fetch(client, circle)
            except SourceOutageError as skipped:
                # Logged and counted, not swallowed. A skipped circle is a hole in the
                # coverage this run will publish, and "which circle, and why" is the only way
                # to tell a quiet region from one we failed to ask about (invariant 7).
                key = self.request_key(circle)
                self._skipped[key] = str(skipped)
                log.warning("source=%s circle=%s state=skipped detail=%s", self.name, key, skipped)
                continue
            self._observed.add(self.request_key(circle))
            records.append(
                RawRecord(
                    source=self.name,
                    request_key=self.request_key(circle),
                    body=body,
                    content_type="application/json",
                    observed_at=utc_now(),
                )
            )
        return records

    def client(self) -> httpx.AsyncClient:
        """An HTTP client that never reuses a connection. See `KEEPALIVE_LIMITS`."""
        return httpx.AsyncClient(
            timeout=self._timeout_s,
            limits=KEEPALIVE_LIMITS,
            headers=self.headers,
        )

    def coverage_note(self) -> str | None:
        missed = sorted(key for key in self._skipped if key not in self._observed)
        if not missed:
            return None
        # Named individually rather than counted: a reader who knows which circle was missed
        # knows which part of the map to distrust.
        detail = "; ".join(f"{key}: {self._skipped[key]}" for key in missed)
        return (
            f"{len(self._observed)} of {len(self._circles)} coverage circles observed. "
            f"No aircraft were requested for {detail}"
        )

    async def _fetch(self, client: httpx.AsyncClient, circle: Circle) -> bytes:
        url = f"{API_ROOT}/{self.request_key(circle)}"
        for attempt in range(self.max_attempts):
            await self._bucket.acquire()
            try:
                response = await client.get(url, headers=self.headers)
            except httpx.HTTPError as exc:
                if attempt == self.max_attempts - 1:
                    raise SourceOutageError(f"adsb.lol unreachable: {exc}") from exc
                await self._backoff(attempt)
                continue

            if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                await self._backoff(attempt, retry_after=_retry_after(response))
                continue
            # Any other 4xx is a request defect; retrying cannot fix it. The body is carried
            # into the message because that is where the provider explains itself — a bare
            # "HTTP 403" sends the reader to a packet capture to learn what a sentence in the
            # response already said.
            if httpx.codes.BAD_REQUEST <= response.status_code < httpx.codes.INTERNAL_SERVER_ERROR:
                raise SourceOutageError(
                    f"adsb.lol rejected {url}: HTTP {response.status_code} "
                    f"{_reason(response)}".rstrip()
                )
            if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
                if attempt == self.max_attempts - 1:
                    raise SourceOutageError(f"adsb.lol failing: HTTP {response.status_code}")
                await self._backoff(attempt)
                continue
            return response.content

        raise SourceOutageError(f"adsb.lol exhausted {self.max_attempts} attempts for {url}")


#: How much of a rejection body to quote. Enough for a sentence of explanation, short enough
#: that an HTML error page does not bury the log.
_REASON_LIMIT = 200


def _reason(response: httpx.Response) -> str:
    text = " ".join(response.text.split())[:_REASON_LIMIT]
    return f"({text})" if text else ""


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
