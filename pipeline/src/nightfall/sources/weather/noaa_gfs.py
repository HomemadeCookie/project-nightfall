"""NOAA GFS wind and GFS-Wave significant wave height at ferry waypoints (US government work, public domain).

This is the commercial-safe replacement for the Open-Meteo adapter (ADR 0003): it emits the same
``route_forecast`` dataset, so staging, indicators and answers do not change. NOMADS serves small
regional GRIB subsets (about 20 KB per forecast hour), decoded with ``eccodes``.
"""

from __future__ import annotations

import math
import tempfile
from collections.abc import Iterator
from datetime import datetime, timedelta

from nightfall.core.envelope import Envelope
from nightfall.core.license import License
from nightfall.sources.base import Source
from nightfall.sources.registry import register

BOX = {"toplat": 22.5, "bottomlat": 3.0, "leftlon": 114.0, "rightlon": 128.5}
GFS = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
WAVE = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfswave.pl"
HOURS = list(range(0, 121, 3))
MISSING = 9000.0  # GRIB missing markers appear as 9999 or ~1e20; no weather variable here is that large
MS_TO_KMH = 3.6


def decode(content: bytes, points: list[tuple[float, float]]) -> dict[str, list[float | None]]:
    """Values by short name at each (lat, lon), using the nearest valid grid point (<= 0.5 degree away).

    Waves are masked over land, so a waypoint beside a port may need a neighbouring sea cell.
    """
    import eccodes

    out: dict[str, list[float | None]] = {}
    with tempfile.NamedTemporaryFile(suffix=".grib2") as tmp:
        tmp.write(content)
        tmp.flush()
        with open(tmp.name, "rb") as fh:
            while (h := eccodes.codes_grib_new_from_file(fh)) is not None:
                name = eccodes.codes_get(h, "shortName")
                vals: list[float | None] = []
                for lat, lon in points:
                    best = None
                    for n in sorted(
                        eccodes.codes_grib_find_nearest(h, lat, lon, npoints=4), key=lambda r: r["distance"]
                    ):
                        v = n["value"]
                        if v is not None and abs(v) < MISSING and not math.isnan(v) and n["distance"] <= 60:
                            best = float(v)
                            break
                    vals.append(best)
                out[name] = vals
                eccodes.codes_release(h)
    return out


def cycle_candidates(now: datetime) -> list[datetime]:
    """Newest first. A cycle is usually complete ~4.5 h after its nominal time."""
    base = (now - timedelta(hours=4, minutes=30)).replace(minute=0, second=0, microsecond=0)
    base -= timedelta(hours=base.hour % 6)
    return [base, base - timedelta(hours=6)]


def _gfs_params(cycle: datetime, hour: int) -> dict[str, str]:
    return {
        "dir": f"/gfs.{cycle:%Y%m%d}/{cycle:%H}/atmos",
        "file": f"gfs.t{cycle:%H}z.pgrb2.0p25.f{hour:03d}",
        "var_UGRD": "on",
        "var_VGRD": "on",
        "var_GUST": "on",
        "lev_10_m_above_ground": "on",
        "lev_surface": "on",
        "subregion": "",
        **{k: str(v) for k, v in BOX.items()},
    }


def _wave_params(cycle: datetime, hour: int) -> dict[str, str]:
    return {
        "dir": f"/gfs.{cycle:%Y%m%d}/{cycle:%H}/wave/gridded",
        "file": f"gfswave.t{cycle:%H}z.global.0p25.f{hour:03d}.grib2",
        "var_HTSGW": "on",
        "lev_surface": "on",
        "subregion": "",
        **{k: str(v) for k, v in BOX.items()},
    }


@register
class NoaaGfs(Source):
    name = "noaa_gfs"
    license = [License.PUBLIC_DOMAIN]
    cadence = (
        "hourly"  # the forecast refreshes every 6 h; repeated polls within a cycle are skipped via `known`
    )
    attribution = "NOAA/NCEP Global Forecast System and GFS-Wave (public domain)"
    incremental = ("route_forecast", "cycle")

    def __init__(self, http, **kw):
        super().__init__(http, **kw)
        http._min_interval["nomads.ncep.noaa.gov"] = 0.7

    def fetch(self, now: datetime) -> Iterator[Envelope]:
        from nightfall.core.reference import ferry_waypoints

        points = ferry_waypoints()
        coords = [(p["lat"], p["lon"]) for p in points]
        for cycle in cycle_candidates(now):
            key = cycle.strftime("%Y%m%d%H")
            if key in self.known:
                return  # this cycle is already stored
            try:
                first = self.http.get(GFS, params=_gfs_params(cycle, 0)).content
            except Exception:
                continue  # not published yet: try the previous cycle
            series: dict[str, dict[str, list]] = {}
            times: list[str] = []
            for hour in HOURS:
                content = first if hour == 0 else self.http.get(GFS, params=_gfs_params(cycle, hour)).content
                atm = decode(content, coords)
                try:
                    wave = decode(self.http.get(WAVE, params=_wave_params(cycle, hour)).content, coords)
                except Exception:
                    wave = {}
                valid = (cycle + timedelta(hours=hour)).strftime("%Y-%m-%dT%H:%M")
                times.append(valid)
                for i, p in enumerate(points):
                    s = series.setdefault(p["waypoint_id"], {"wind": [], "gust": [], "wave": []})
                    u, v = atm.get("10u", [None] * len(points))[i], atm.get("10v", [None] * len(points))[i]
                    s["wind"].append(
                        None if u is None or v is None else round(math.hypot(u, v) * MS_TO_KMH, 1)
                    )
                    g = atm.get("gust", [None] * len(points))[i]
                    s["gust"].append(None if g is None else round(g * MS_TO_KMH, 1))
                    w = wave.get("swh", [None] * len(points))[i]
                    s["wave"].append(None if w is None else round(w, 2))
            records = [
                {
                    "waypoint_id": p["waypoint_id"],
                    "lat": p["lat"],
                    "lon": p["lon"],
                    "weather": {
                        "time": times,
                        "wind_speed_10m": series[p["waypoint_id"]]["wind"],
                        "wind_gusts_10m": series[p["waypoint_id"]]["gust"],
                        "precipitation": [0.0] * len(times),
                    },
                    "marine": {"time": times, "wave_height": series[p["waypoint_id"]]["wave"]},
                }
                for p in points
            ]
            yield self.envelope("route_forecast", records, now=now, request={"cycle": key, "hours": HOURS})
            return
