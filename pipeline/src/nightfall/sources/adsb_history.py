"""adsb.lol globe_history — one day's traces, clipped to the Philippine AOI.

Year-scale ADS-B is not fillable at $0.00: the documented historical dump is a *global* daily
tar on GitHub Releases (ODbL, no payment method), each day several gigabytes, and years of
Philippine tracks would breach both the 1 GB serving-set ceiling and the 300k-vertex frame
budget. This module therefore collects **one calendar day**, writes each matching aircraft's
trace bytes untouched, and lets the transform clip points to the AOI.

It is not a second source. Attribution, licence, and the landing-zone prefix stay `adsb_lol`.
The GitHub release is the documented distribution channel for the same provider
(https://www.adsb.lol/docs/open-data/historical/). Tests never call it; they replay a
recorded trace.

The browser never sees these URLs (invariant 1).
"""

from __future__ import annotations

import io
import json
import logging
import tarfile
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

import httpx

from nightfall.clock import from_unix
from nightfall.geo import PH_AOI
from nightfall.sources.adsb_lol import AdsbLolAdapter
from nightfall.sources.base import RawRecord, SourceOutageError, as_number, as_text
from nightfall.store import LocalRawStore, RawStore

log = logging.getLogger("nightfall")

GITHUB_API = "https://api.github.com"
GITHUB_REPO_PREFIX = "adsblol/globe_history_"

#: Prefer the production replica; staging is a fallback if prod is missing or tiny.
PREFERRED_INSTANCE = "planes-readsb-prod-0"
FALLBACK_INSTANCE = "planes-readsb-staging-0"

#: Trace files we keep. `trace_recent_*` is a short suffix of the same day and would
#: double-count the afternoon if ingested alongside `trace_full_*`.
TRACE_FULL_MARK = "trace_full_"

#: readsb trace point: [offset_s, lat, lon, alt, gs, track, ...]
IDX_OFFSET = 0
IDX_LAT = 1
IDX_LON = 2
IDX_ALT = 3
IDX_GS = 4
IDX_TRACK = 5


class GlobeHistoryError(SourceOutageError):
    """The documented daily dump could not be fetched or contained no Philippine traces."""


def history_repo(day: date) -> str:
    return f"{GITHUB_REPO_PREFIX}{day.year}"


def release_tag(day: date, instance: str) -> str:
    return f"v{day.isoformat()}-{instance}"


def parse_trace(payload: bytes) -> list[dict[str, object]]:
    """Flatten one readsb globe_history trace into position rows.

    Same output shape as `adsb_lol.normalise`, so tests and the bake stage do not grow a
    second schema. Points without a usable lat/lon are dropped; altitude may be the string
    `ground`. Times are Unix seconds, timezone-aware once they reach storage.
    """
    document = json.loads(payload)
    if not isinstance(document, dict):
        raise ValueError("globe_history trace is not a JSON object")
    base = as_number(document.get("timestamp"))
    if base is None:
        raise ValueError("globe_history trace carries no usable `timestamp`")
    entity_id = (
        as_text(document.get("hex"))
        or as_text(document.get("icao"))
        or as_text(document.get("icao24"))
        or ""
    ).lower()
    if not entity_id:
        return []
    label = as_text(document.get("flight"))
    registration = as_text(document.get("r"))
    aircraft_type = as_text(document.get("t"))
    rows: list[dict[str, object]] = []
    for point in document.get("trace") or []:
        if not isinstance(point, list) or len(point) <= IDX_LON:
            continue
        offset = as_number(point[IDX_OFFSET])
        lat = as_number(point[IDX_LAT])
        lon = as_number(point[IDX_LON])
        if offset is None or lat is None or lon is None:
            continue
        altitude = point[IDX_ALT] if len(point) > IDX_ALT else None
        on_ground = altitude == "ground"
        rows.append(
            {
                "entity_id": entity_id,
                "callsign": label,
                "registration": registration,
                "aircraft_type": aircraft_type,
                "lon": lon,
                "lat": lat,
                "altitude_ft": None if on_ground else as_number(altitude),
                "on_ground": on_ground,
                "speed_kt": as_number(point[IDX_GS]) if len(point) > IDX_GS else None,
                "track_deg": as_number(point[IDX_TRACK]) if len(point) > IDX_TRACK else None,
                "observed_unix": base + offset,
            }
        )
    return rows


def trace_intersects_aoi(payload: bytes) -> bool:
    """True when at least one fix in the raw trace sits inside the Philippine AOI."""
    for row in parse_trace(payload):
        lon, lat = row["lon"], row["lat"]
        if (
            isinstance(lon, int | float)
            and isinstance(lat, int | float)
            and PH_AOI.contains(float(lon), float(lat))
        ):
            return True
    return False


def last_observed_at(payload: bytes) -> datetime:
    """The latest fix in the trace, which is when this object finished observing."""
    rows = parse_trace(payload)
    if not rows:
        raise ValueError("trace has no position fixes")
    latest = max(float(row["observed_unix"]) for row in rows)  # type: ignore[arg-type]
    return from_unix(latest)


def is_full_trace_member(name: str) -> bool:
    normalised = name.replace("\\", "/")
    return TRACE_FULL_MARK in normalised and "/traces/" in normalised


def iter_trace_payloads(archive: BinaryIO) -> Iterator[tuple[str, bytes]]:
    """Yield `(member_name, decompressed_json)` for every full-day trace in a tar stream."""
    with tarfile.open(fileobj=archive, mode="r|") as tar:
        for member in tar:
            if not member.isfile() or not is_full_trace_member(member.name):
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            raw = extracted.read()
            payload = _maybe_gunzip(raw, member.name)
            yield member.name, payload


