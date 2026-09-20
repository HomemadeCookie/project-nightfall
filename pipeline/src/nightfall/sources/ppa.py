"""Philippine Ports Authority Summary Port Statistics.

Official quarterly/annual throughput at PPA ports, by region. This is volume at nodes,
not vessel tracks. The Excel layout uses merged header cells, so tidy parsing is done
from the numeric grid rather than from the pretty headers.

www.ppa.com.ph currently omits the Sectigo intermediate certificate. Collection still
verifies TLS: the missing intermediate is fetched from Sectigo and added to the trust
store, rather than disabling verification.
"""

from __future__ import annotations

import ssl
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import httpx

from nightfall.clock import utc_now
from nightfall.config import Settings
from nightfall.ratelimit import PPA_QUOTA, TokenBucket
from nightfall.sources.base import (
    CommercialUse,
    Licence,
    RawRecord,
    SourceAdapter,
    SourceFamily,
    SourceOutageError,
)
from nightfall.store import RawStore

API_ROOT = "https://www.ppa.com.ph"
INTERMEDIATE_URL = "http://crt.sectigo.com/SectigoPublicServerAuthenticationCAOVR36.crt"

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SSML = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

#: Annual summary workbooks PPA publishes under /sites/default/files/qtr_stat/.
#: Filenames include a republication date; a 404 here is a coverage gap, not zero traffic.
PUBLICATIONS: tuple[tuple[str, str], ...] = (
    ("2024", f"{API_ROOT}/sites/default/files/qtr_stat/2024_Summary_Statistics_04112025.xlsx"),
    ("2023", f"{API_ROOT}/sites/default/files/qtr_stat/2023_Summary_Statistics05152024.xlsx"),
)

REGIONS: tuple[str, ...] = (
    "PHILIPPINES",
    "MANILA/N. LUZON",
    "SOUTHERN LUZON",
    "VISAYAS",
    "NORTHERN MINDANAO",
    "SOUTHERN MINDANAO",
)
PERIODS: tuple[str, ...] = ("Q1", "Q2", "Q3", "Q4", "annual")

NS = {"m": SSML}


@dataclass(frozen=True, slots=True)
class PortStat:
    year: int
    period: str
    region: str
    metric: str
    breakdown: str
    value: float
    unit: str


class PpaAdapter(SourceAdapter):
    name = "ppa"
    family = SourceFamily.STATISTICS
    licence = Licence(
        name="PPA official statistics",
        url="https://www.ppa.com.ph/",
        commercial_use=CommercialUse.PERMITTED,
        attribution="Port statistics © Philippine Ports Authority",
    )
    quota = PPA_QUOTA

    def __init__(
        self,
        store: RawStore,
        settings: Settings,
        *,
        bucket: TokenBucket | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        super().__init__(store, settings, bucket=bucket)
        self._timeout_s = timeout_s
        self._skipped: dict[str, str] = {}

    def coverage_note(self) -> str | None:
        if not self._skipped:
            return None
        detail = "; ".join(f"{key}: {reason}" for key, reason in sorted(self._skipped.items()))
        return f"PPA publications not retrieved: {detail}"

    async def collect(self) -> Sequence[RawRecord]:
        records: list[RawRecord] = []
        context = await self._tls_context()
        async with httpx.AsyncClient(
            timeout=self._timeout_s,
            headers=self.headers,
            verify=context,
        ) as client:
            for year, url in PUBLICATIONS:
                try:
                    body = await self._fetch(client, url)
                except SourceOutageError as skipped:
                    self._skipped[year] = str(skipped)
                    continue
                records.append(
                    RawRecord(
                        source=self.name,
                        request_key=f"summary/{year}",
                        body=body,
                        content_type=XLSX_TYPE,
                        observed_at=utc_now(),
                    )
                )
        if not records:
            raise SourceOutageError(
                "ppa.com.ph delivered no summary workbooks; "
                "recorded as a coverage gap rather than zero port traffic"
            )
        return records

    async def _tls_context(self) -> ssl.SSLContext:
        """Trust store plus the Sectigo intermediate www.ppa.com.ph omits from its chain."""
        await self._bucket.acquire()
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s, headers=self.headers) as client:
                response = await client.get(INTERMEDIATE_URL)
        except httpx.HTTPError as exc:
            raise SourceOutageError(
                f"could not fetch the Sectigo intermediate needed to verify ppa.com.ph: {exc}"
            ) from exc
        if response.status_code != httpx.codes.OK:
            raise SourceOutageError(
                f"Sectigo intermediate HTTP {response.status_code}; "
                "refusing to disable TLS verification for ppa.com.ph"
            )
        pem = ssl.DER_cert_to_PEM_cert(response.content)
        context = ssl.create_default_context()
        context.load_verify_locations(cadata=pem)
        return context

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> bytes:
        for attempt in range(self.max_attempts):
            await self._bucket.acquire()
            try:
                response = await client.get(url, headers={**self.headers, "accept": XLSX_TYPE})
            except httpx.HTTPError as exc:
                if attempt == self.max_attempts - 1:
                    raise SourceOutageError(f"ppa.com.ph unreachable: {exc}") from exc
                await self._backoff(attempt)
                continue
            if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                await self._backoff(attempt)
                continue
            if httpx.codes.BAD_REQUEST <= response.status_code < httpx.codes.INTERNAL_SERVER_ERROR:
                raise SourceOutageError(f"ppa.com.ph rejected {url}: HTTP {response.status_code}")
            if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
                if attempt == self.max_attempts - 1:
                    raise SourceOutageError(f"ppa.com.ph failing: HTTP {response.status_code}")
                await self._backoff(attempt)
                continue
            return response.content
        raise SourceOutageError(f"ppa.com.ph exhausted {self.max_attempts} attempts for {url}")


