from __future__ import annotations

import re
from datetime import date, timedelta

from nightfall.core.lake import Lake
from nightfall.core.reference import price_items
from nightfall.stage.common import available_on, make_table, num, parse_date

US_PRODUCTS = ("EPD2DXL0", "EPMRU", "EPCWTI")  # priced in US markets: closed on US holidays


def drop_carry_forward(rows: dict[tuple, dict]) -> tuple[dict[tuple, dict], list[date]]:
    """EIA repeats the previous US price on US holidays. A holiday has a clear signature: every US
    product is unchanged from its previous observation while Brent, which keeps trading, has moved.
    Requiring both stops a genuinely flat stretch from being mistaken for a holiday."""
    days = sorted({d for d, _ in rows})
    holidays: list[date] = []
    last: dict[str, float] = {}
    last_brent: float | None = None
    for d in days:
        us = {p: rows[(d, p)]["value"] for p in US_PRODUCTS if (d, p) in rows}
        brent = rows[(d, "EPCBRENT")]["value"] if (d, "EPCBRENT") in rows else None
        repeats = bool(us) and all(p in last and last[p] == v for p, v in us.items())
        if repeats and brent is not None and last_brent is not None and brent != last_brent:
            holidays.append(d)
            for p in us:
                del rows[(d, p)]
        else:
            last.update(us)
        if brent is not None:
            last_brent = brent
    return rows, holidays


def stage_eia(lake: Lake):
    rows: dict[tuple, dict] = {}
    for rec in lake.iter_raw("eia", "spot_prices"):
        for r in rec["payload"]:
            v = num(r.get("value"))
            if v is None:
                continue
            d = parse_date(r["period"])
            rows[(d, r["product"])] = {
                "date": d,
                "product": r["product"],
                "value": v,
                "units": r.get("units"),
                "available_on": available_on(d, "eia"),
            }
    rows, holidays = drop_carry_forward(rows)
    cols = {"date": "date", "product": "str", "value": "f", "units": "str", "available_on": "date"}
    hcols = {"date": "date", "available_on": "date"}
    return {
        "eia_spot": make_table(sorted(rows.values(), key=lambda x: (x["product"], x["date"])), cols),
        "eia_holidays": make_table(
            [{"date": d, "available_on": available_on(d, "eia")} for d in holidays], hcols
        ),
    }


def stage_fx(lake: Lake):
    rows: dict[date, dict] = {}
    for rec in lake.iter_raw("frankfurter", "usd_php"):
        for d, rates in rec["payload"].get("rates", {}).items():
            dd = parse_date(d)
            rows[dd] = {"date": dd, "rate": float(rates["PHP"]), "available_on": available_on(dd, "fx")}
    cols = {"date": "date", "rate": "f", "available_on": "date"}
    return {"fx_usd_php": make_table(sorted(rows.values(), key=lambda x: x["date"]), cols)}


def stage_pink_sheet(lake: Lake):
    rows: dict[tuple, dict] = {}
    for rec in lake.iter_raw("worldbank", "pink_sheet_monthly"):
        for r in rec["payload"]:
            y, m = map(int, r["period"].split("-"))
            start = date(y, m, 1)
            end = (date(y + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)
            rows[(start, r["series"])] = {
                "period_start": start,
                "series": r["series"],
                "value": r["value"],
                "available_on": available_on(end, "pink_sheet"),
            }
    cols = {"period_start": "date", "series": "str", "value": "f", "available_on": "date"}
    return {
        "pink_sheet": make_table(sorted(rows.values(), key=lambda x: (x["series"], x["period_start"])), cols)
    }


# -- DA weekly retail prices (PDF text) -------------------------------------------------------
MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        1,
    )
}
_MONTH = "|".join(MONTHS)
_PERIOD = re.compile(
    rf"period\s*of\s*(?P<m1>{_MONTH})\s*(?P<d1>\d+)\s*(?:-\s*(?:(?P<m2>{_MONTH})\s*)?(?P<d2>\d+))?\s*,?\s*(?P<y>\d{{4}})",
    re.I,
)
# OCR drops spaces and reads "kg" as "ka"/"kq"/"ko"; text-layer PDFs are clean, so one tolerant pattern serves both.
_ROW = re.compile(
    r"^(?P<item>.+?)(?:\s+(?P<unit>kg|ka|kq|ko|ml|L|l|pc|g))?\s*(?P<price>\d[\d,]*[.,]\d{2}|[-\u2014\u2013])\s*$"
)
_UNIT = {"ka": "kg", "kq": "kg", "ko": "kg", "l": "L"}
_CATEGORY = re.compile(r"^[A-Z][A-Z0-9 &/\-\(\)']{3,}$")


