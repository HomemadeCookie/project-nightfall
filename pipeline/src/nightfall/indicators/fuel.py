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


JUMP = 0.07  # a one-day move above 7% in a product price ...
CRUDE_SHARE = 0.5  # ... is "unexplained" unless crude moved at least half as much that day


@dataclass(frozen=True)
class WeekCost:
    week_start: date  # Monday
    php_per_l: float
    n_days: int
    expected_days: int = 5


@dataclass(frozen=True)
class FuelSignal:
    product: str
    current: WeekCost
    previous: WeekCost
    delta_php_l: float  # from the jump-adjusted series
    data_through: date
    history: tuple[WeekCost, ...]
    jumps: tuple[date, ...] = ()  # unexplained one-day steps that were neutralised


def _fx_on(fx: list[dict], d: date) -> float | None:
    """Latest rate on or before ``d`` (fx rows are sorted ascending)."""
    best = None
    for r in fx:
        if r["date"] <= d:
            best = r["rate"]
        else:
            break
    return best


def adjust_jumps(
    series: list[tuple[date, float]], crude: dict[date, float]
) -> tuple[list[tuple[date, float]], list[date]]:
    """Remove one-day steps that crude does not explain.

    NY Harbor product prices occasionally step when the traded grade changes with the season (an
    RVP switch). That is not a market move, and left in it would dominate a weekly average. The step
    day is treated as flat and later days are shifted by the same amount, so real moves before and
    after are preserved.
    """
    out: list[tuple[date, float]] = []
    jumps: list[date] = []
    offset = 0.0
    prev_raw: float | None = None
    prev_day: date | None = None
    for d, v in series:
        if prev_raw is not None and prev_raw > 0:
            r = v / prev_raw - 1.0
            c0, c1 = crude.get(prev_day), crude.get(d)
            cr = (c1 / c0 - 1.0) if c0 and c1 else 0.0
            if abs(r) > JUMP and abs(cr) < CRUDE_SHARE * abs(r):
                offset -= v - prev_raw
                jumps.append(d)
        out.append((d, v + offset))
        prev_raw, prev_day = v, d
    return out, jumps


def _weekly(
    daily: list[tuple[date, float]], fx: list[dict], holidays: set[date], as_of_day: date
) -> list[WeekCost]:
    weeks: dict[date, list[float]] = {}
    for d, v in daily:
        rate = _fx_on(fx, d)
        if rate is None:
            continue
        monday = d - timedelta(days=d.weekday())
        weeks.setdefault(monday, []).append(v * rate / LITRES_PER_GALLON)
    out = []
    for w, vals in sorted(weeks.items()):
        days = [w + timedelta(days=k) for k in range(5)]
        # Trading days we could expect by now: weekdays up to as_of (the last published day is as_of - 1),
        # minus detected US holidays.
        expected = max(1, sum(1 for d in days if d < as_of_day and d not in holidays))
        out.append(WeekCost(w, sum(vals) / len(vals), len(vals), min(expected, 5)))
    return out


def _daily(
    ctx: Context, product: str
) -> tuple[list[tuple[date, float]], list[tuple[date, float]], list[date]]:
    code = PRODUCTS[product]
    raw = [(r["date"], r["value"]) for r in ctx.rows("eia_spot", "product = ?", [code], order="date")]
    crude = {r["date"]: r["value"] for r in ctx.rows("eia_spot", "product = ?", ["EPCBRENT"], order="date")}
    adjusted, jumps = adjust_jumps(raw, crude)
    return raw, adjusted, jumps


def weekly_costs(ctx: Context, product: str) -> list[WeekCost]:
    """Weekly average cost in PHP/L from the raw (unadjusted) prices, for display."""
    raw, _, _ = _daily(ctx, product)
    holidays = {r["date"] for r in ctx.rows("eia_holidays")}
    return _weekly(raw, ctx.rows("fx_usd_php", order="date"), holidays, ctx.today)


def fuel_signal(ctx: Context, product: str) -> FuelSignal | None:
    raw, adjusted, jumps = _daily(ctx, product)
    fx = ctx.rows("fx_usd_php", order="date")
    holidays = {r["date"] for r in ctx.rows("eia_holidays")}
    shown = _weekly(raw, fx, holidays, ctx.today)
    basis = _weekly(adjusted, fx, holidays, ctx.today)
    if len(shown) < 2 or len(basis) < 2:
        return None
    # The change is measured on the adjusted series; the displayed levels stay as published.
    delta = basis[-1].php_per_l - basis[-2].php_per_l
    recent = tuple(j for j in jumps if (ctx.today - j).days <= 14)
    return FuelSignal(product, shown[-1], shown[-2], delta, raw[-1][0], tuple(shown[-13:]), recent)