def rows_from_xlsx(body: bytes) -> list[list[str]]:
    """First worksheet as a grid of strings. Shared strings are resolved."""
    with ZipFile(BytesIO(body)) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", NS):
                shared.append("".join(node.text or "" for node in item.findall(".//m:t", NS)))
        sheet = ET.fromstring(archive.read(_first_sheet_path(archive)))
        rows: list[list[str]] = []
        for row in sheet.findall("m:sheetData/m:row", NS):
            values: list[str] = []
            for cell in row.findall("m:c", NS):
                kind = cell.attrib.get("t")
                node = cell.find("m:v", NS)
                raw = "" if node is None or node.text is None else node.text
                if kind == "s" and raw != "":
                    values.append(shared[int(raw)])
                else:
                    values.append(raw)
            rows.append(values)
        return rows


def _first_sheet_path(archive: ZipFile) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    by_id = {rel.attrib.get("Id"): rel.attrib.get("Target") for rel in rels}
    sheet = workbook.find("m:sheets/m:sheet", NS)
    if sheet is None:
        raise ValueError("PPA workbook has no sheet")
    target = by_id.get(sheet.attrib[REL_ID])
    if not target:
        raise ValueError("PPA workbook sheet has no target")
    if not target.startswith("xl/"):
        target = "xl/" + target.lstrip("/")
    return target


def tidy_summary(rows: Sequence[Sequence[str]], *, year: int) -> list[PortStat]:
    """Unpivot the regional quarterly grid into one row per figure.

    Each data row is a metric (and optional breakdown) followed by five blocks of six
    numbers: Q1-Q4 and the annual total, each as Philippines + five PPA regions.
    """
    stats: list[PortStat] = []
    metric = ""
    unit = ""
    for raw in rows:
        cells = [str(cell).strip() for cell in raw]
        if not any(cells):
            continue
        head = cells[0]
        if head.startswith("Source:") or head.startswith("Notes:") or head.startswith("("):
            continue
        if _looks_like_number(head) or head in {"PARTICULARS", "SUMMARY PORT STATISTICS"}:
            continue
        if (
            head
            and not _looks_like_number(cells[1] if len(cells) > 1 else "")
            and _metric_unit(head)[0]
        ):
            metric, unit = _metric_unit(head)
        label, numbers = _split_label_and_numbers(cells)
        if not numbers:
            if label and _metric_unit(label)[0]:
                metric, unit = _metric_unit(label)
            continue
        if label and _metric_unit(label)[0]:
            metric, unit = _metric_unit(label)
            breakdown = "all"
        else:
            breakdown = label or "all"
        if not metric:
            continue
        # 30 figures: 5 periods x 6 regions. Truncate rather than invent.
        usable = numbers[: len(PERIODS) * len(REGIONS)]
        for index, token in enumerate(usable):
            number = _as_float(token)
            if number is None:
                continue
            period = PERIODS[index // len(REGIONS)]
            region = REGIONS[index % len(REGIONS)]
            stats.append(
                PortStat(
                    year=year,
                    period=period,
                    region=region,
                    metric=metric,
                    breakdown=breakdown,
                    value=number,
                    unit=unit,
                )
            )
    return stats


def _split_label_and_numbers(cells: Sequence[str]) -> tuple[str, list[str]]:
    nonempty = [cell for cell in cells if cell]
    if not nonempty:
        return "", []
    if _looks_like_number(nonempty[0]):
        return "", list(nonempty)
    if len(nonempty) > 1 and _looks_like_number(nonempty[1]):
        return nonempty[0], list(nonempty[1:])
    if len(nonempty) > 2 and _looks_like_number(nonempty[2]):
        return nonempty[1], list(nonempty[2:])
    return nonempty[0], []


def _metric_unit(label: str) -> tuple[str, str]:
    text = " ".join(label.split())
    text = text.lstrip("0123456789.").strip()
    lowered = text.lower()
    if lowered.startswith("shipcall"):
        return "shipcalls", "count"
    if "cargo" in lowered:
        return "cargo_throughput", "metric_tons"
    if "container" in lowered or "teu" in lowered:
        return "container_traffic", "teu"
    if "passenger" in lowered:
        return "passenger_traffic", "count"
    if "roro" in lowered:
        return "roro_traffic", "count"
    return "", ""


def _looks_like_number(value: str) -> bool:
    return _as_float(value) is not None


def _as_float(value: str) -> float | None:
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None
