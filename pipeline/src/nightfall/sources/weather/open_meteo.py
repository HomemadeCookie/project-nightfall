"""Open-Meteo wind, gust, rain and wave forecasts at ferry-route waypoints.

The free API is for NON-COMMERCIAL use only, so this adapter is marked NON_COMMERCIAL: it powers
development and research. Before charging anyone, swap in a commercial-safe provider that
implements the same dataset (see docs/adr/0003-weather-provider.md).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from nightfall.core.envelope import Envelope
from nightfall.core.license import License
from nightfall.sources.base import Source
from nightfall.sources.registry import register

WEATHER = "https://api.open-meteo.com/v1/forecast"
MARINE = "https://marine-api.open-meteo.com/v1/marine"


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def waypoints_from_reference() -> list[dict]:
    from nightfall.core.reference import ferry_waypoints

    return ferry_waypoints()


@register
class OpenMeteo(Source):
    name = "open_meteo"
    license = [License.NON_COMMERCIAL]
    cadence = "hourly"
    attribution = "Weather data by Open-Meteo.com (CC BY 4.0, non-commercial tier)"
    forecast_days = 5

    def fetch(self, now: datetime) -> Iterator[Envelope]:
        points = waypoints_from_reference()
        for batch in chunks(points, 40):
            lat = ",".join(f"{p['lat']:.3f}" for p in batch)
            lon = ",".join(f"{p['lon']:.3f}" for p in batch)
            common = {
                "latitude": lat,
                "longitude": lon,
                "timezone": "UTC",
                "forecast_days": str(self.forecast_days),
            }
            w = self.http.get_json(
                WEATHER,
                params={
                    **common,
                    "hourly": "wind_speed_10m,wind_gusts_10m,precipitation",
                    "wind_speed_unit": "kmh",
                },
            )
            m = self.http.get_json(MARINE, params={**common, "hourly": "wave_height"})
            w = w if isinstance(w, list) else [w]
            m = m if isinstance(m, list) else [m]
            records = []
            for p, wi, mi in zip(batch, w, m, strict=True):
                records.append(
                    {
                        "waypoint_id": p["waypoint_id"],
                        "lat": p["lat"],
                        "lon": p["lon"],
                        "weather": wi["hourly"],
                        "marine": mi["hourly"],
                    }
                )
            yield self.envelope(
                "route_forecast",
                records,
                now=now,
                request={"n_points": len(batch), "forecast_days": self.forecast_days},
            )
