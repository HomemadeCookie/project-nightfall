"""Rule-based extraction of supply-chain events from news headlines.

Rules first, not an LLM: they are free, deterministic, testable, and good enough for the two
event types that matter most (weekly fuel adjustments and sea-trip suspensions). Every event keeps
the headline URL so a human can verify it before it is trusted as ground truth.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from nightfall.core.reference import ferry_routes
from nightfall.core.time import next_weekday, to_manila

PESO = r"(?:P|₱|PHP|Php)\s?(\d+(?:\.\d{1,2})?)"
_AMOUNT = re.compile(PESO)
_PRODUCT = re.compile(r"\b(diesel|gasoline|kerosene)\b", re.I)
_DOWN = re.compile(
    r"\b(roll\s?back|rolls?\s?back|rollback|cut|cuts|reduc\w+|decreas\w+|drop\w*|lower\w*|down|bawas)\b", re.I
)
_UP = re.compile(r"\b(hike\w*|increas\w+|rise\w*|rising|up|taas|bump\w*)\b", re.I)
_SPLIT = re.compile(r"[;,]|\b(?:while|but|as|and)\b", re.I)
_LITER = re.compile(r"(?:per|/|a)\s?(?:liter|litre|l)\b", re.I)


def extract_fuel_adjustments(items: list[dict]) -> list[dict]:
    """Candidate weekly pump-price adjustments from headlines.

    ``items`` need ``title``, ``url`` and ``published`` (tz-aware datetime). The effective date is the
    Tuesday on or after publication (Manila time), since adjustments take effect on Tuesdays.
    """
    out: list[dict] = []
    for it in items:
        title = it.get("title") or ""
        if not _LITER.search(title) and "price" not in title.lower():
            continue
        published: datetime | None = it.get("published")
        if published is None:
            continue
        day = to_manila(published).date()
        effective = day if day.weekday() == 1 else next_weekday(day, 1)
        clauses = [c for c in _SPLIT.split(title) if c]
        last_product: str | None = None
        for clause in clauses:
            prods = _PRODUCT.findall(clause)
            amt = _AMOUNT.search(clause)
            if prods:
                last_product = prods[-1].lower()
            if not amt or not last_product:
                continue
            down, up = bool(_DOWN.search(clause)), bool(_UP.search(clause))
            if down == up:  # ambiguous or no direction
                continue
            value = float(amt.group(1)) * (-1 if down else 1)
            out.append(
                {
                    "effective_date": effective,
                    "product": last_product,
                    "delta_php_l": value,
                    "url": it.get("url"),
                    "title": title,
                }
            )
    # A headline often repeats one product across clauses; keep one candidate per (date, product, url).
    seen, unique = set(), []
    for e in out:
        key = (e["effective_date"], e["product"], e["url"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


_SUSPEND = re.compile(r"\b(suspend\w*|cancel\w*|no sail\w*|halt\w*|stranded|banned|prohibit\w*)\b", re.I)
_TRIPS = re.compile(r"\b(sea trips?|sailings?|ferry|ferries|ro-?ro|vessels?|coast guard|pcg|ports?)\b", re.I)
_RESUME = re.compile(r"\b(resum\w+|lift\w*|allowed to sail)\b", re.I)

# Words that identify a corridor in a headline, from the reference data.
_PLACE_WORDS = {
    "batangas-calapan": ["batangas", "calapan"],
    "matnog-allen": ["matnog", "allen"],
    "liloan-lipata": ["liloan", "lipata", "surigao"],
    "cebu-tagbilaran": ["tagbilaran", "bohol"],
    "cebu-ormoc": ["ormoc"],
    "iloilo-bacolod": ["iloilo", "bacolod", "guimaras"],
    "dapitan-dumaguete": ["dapitan", "dumaguete"],
    "roxas-caticlan": ["caticlan", "boracay", "roxas"],
}


def extract_sea_trip_notices(items: list[dict]) -> list[dict]:
    """Headlines about suspended (or resumed) sea trips, tagged with the ferry corridors they name."""
    known = {r["route_id"] for r in ferry_routes()}
    out = []
    for it in items:
        title = (it.get("title") or "") + " " + (it.get("teaser") or "")
        if not _TRIPS.search(title):
            continue
        suspended, resumed = bool(_SUSPEND.search(title)), bool(_RESUME.search(title))
        if not (suspended or resumed):
            continue
        low = title.lower()
        routes = sorted(
            rid for rid, words in _PLACE_WORDS.items() if rid in known and any(w in low for w in words)
        )
        out.append(
            {
                "kind": "resumed" if resumed and not suspended else "suspended",
                "routes": routes,
                "published": it.get("published"),
                "url": it.get("url"),
                "title": it.get("title"),
            }
        )
    return out


def as_date(d: date | datetime) -> date:
    return d.date() if isinstance(d, datetime) else d
