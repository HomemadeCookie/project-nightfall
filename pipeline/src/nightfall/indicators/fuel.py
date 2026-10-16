"""Fuel cost indicator: weekly average landed-cost proxy in PHP per litre.

The DOE adjustment each Tuesday follows the previous week's Singapore (MOPS) product prices and
the peso. We do not have MOPS, so US NY Harbor spot prices stand in as a correlated proxy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from nightfall.core.context import Context

LITRES_PER_GALLON = 3.78541
PRODUCTS = {"diesel": "EPD2DXL0", "gasoline": "EPMRU"}


@dataclass(frozen=True)
class WeekCost:
    week_start: date  # Monday
    php_per_l: float
    n_days: int


@dataclass(frozen=True)
class FuelSignal:
    product: str
    current: WeekCost
    previous: WeekCost
    delta_php_l: float
    data_through: date
    history: tuple[WeekCost, ...]


def _fx_on(fx: list[dict], d: date) -> float | None:
    """Latest rate on or before ``d`` (fx rows are sorted ascending)."""
    best = None
    for r in fx:
        if r["date"] <= d:
            best = r["rate"]
        else:
            break
    return best


def weekly_costs(ctx: Context, product: str) -> list[WeekCost]:
    code = PRODUCTS[product]
    px = ctx.rows("eia_spot", "product = ?", [code], order="date")
    fx = ctx.rows("fx_usd_php", order="date")
    weeks: dict[date, list[float]] = {}
    for r in px:
        rate = _fx_on(fx, r["date"])
        if rate is None:
            continue
        monday = r["date"] - timedelta(days=r["date"].weekday())
        weeks.setdefault(monday, []).append(r["value"] * rate / LITRES_PER_GALLON)
    return [WeekCost(w, sum(v) / len(v), len(v)) for w, v in sorted(weeks.items())]


def fuel_signal(ctx: Context, product: str) -> FuelSignal | None:
    weeks = weekly_costs(ctx, product)
    if len(weeks) < 2:
        return None
    px = ctx.rows("eia_spot", "product = ?", [PRODUCTS[product]], order="date DESC")
    cur, prev = weeks[-1], weeks[-2]
    return FuelSignal(product, cur, prev, cur.php_per_l - prev.php_per_l, px[0]["date"], tuple(weeks[-13:]))
