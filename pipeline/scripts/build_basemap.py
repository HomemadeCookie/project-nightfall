"""Cut a Philippines-sized basemap out of a Protomaps planet build into the serving set.

Self-hosted because a hosted tile service is a metered billing relationship (invariant 0) and
MapLibre's demo tiles are a demo, not a licence to depend on. Protomaps publishes complete
planet builds as PMTiles, and `pmtiles extract` reads only the byte ranges it needs over HTTP,
so cutting our area of interest out of a 137 GB planet file costs about 20 MB of transfer and a
few seconds rather than a download of the planet.

This runs inside the pipeline job rather than in a workflow of its own, and writes through a
cache directory keyed by the month. That is a deliberate simplification of an earlier design
where a monthly workflow published the extract to the archive and the pipeline fetched it back:
that path needed an archive repository and a write token, so on a repository where those were
never configured — the common case, and the one the owner is in — the map silently had no
geography at all. Nothing here needs a credential.

Absence remains a supported state. The app draws positions without geographic context and says
why, so every failure below is logged and returns zero: a basemap is context, and the
observations are the product.

    uv run --project pipeline python pipeline/scripts/build_basemap.py
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from datetime import timedelta
from pathlib import Path

import httpx

from nightfall.clock import utc_now
from nightfall.config import Settings
from nightfall.geo import BASEMAP_BBOX, BASEMAP_MAX_ZOOM

log = logging.getLogger("nightfall.basemap")

LOG_FORMAT = "%(asctime)sZ %(levelname)s %(name)s %(message)s"

#: Protomaps names each planet build by date.
BUILD_URL = "https://build.protomaps.com/{date}.pmtiles"

#: How far back to look for a published build. It appears on Protomaps' schedule, not ours, so
#: today's may not exist yet and a run must not fail for being early in the day.
BUILD_LOOKBACK_DAYS = 7

#: What the app requests. A fixed name rather than a content hash: the app asks for it by
#: name, and a basemap that changes monthly does not need a cache-busting URL.
SERVING_NAME = "basemap.pmtiles"

#: The whole site must fit under 1 GB and the mobility artifacts need room too. The Philippine
#: extract at zoom 10 measures about 20 MB, so this is a tripwire for a changed bbox or zoom
#: ceiling rather than a limit anyone is near.
SIZE_LIMIT_BYTES = 200 * 1024 * 1024


class BasemapUnavailableError(RuntimeError):
    """Something upstream, or the toolchain, is not there. Reported, never fatal."""


def find_build() -> str:
    """The URL of the most recent published planet build."""
    at = utc_now()
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for offset in range(1, BUILD_LOOKBACK_DAYS + 1):
            url = BUILD_URL.format(date=(at - timedelta(days=offset)).strftime("%Y%m%d"))
            try:
                response = client.head(url)
            except httpx.HTTPError as error:
                log.warning("could not reach %s: %s", url, error)
                continue
            if response.is_success:
                return url
    raise BasemapUnavailableError(
        f"no Protomaps build published in the last {BUILD_LOOKBACK_DAYS} days"
    )


def extract(url: str, target: Path) -> None:
    """Cut the area of interest out of a planet build."""
    if shutil.which("pmtiles") is None:
        raise BasemapUnavailableError("the pmtiles tool is not installed")

    bbox = f"{BASEMAP_BBOX.west},{BASEMAP_BBOX.south},{BASEMAP_BBOX.east},{BASEMAP_BBOX.north}"
    target.parent.mkdir(parents=True, exist_ok=True)
    # To a temporary name, then moved: a half-written archive left in the cache directory would
    # be restored on the next run and handed to the browser as if it were whole.
    partial = target.with_suffix(".partial")
    log.info("extracting bbox=%s maxzoom=%d from %s", bbox, BASEMAP_MAX_ZOOM, url)
    try:
        # Fixed argv, no shell, and the URL came from `find_build` rather than from input.
        subprocess.run(
            [
                "pmtiles",
                "extract",
                url,
                str(partial),
                f"--bbox={bbox}",
                f"--maxzoom={BASEMAP_MAX_ZOOM}",
            ],
            check=True,
        )
    except subprocess.CalledProcessError as error:
        partial.unlink(missing_ok=True)
        message = f"pmtiles extract failed with status {error.returncode}"
        raise BasemapUnavailableError(message) from error

    size = partial.stat().st_size
    if size > SIZE_LIMIT_BYTES:
        partial.unlink(missing_ok=True)
        raise BasemapUnavailableError(
            f"extract is {size} bytes, over the {SIZE_LIMIT_BYTES} byte limit; "
            "lower BASEMAP_MAX_ZOOM or tighten BASEMAP_BBOX"
        )
    partial.replace(target)


def cache_dir(settings: Settings) -> Path:
    """Where the extract is kept between runs.

    Outside the serving set, because the serving set is rebuilt from scratch by the bake stage
    and this is the one artifact that must survive it.
    """
    override = os.environ.get("NIGHTFALL_BASEMAP_CACHE")
    return Path(override) if override else settings.data_root / "basemap"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    logging.Formatter.converter = time.gmtime

    settings = Settings()
    cached = cache_dir(settings) / SERVING_NAME

    try:
        if cached.exists():
            log.info("using the cached extract bytes=%d", cached.stat().st_size)
        else:
            extract(find_build(), cached)
    except BasemapUnavailableError as error:
        log.warning("no basemap this run: %s", error)
        return 0

    settings.serving_dir.mkdir(parents=True, exist_ok=True)
    target = settings.serving_dir / SERVING_NAME
    # Copied rather than linked: the Pages artifact is a tarball of real files.
    shutil.copyfile(cached, target)
    log.info("basemap ready at %s bytes=%d", target, target.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
