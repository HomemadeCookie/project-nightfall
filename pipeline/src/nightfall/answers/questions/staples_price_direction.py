"""staples.price_direction: will an NCR retail staple price rise over the next 4 weeks?

One small classifier per item, refit at every forecast origin on data that was public at the time.
The same ``predict_at`` function backs the live answer and the walk-forward backtest, so the
backtest measures exactly what is shipped. Items ship only when the backtest beats persistence.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from nightfall.answers.common import load_report, make_answer, model_info, staleness_days
from nightfall.core import reference
from nightfall.core.context import Context
from nightfall.core.contracts import Driver, Evidence, LocalizedText
from nightfall.indicators.prices import (
    FEATURE_NAMES,
    HORIZON_WEEKS,
    WeekPrice,
    diesel_weekly,
    direction,
    features_at,
    fx_weekly,
    pct,
    weekly_prices,
    world_series,
)

QUESTION_ID, VERSION = "staples.price_direction", 1
SOURCES = ["da_prices", "worldbank", "frankfurter", "eia"]
MIN_TRAIN = 40
CLASSES = ["down", "flat", "up"]


@dataclass(frozen=True)
class Prediction:
    item_id: str
    origin_week: object
    probs: dict[str, float]
    label: str
    persistence_label: str
    last_change_4w: float
    n_train: int
    top_features: list[tuple[str, float]]


def world_for(item_id: str) -> list[str]:
    """World Bank series that proxy this item's global price (empty if none apply)."""
    cid = {r["item_id"]: r["commodity_id"] for r in reference.price_items()}.get(item_id)
    return next((c["worldbank_series"] for c in reference.commodities() if c["commodity_id"] == cid), [])


def predict_at(ctx: Context, item_id: str) -> Prediction | None:
    """Fit on everything knowable at ``ctx.as_of`` and predict the direction 4 weeks ahead."""
    prices = weekly_prices(ctx, item_id)
    if len(prices) < MIN_TRAIN + 12 + HORIZON_WEEKS:
        return None
    world = world_series(ctx, world_for(item_id))
    fx, diesel = fx_weekly(ctx), diesel_weekly(ctx)

    X, y = [], []
    known = [p for p in prices]
    for j in range(len(known) - HORIZON_WEEKS):
        target = known[j + HORIZON_WEEKS]
        feats = features_at(known, j, world, fx, diesel)
        if feats is None:
            continue
        X.append(feats)
        y.append(direction(pct(target.price, known[j].price)))
    last = len(known) - 1
    x_now = features_at(known, last, world, fx, diesel)
    if x_now is None or len(X) < MIN_TRAIN or len(set(y)) < 2:
        return None

    scaler = StandardScaler().fit(np.array(X))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        clf = LogisticRegression(C=0.3, class_weight="balanced", max_iter=1000)
        clf.fit(scaler.transform(np.array(X)), y)
    proba = clf.predict_proba(scaler.transform(np.array([x_now])))[0]
    probs = {c: 0.0 for c in CLASSES}
    probs.update({c: float(p) for c, p in zip(clf.classes_, proba, strict=True)})
    label = max(probs, key=probs.get)

    if clf.coef_.shape[0] == 1:  # binary fit: one row, for classes_[1]
        coefs = clf.coef_[0] if label == clf.classes_[1] else -clf.coef_[0]
    else:
        coefs = clf.coef_[list(clf.classes_).index(label)]
    z = scaler.transform(np.array([x_now]))[0]
    contrib = sorted(zip(FEATURE_NAMES, (coefs * z).tolist(), strict=True), key=lambda t: -abs(t[1]))[:3]
    chg4 = x_now[0]
    return Prediction(item_id, known[last].week_start, probs, label, direction(chg4), chg4, len(X), contrib)


def run(ctx: Context, prior=None) -> list:
    report = load_report(QUESTION_ID) or {}
    ship = {k for k, v in (report.get("items") or {}).items() if v.get("ship")}
    answers = []
    for item in reference.price_items():
        item_id = item["item_id"]
        prices = weekly_prices(ctx, item_id)
        if not prices:
            continue
        latest: WeekPrice = prices[-1]
        stale = staleness_days(ctx, latest.week_end)
        pred = predict_at(ctx, item_id) if stale <= 21 else None
        shipped = item_id in ship
        chg4 = pct(latest.price, prices[-5].price) if len(prices) >= 5 else 0.0
        label_en, label_fil = item["label_en"], item["label_fil"]
        if pred is None or not shipped:
            verdict = "no_call"
            reason = (
                "not enough history"
                if pred is None
                else "the model has not beaten a simple trend baseline in backtests"
            )
            en = (
                f"{label_en}: ₱{latest.price:.2f}/{item['unit_hint']} "
                f"(NCR weekly average), {chg4 * 100:+.1f}% over 4 weeks. No forecast: {reason}."
            )
            fil = (
                f"{label_fil}: ₱{latest.price:.2f} (lingguhang average sa NCR), {chg4 * 100:+.1f}% sa 4 na linggo. "
                "Walang hula sa ngayon."
            )
            conf, probs, drivers = "none", None, []
        else:
            verdict = pred.label
            probs = {k: round(v, 2) for k, v in pred.probs.items()}
            word_en = {"up": "likely to rise", "down": "likely to fall", "flat": "likely to hold steady"}[
                verdict
            ]
            word_fil = {"up": "malamang tumaas", "down": "malamang bumaba", "flat": "malamang hindi gumalaw"}[
                verdict
            ]
            en = f"{label_en} in NCR is {word_en} over the next 4 weeks (now ₱{latest.price:.2f}, {chg4 * 100:+.1f}% in 4 weeks)."
            fil = f"Ang presyo ng {label_fil.lower()} sa NCR ay {word_fil} sa susunod na 4 na linggo (ngayon ₱{latest.price:.2f})."
            conf = "medium" if max(pred.probs.values()) >= 0.6 else "low"
            drivers = [
                Driver(feature=f, value=round(v, 2), effect="+" if v > 0 else "-")
                for f, v in pred.top_features
            ]
        answers.append(
            make_answer(
                ctx,
                question_id=QUESTION_ID,
                version=VERSION,
                scope={"item": item_id, "region": "NCR"},
                verdict=verdict,
                text=LocalizedText(en=en, fil=fil),
                sources=SOURCES,
                confidence=conf,
                coverage=1.0 if stale <= 21 else 0.0,
                data_through=latest.week_end.isoformat(),
                model=model_info(
                    QUESTION_ID,
                    "logit_walkforward",
                    "2026-10",
                    "experimental",
                    "Per-item logistic regression refit weekly; ships only if it beats persistence.",
                ),
                value={
                    "item": label_en,
                    "price_php": latest.price,
                    "change_4w": round(chg4, 4),
                    "probs": probs,
                    "week_end": latest.week_end.isoformat(),
                },
                drivers=drivers,
                evidence=[Evidence(kind="price", label="Latest NCR weekly average (₱)", value=latest.price)],
                caveats=[
                    "Prices are Metro Manila market averages from DA Bantay Presyo; other regions are not covered.",
                    "Direction thresholds: more than +/-2% over 4 weeks.",
                ],
            )
        )
    return answers