def _clean_item(item: str) -> str:
    """OCR reads ( ) as [ ] or { }; normalise so one set of patterns serves text and scanned files."""
    return item.translate(str.maketrans("[{]}", "(())")).strip()


def _unit_from_item(item: str) -> str:
    low = item.lower()
    return "L" if "liter" in low or "litre" in low else "ml" if "ml" in low else "kg"


def parse_period(text: str) -> tuple[date, date] | None:
    m = _PERIOD.search(text)
    if not m:
        return None
    y = int(m["y"])
    m1 = MONTHS[m["m1"].capitalize()]
    m2 = MONTHS[m["m2"].capitalize()] if m["m2"] else m1
    end = date(y, m2, int(m["d2"] or m["d1"]))
    start = date(y - 1 if m1 > m2 else y, m1, int(m["d1"]))
    return start, end


def parse_weekly_text(text: str) -> tuple[tuple[date, date] | None, list[dict]]:
    period, category, out = parse_period(text), "", []
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        m = _ROW.match(line)
        if m:
            raw = m["price"]
            price = None if raw in "-\u2014\u2013" else float(raw.replace(",", "." if raw[-3] == "," else ""))
            item = _clean_item(m["item"])
            unit = _UNIT.get(m["unit"], m["unit"]) if m["unit"] else _unit_from_item(item)
            out.append({"category": category, "item": item, "unit": unit, "price": price})
        elif _CATEGORY.match(line) and "COMMODITY" not in line:
            category = line
    return period, out


def _drop_misreads(mapped: list[dict], lo: float = 0.4, hi: float = 2.5) -> list[dict]:
    """Drop prices far from the item's median (a lost decimal point in OCR, say). Staples do not move 2.5x."""
    by_item: dict[str, list[float]] = {}
    for r in mapped:
        by_item.setdefault(r["item_id"], []).append(r["price"])
    med = {k: sorted(v)[len(v) // 2] for k, v in by_item.items()}
    return [r for r in mapped if lo * med[r["item_id"]] <= r["price"] <= hi * med[r["item_id"]]]


def stage_da_weekly(lake: Lake):
    items = [
        (r["item_id"], re.compile(re.sub(r"(?<!\\) ", r"\\s*", r["match"]), re.I)) for r in price_items()
    ]
    best: dict[tuple, dict] = {}
    for rec in lake.iter_raw("da_prices", "weekly_ncr"):
        url = rec["request"].get("url", "")
        period, rows = parse_weekly_text(rec["payload"]["text"])
        if period is None:
            continue
        revised = "/Revised-" in url
        for r in rows:
            key = (period[0], r["category"], r["item"])
            prev = best.get(key)
            if prev and prev["revised"] and not revised:
                continue
            best[key] = {
                "week_start": period[0],
                "week_end": period[1],
                "category": r["category"],
                "item": r["item"],
                "unit": r["unit"],
                "price": r["price"],
                "revised": revised,
                "url": url,
                "available_on": available_on(period[1], "da_weekly"),
            }
    rows = sorted(best.values(), key=lambda x: (x["week_start"], x["category"], x["item"]))
    cols = {
        "week_start": "date",
        "week_end": "date",
        "category": "str",
        "item": "str",
        "unit": "str",
        "price": "f",
        "revised": "b",
        "url": "str",
        "available_on": "date",
    }
    mapped: list[dict] = []
    for r in rows:
        if r["price"] is None:
            continue
        hay = f"{r['category']}|{r['item']}"
        for item_id, rx in items:
            if rx.search(hay):
                mapped.append(
                    {
                        "item_id": item_id,
                        "week_start": r["week_start"],
                        "week_end": r["week_end"],
                        "price": r["price"],
                        "unit": r["unit"],
                        "available_on": r["available_on"],
                    }
                )
                break
    mcols = {
        "item_id": "str",
        "week_start": "date",
        "week_end": "date",
        "price": "f",
        "unit": "str",
        "available_on": "date",
    }
    return {"da_weekly_all": make_table(rows, cols), "price_weekly": make_table(mapped, mcols)}
