"""Retail price series and the features that drive the price-direction model."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date

from nightfall.core.context import Context
from nightfall.indicators.fuel import weekly_costs

FLAT_BAND = 0.02  # +/-2% over 4 weeks counts as "flat"
HORIZON_WEEKS = 4


@dataclass(frozen=True)
class WeekPrice:
    week_start: date
    week_end: date
    price: float
    available_on: date


def weekly_prices(ctx: Context, item_id: str) -> list[WeekPrice]:
    rows = ctx.rows("price_weekly", "item_id = ?", [item_id], order="week_start")
    by_week: dict[date, WeekPrice] = {}
    for r in rows:
        by_week[r["week_start"]] = WeekPrice(r["week_start"], r["week_end"], r["price"], r["available_on"])
    return [by_week[k] for k in sorted(by_week)]


def direction(change: float, band: float = FLAT_BAND) -> str:
    return "up" if change > band else "down" if change < -band else "flat"


def pct(a: float, b: float) -> float:
    return (a / b - 1.0) if b else 0.0


def world_series(ctx: Context, series: list[str]) -> list[tuple[date, float]]:
    """Mean of the named Pink Sheet series per month, oldest first."""
    if not series:
        return []
    rows = ctx.rows(
        "pink_sheet", f"series IN ({','.join('?' * len(series))})", list(series), order="period_start"
    )
    by_month: dict[date, list[float]] = {}
    for r in rows:
        by_month.setdefault(r["period_start"], []).append(r["value"])
    return [(m, statistics.fmean(v)) for m, v in sorted(by_month.items())]


def features_at(
    prices: list[WeekPrice],
    j: int,
    world: list[tuple[date, float]],
    fx: list[tuple[date, float]],
    diesel: list[tuple[date, float]],
) -> list[float] | None:
    """Feature vector for origin week index ``j`` using only data up to that week."""
    if j < 12:
        return None
    cur = prices[j]
    f1 = pct(cur.price, prices[j - 4].price)
    f2 = pct(cur.price, prices[j - 12].price)
    f3 = pct(cur.price, statistics.fmean(p.price for p in prices[max(0, j - 26) : j + 1]))
    w = [v for d, v in world if d <= cur.week_start]
    f4 = pct(w[-1], w[-4]) if len(w) >= 4 else 0.0
    fxs = [v for d, v in fx if d <= cur.week_end]
    f5 = pct(fxs[-1], fxs[-8]) if len(fxs) >= 8 else 0.0
    dz = [v for d, v in diesel if d <= cur.week_start]
    f6 = pct(dz[-1], dz[-5]) if len(dz) >= 5 else 0.0
    return [f1, f2, f3, f4, f5, f6]


FEATURE_NAMES = ["change_4w", "change_12w", "vs_26w_mean", "world_price_3m", "usd_php_8w", "diesel_cost_4w"]


def fx_weekly(ctx: Context) -> list[tuple[date, float]]:
    return [(r["date"], r["rate"]) for r in ctx.rows("fx_usd_php", order="date")]


def diesel_weekly(ctx: Context) -> list[tuple[date, float]]:
    return [(w.week_start, w.php_per_l) for w in weekly_costs(ctx, "diesel")]
