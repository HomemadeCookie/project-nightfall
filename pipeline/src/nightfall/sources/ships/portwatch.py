"""IMF PortWatch: daily port calls and chokepoint transits, derived from AIS by the IMF.

The licence is not stated in the ArcGIS service metadata, so it is marked UNCLEAR and
stays blocked from commercial publishing until it is reviewed (reference/license_reviews.yaml).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta

from nightfall.core.envelope import Envelope
from nightfall.core.license import License
from nightfall.sources.base import Source
from nightfall.sources.registry import register

WINDOW_DAYS = 60
BASE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"

# Chokepoints on the routes that feed the Philippines, plus the global ones that move freight rates.
CHOKEPOINTS = {
    "chokepoint5": "Malacca Strait",
    "chokepoint11": "Taiwan Strait",
    "chokepoint14": "Luzon Strait",
    "chokepoint27": "Mindoro Strait",
    "chokepoint25": "Balabac Strait",
    "chokepoint20": "Makassar Strait",
    "chokepoint15": "Lombok Strait",
    "chokepoint19": "Sunda Strait",
    "chokepoint1": "Suez Canal",
    "chokepoint4": "Bab el-Mandeb Strait",
    "chokepoint6": "Strait of Hormuz",
    "chokepoint2": "Panama Canal",
}

PORT_FIELDS = (
    "date,portid,portname,portcalls,portcalls_container,portcalls_tanker,portcalls_dry_bulk,"
    "portcalls_general_cargo,portcalls_roro,import,export,import_container,import_dry_bulk,"
    "import_general_cargo,import_roro,import_tanker,export_container,export_dry_bulk,"
    "export_general_cargo,export_roro,export_tanker"
)


@register
class PortWatch(Source):
    name = "portwatch"
    license = [License.UNCLEAR]
    cadence = "daily"
    attribution = "IMF PortWatch (portwatch.imf.org)"
    lookback_days = 120

    def _query(self, service: str, where: str, out_fields: str, order: str | None = "ObjectId") -> list[dict]:
        """Paged ArcGIS query returning attribute dicts."""
        url = f"{BASE}/{service}/FeatureServer/0/query"
        rows: list[dict] = []
        offset = 0
        while True:
            params = {
                "where": where,
                "outFields": out_fields,
                "returnGeometry": "false",
                "f": "json",
                "resultOffset": str(offset),
                "resultRecordCount": "1000",
            }
            if order:
                params["orderByFields"] = order
            body = self.http.get_json(url, params=params, timeout=90.0)
            if "error" in body:
                raise RuntimeError(f"PortWatch {service}: {body['error']}")
            feats = body.get("features", [])
            rows.extend(f["attributes"] for f in feats)
            if not body.get("exceededTransferLimit") or not feats:
                return rows
            offset += len(feats)

    def _windowed(self, service: str, id_clause: str, out_fields: str, start: date, end: date) -> list[dict]:
        """Query in WINDOW_DAYS slices: one huge date range is slow enough to time out on the server."""
        rows: list[dict] = []
        lo = start
        while lo <= end:
            hi = min(lo + timedelta(days=WINDOW_DAYS), end + timedelta(days=1))
            where = (
                f"{id_clause} AND date >= timestamp '{lo:%Y-%m-%d} 00:00:00' "
                f"AND date < timestamp '{hi:%Y-%m-%d} 00:00:00'"
            )
            rows.extend(self._query(service, where, out_fields))
            lo = hi
        rows.sort(key=lambda r: (str(r["date"]), r["portid"]))
        return rows

    def fetch(self, now: datetime) -> Iterator[Envelope]:
        start = (now - timedelta(days=self.lookback_days)).date()
        ports = self._query(
            "PortWatch_ports_database",
            "ISO3='PHL'",
            "portid,portname,lat,lon,vessel_count_total,vessel_count_container,"
            "vessel_count_tanker,vessel_count_dry_bulk,vessel_count_RoRo",
            "portid",
        )
        yield self.envelope("ports", ports, now=now, request={"iso3": "PHL"})

        ids = ",".join(f"'{p['portid']}'" for p in ports if p["portid"].startswith("port"))
        daily = self._windowed("Daily_Ports_Data", f"portid IN ({ids})", PORT_FIELDS, start, now.date())
        yield self.envelope("daily_ports", daily, now=now, request={"since": start.isoformat()})

        cp_ids = ",".join(f"'{c}'" for c in CHOKEPOINTS)
        choke = self._windowed(
            "Daily_Chokepoints_Data",
            f"portid IN ({cp_ids})",
            "date,portid,portname,n_container,n_dry_bulk,n_general_cargo,n_roro,n_tanker,n_total,capacity",
            start,
            now.date(),
        )
        yield self.envelope("daily_chokepoints", choke, now=now, request={"since": start.isoformat()})
