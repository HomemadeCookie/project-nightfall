"""Walk-forward backtests. Every origin replays the data exactly as it stood at that time."""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime, time, timedelta

from nightfall.answers.common import key_ports
from nightfall.core.context import Context
from nightfall.core.reference import reference_dir
from nightfall.eval.metrics import accuracy, balanced_accuracy, mae, majority
from nightfall.indicators.fuel import fuel_signal
from nightfall.indicators.ports import calls_series, forecast_next_week
from nightfall.indicators.prices import HORIZON_WEEKS, direction, pct, weekly_prices

MIN_ORIGINS = 26
SHIP_MARGIN = 0.05


def _eod(d: date) -> datetime:
    return datetime.combine(d, time(23, 59), tzinfo=UTC)


# -- ports.pressure: next-7-day call forecast vs repeating last week ---------------------------
def backtest_ports(ctx: Context, weeks: int = 52) -> dict:
    out: dict[str, dict] = {}
    for port in key_ports():
        series = calls_series(ctx, port["portwatch_id"])
        vals = [v for _, v in series]
        dates = [d for d, _ in series]
        origins = list(range(len(vals) - 7 - 7 * weeks, len(vals) - 7, 7))
        origins = [o for o in origins if o >= 7 * 12]
        if len(origins) < MIN_ORIGINS or sum(vals[-28:]) < 40:
            out[port["port_id"]] = {
                "n_origins": len(origins),
                "ship_forecast": False,
                "reason": "too little history or traffic",
            }
            continue
        actual = [sum(vals[o + 1 : o + 8]) for o in origins]
        results = {}
        for model in ("naive", "blend4"):
            preds = [forecast_next_week(vals[: o + 1], model) for o in origins]
            results[model] = mae(actual, preds)
        best = min(results, key=results.get)
        ship = best != "naive" and results[best] <= results["naive"] * (1 - SHIP_MARGIN)
        out[port["port_id"]] = {
            "n_origins": len(origins),
            "mae_naive": round(results["naive"], 2),
            "mae_blend4": round(results["blend4"], 2),
            "mean_weekly_calls": round(sum(actual) / len(actual), 1),
            "model": best,
            "ship_forecast": ship,
            "first_origin": dates[origins[0]].isoformat(),
            "last_origin": dates[origins[-1]].isoformat(),
        }
    shipped = [k for k, v in out.items() if v.get("ship_forecast")]
    return {
        "status": "experimental",
        "ports": out,
        "summary": f"Forecast beats 'repeat last week' by >=5% MAE at {len(shipped)} of {len(out)} key ports.",
    }


# -- staples.price_direction -------------------------------------------------------------------
def backtest_prices(ctx: Context, weeks: int = 60) -> dict:
    from nightfall.answers.questions.staples_price_direction import predict_at
    from nightfall.core import reference

    items_out: dict[str, dict] = {}
    for item in reference.price_items():
        item_id = item["item_id"]
        prices = weekly_prices(ctx, item_id)
        if len(prices) < 60:
            items_out[item_id] = {"ship": False, "reason": f"only {len(prices)} weeks of history"}
            continue
        first = max(len(prices) - HORIZON_WEEKS - weeks, 52)
        actual, model_pred, persist = [], [], []
        for j in range(first, len(prices) - HORIZON_WEEKS):
            pred = predict_at(ctx.at(_eod(prices[j].available_on)), item_id)
            if pred is None:
                continue
            actual.append(direction(pct(prices[j + HORIZON_WEEKS].price, prices[j].price)))
            model_pred.append(pred.label)
            persist.append(pred.persistence_label)
        if len(actual) < MIN_ORIGINS or len(set(actual)) < 2:
            items_out[item_id] = {
                "ship": False,
                "n_origins": len(actual),
                "reason": "too few origins or classes",
            }
            continue
        maj = majority(actual)
        ba_model, ba_persist = balanced_accuracy(actual, model_pred), balanced_accuracy(actual, persist)
        ba_major = balanced_accuracy(actual, [maj] * len(actual))
        ship = ba_model >= max(ba_persist, ba_major) + SHIP_MARGIN
        items_out[item_id] = {
            "n_origins": len(actual),
            "ba_model": round(ba_model, 3),
            "ba_persistence": round(ba_persist, 3),
            "ba_majority": round(ba_major, 3),
            "acc_model": round(accuracy(actual, model_pred), 3),
            "acc_persistence": round(accuracy(actual, persist), 3),
            "class_balance": {c: actual.count(c) for c in sorted(set(actual))},
            "ship": ship,
        }
    shipped = [k for k, v in items_out.items() if v.get("ship")]
    status = "experimental" if shipped else "unvalidated"
    return {
        "status": status,
        "items": items_out,
        "summary": f"Model beats persistence and majority-class by >=5 points of balanced accuracy for "
        f"{len(shipped)} of {len(items_out)} items. Only those items publish a forecast.",
    }


# -- fuel.next_week ----------------------------------------------------------------------------
def load_fuel_truth() -> list[dict]:
    path = reference_dir().parent / "eval" / "ground_truth" / "fuel_adjustments.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [
            {
                **r,
                "delta_php_l": float(r["delta_php_l"]),
                "effective_date": date.fromisoformat(r["effective_date"]),
            }
            for r in csv.DictReader(fh)
        ]


def backtest_fuel(ctx: Context) -> dict:
    truth = load_fuel_truth()
    if len(truth) < 8:
        return {
            "status": "unvalidated",
            "n_observations": len(truth),
            "summary": f"{len(truth)} official adjustments recorded; at least 8 are needed to evaluate. "
            "The collector appends to eval/ground_truth/fuel_adjustments.csv.",
        }
    actual_dir, pred_dir, actual, pred = [], [], [], []
    for row in truth:
        as_of = _eod(row["effective_date"] - timedelta(days=3))  # Saturday before the Tuesday
        sig = fuel_signal(ctx.at(as_of), row["product"])
        if sig is None:
            continue
        actual.append(row["delta_php_l"])
        pred.append(sig.delta_php_l)
        actual_dir.append(direction(row["delta_php_l"], 0.5))
        pred_dir.append(direction(sig.delta_php_l, 0.5))
    if len(actual) < 8:
        return {
            "status": "unvalidated",
            "n_observations": len(actual),
            "summary": "Too few overlapping weeks.",
        }
    return {
        "status": "experimental" if balanced_accuracy(actual_dir, pred_dir) >= 0.6 else "unvalidated",
        "n_observations": len(actual),
        "mae_php_l": round(mae(actual, pred), 3),
        "mae_zero_baseline": round(mae(actual, [0.0] * len(actual)), 3),
        "balanced_accuracy": round(balanced_accuracy(actual_dir, pred_dir), 3),
        "accuracy": round(accuracy(actual_dir, pred_dir), 3),
    }