def _maybe_gunzip(raw: bytes, name: str) -> bytes:
    if name.endswith(".gz") or raw[:2] == b"\x1f\x8b":
        import gzip

        return gzip.decompress(raw)
    return raw


def records_from_tar(archive: BinaryIO, *, day: date) -> list[RawRecord]:
    """Filter a globe_history tar down to traces that intersect the AOI.

    Each matching file is queued as a `RawRecord` with the *original JSON bytes*. Parsing
    happens only to decide whether to keep the object; the bytes written are the document as
    it arrived in the archive.
    """
    records: list[RawRecord] = []
    considered = 0
    for name, payload in iter_trace_payloads(archive):
        considered += 1
        try:
            if not trace_intersects_aoi(payload):
                continue
            observed_at = last_observed_at(payload)
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            log.warning("source=adsb_lol globe_history member=%s skipped detail=%s", name, exc)
            continue
        hex_id = Path(name).name.split("trace_full_")[-1].split(".")[0].lower()
        records.append(
            RawRecord(
                source=AdsbLolAdapter.name,
                request_key=f"globe_history/{day.isoformat()}/trace/{hex_id}",
                body=payload,
                content_type="application/json",
                observed_at=observed_at,
            )
        )
    log.info(
        "source=adsb_lol globe_history day=%s considered=%d kept=%d",
        day.isoformat(),
        considered,
        len(records),
    )
    return records


def collect_globe_history(
    store: RawStore,
    *,
    day: date,
    client: httpx.Client | None = None,
    user_agent: str,
) -> list[str]:
    """Download one day's production dump, filter to the AOI, write raw traces.

    Network belongs here, not in tests. A missing release is an outage of the historical
    archive, not an empty sky.
    """
    own_client = client is None
    http = client or httpx.Client(timeout=120.0, headers={"user-agent": user_agent})
    try:
        assets = _release_assets(http, day)
        archive = _download_split_tar(http, assets)
        records = records_from_tar(archive, day=day)
    finally:
        if own_client:
            http.close()
    if not records:
        raise GlobeHistoryError(
            f"adsb.lol globe_history {day.isoformat()} contained no traces inside the "
            "Philippine AOI"
        )
    return [
        store.put(
            source=record.source,
            request_key=record.request_key,
            body=record.body,
            observed_at=record.observed_at,
            content_type=record.content_type,
        )
        for record in records
    ]


def _release_assets(client: httpx.Client, day: date) -> list[str]:
    """Browser-download URLs for the split tar of the preferred replica."""
    repo = history_repo(day)
    for instance in (PREFERRED_INSTANCE, FALLBACK_INSTANCE):
        tag = release_tag(day, instance)
        url = f"{GITHUB_API}/repos/{repo}/releases/tags/{tag}"
        response = client.get(url)
        if response.status_code == httpx.codes.NOT_FOUND:
            continue
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise GlobeHistoryError(
                f"GitHub refused {url}: HTTP {response.status_code} {response.text[:200]}"
            )
        document = response.json()
        assets = [
            str(asset["browser_download_url"])
            for asset in document.get("assets", [])
            if str(asset.get("name", "")).endswith((".tar.aa", ".tar.ab", ".tar", ".tar.gz"))
            or ".tar." in str(asset.get("name", ""))
        ]
        assets.sort()
        if assets:
            log.info("source=adsb_lol globe_history release=%s assets=%d", tag, len(assets))
            return assets
    raise GlobeHistoryError(
        f"no globe_history release for {day.isoformat()} in {repo} "
        f"({PREFERRED_INSTANCE} / {FALLBACK_INSTANCE})"
    )


def _download_split_tar(client: httpx.Client, urls: list[str]) -> io.BytesIO:
    """Concatenate the split tar parts in name order into one in-memory stream.

    A day's dump is a few gigabytes. This environment can hold it; GitHub Actions standard
    runners cannot, which is why this collector is an explicit command and not the scheduled
    job. Parts are streamed to a single BytesIO so `tarfile` can read them as one archive.
    """
    buffer = io.BytesIO()
    for url in urls:
        log.info("source=adsb_lol globe_history download=%s", url)
        with client.stream("GET", url, follow_redirects=True) as response:
            if response.status_code >= httpx.codes.BAD_REQUEST:
                raise GlobeHistoryError(f"failed to download {url}: HTTP {response.status_code}")
            for chunk in response.iter_bytes(1024 * 1024):
                buffer.write(chunk)
    buffer.seek(0)
    return buffer


def seed_trace(store: LocalRawStore, payload: bytes, *, observed_at: datetime | None = None) -> str:
    """Write one recorded trace into the landing zone. Tests and the fixture path use this."""
    observed = observed_at if observed_at is not None else last_observed_at(payload)
    document = json.loads(payload)
    hex_id = (as_text(document.get("hex")) or as_text(document.get("icao")) or "unknown").lower()
    day = observed.astimezone(UTC).date()
    return store.put(
        source=AdsbLolAdapter.name,
        request_key=f"globe_history/{day.isoformat()}/trace/{hex_id}",
        body=payload,
        observed_at=observed,
        content_type="application/json",
    )


def default_history_day() -> date:
    """Yesterday UTC — today's dump is published the following morning."""
    return datetime.now(tz=UTC).date() - timedelta(days=1)
