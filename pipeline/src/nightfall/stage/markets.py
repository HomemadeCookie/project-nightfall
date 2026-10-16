from __future__ import annotations

import re
from datetime import date, timedelta

from nightfall.core.lake import Lake
from nightfall.core.reference import price_items
from nightfall.stage.common import available_on, make_table, num, parse_date


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
    cols = {"date": "date", "product": "str", "value": "f", "units": "str", "available_on": "date"}
    return {"eia_spot": make_table(sorted(rows.values(), key=lambda x: (x["product"], x["date"])), cols)}


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
_PERIOD = re.compile(
    r"period of\s+(?P<m1>[A-Za-z]+)\s+(?P<d1>\d+)\s*(?:-\s*(?:(?P<m2>[A-Za-z]+)\s+)?(?P<d2>\d+))?,?\s*(?P<y>\d{4})"
)
_ROW = re.compile(r"^(?P<item>.+?)\s+(?P<unit>kg|ml|L|pc|g)\s+(?P<price>\d[\d,]*\.\d+|-)\s*$")
_CATEGORY = re.compile(r"^[A-Z][A-Z0-9 &/\-\(\)']{3,}$")


def parse_period(text: str) -> tuple[date, date] | None:
    m = _PERIOD.search(text)
    if not m or m["m1"] not in MONTHS:
        return None
    y = int(m["y"])
    m1 = MONTHS[m["m1"]]
    m2 = MONTHS.get(m["m2"] or "", m1)
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
            price = None if m["price"] == "-" else float(m["price"].replace(",", ""))
            out.append({"category": category, "item": m["item"].strip(), "unit": m["unit"], "price": price})
        elif _CATEGORY.match(line) and "COMMODITY" not in line:
            category = line
    return period, out


def stage_da_weekly(lake: Lake):
    items = [(r["item_id"], re.compile(r["match"], re.I)) for r in price_items()]
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
