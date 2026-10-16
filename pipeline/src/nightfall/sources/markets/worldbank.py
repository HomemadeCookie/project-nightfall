"""World Bank Commodity Price Data ("Pink Sheet"), monthly. CC BY 4.0."""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import datetime

import openpyxl

from nightfall.core.envelope import Envelope
from nightfall.core.license import License
from nightfall.sources.base import Source
from nightfall.sources.registry import register

URL = (
    "https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/"
    "related/CMO-Historical-Data-Monthly.xlsx"
)
WANTED = {
    "Crude oil, Brent": "brent",
    "Rice, Thai 5%": "rice_thai_5",
    "Rice, Viet Namese 5%": "rice_viet_5",
    "Wheat, US HRW": "wheat_us_hrw",
    "Sugar, world": "sugar_world",
    "Palm oil": "palm_oil",
    "Coconut oil": "coconut_oil",
    "Maize": "maize",
    "Soybean meal": "soybean_meal",
}


def parse_pink_sheet(content: bytes) -> list[dict]:
    """Long-format rows ``{period, series, value}`` for the commodities we use."""
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    rows = list(wb["Monthly Prices"].iter_rows(values_only=True))
    header_idx = next(
        i for i, r in enumerate(rows) if r and any(str(c).strip() == "Crude oil, Brent" for c in r)
    )
    cols = {
        j: WANTED[str(name).strip()]
        for j, name in enumerate(rows[header_idx])
        if name and str(name).strip() in WANTED
    }
    out: list[dict] = []
    for r in rows[header_idx + 1 :]:
        label = str(r[0] or "")
        if "M" not in label or not label[:4].isdigit():  # data rows look like 1960M01
            continue
        year, month = label.split("M")
        for j, key in cols.items():
            v = r[j]
            if isinstance(v, int | float):  # missing values are the string "…"
                out.append({"period": f"{int(year):04d}-{int(month):02d}", "series": key, "value": float(v)})
    return out


@register
class WorldBankPinkSheet(Source):
    name = "worldbank"
    license = [License.ATTRIBUTION]
    cadence = "weekly"
    attribution = "World Bank Commodity Price Data (The Pink Sheet), CC BY 4.0"

    def fetch(self, now: datetime) -> Iterator[Envelope]:
        content = self.http.get(URL).content
        rows = parse_pink_sheet(content)
        yield self.envelope("pink_sheet_monthly", rows, now=now, request={"url": URL})
