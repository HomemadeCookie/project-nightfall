"""fuel.next_week: expected direction of next Tuesday's pump-price adjustment."""

from __future__ import annotations

from nightfall.answers.common import fmt_date, make_answer, manila_today, model_info, staleness_days
from nightfall.core.context import Context
from nightfall.core.contracts import Driver, Evidence, LocalizedText
from nightfall.core.time import next_weekday
from nightfall.indicators.fuel import fuel_signal

QUESTION_ID, VERSION = "fuel.next_week", 1
SOURCES = ["eia", "frankfurter"]
FLAT_BAND_PHP = 0.50
PASS_THROUGH = 1.0  # refit against official adjustments once ground truth accumulates
LABEL = {"diesel": ("Diesel", "Diesel"), "gasoline": ("Gasoline", "Gasolina")}


def run(ctx: Context, prior=None) -> list:
    answers = []
    effective = next_weekday(manila_today(ctx), 1)  # Tuesday
    for product in ("diesel", "gasoline"):
        sig = fuel_signal(ctx, product)
        if sig is None:
            continue
        stale = staleness_days(ctx, sig.data_through)
        coverage = 0.0 if stale > 6 else min(sig.current.n_days / sig.current.expected_days, 1.0)
        delta = round(sig.delta_php_l * PASS_THROUGH, 2)
        name_en, name_fil = LABEL[product]
        if coverage < 0.5:
            verdict, conf = "insufficient_data", "none"
            en = f"Not enough price data yet this week to call {name_en.lower()}."
            fil = f"Kulang pa ang datos ngayong linggo para sa {name_fil.lower()}."
        else:
            verdict = "up" if delta >= FLAT_BAND_PHP else "down" if delta <= -FLAT_BAND_PHP else "flat"
            conf = "low"
            amt = f"₱{abs(delta):.2f}/L"
            when_en, when_fil = fmt_date(effective), fmt_date(effective, "fil")
            partial = (
                ""
                if sig.current.n_days >= sig.current.expected_days and sig.current.expected_days >= 4
                else f" (so far: {sig.current.n_days} of {sig.current.expected_days} trading days)"
            )
            en = {
                "up": f"{name_en} looks set to rise by about {amt} on Tuesday {when_en}{partial}.",
                "down": f"{name_en} looks set to fall by about {amt} on Tuesday {when_en}{partial}.",
                "flat": f"{name_en} looks roughly unchanged on Tuesday {when_en}{partial}.",
            }[verdict]
            fil = {
                "up": f"Posibleng tumaas ng humigit-kumulang {amt} ang {name_fil.lower()} sa Martes, {when_fil}.",
                "down": f"Posibleng bumaba ng humigit-kumulang {amt} ang {name_fil.lower()} sa Martes, {when_fil}.",
                "flat": f"Halos walang pagbabago sa presyo ng {name_fil.lower()} sa Martes, {when_fil}.",
            }[verdict]
        answers.append(
            make_answer(
                ctx,
                question_id=QUESTION_ID,
                version=VERSION,
                scope={"product": product},
                verdict=verdict,
                text=LocalizedText(en=en, fil=fil),
                model=model_info(
                    QUESTION_ID,
                    "spot_cost_pass_through",
                    "2026-10",
                    "unvalidated",
                    "Week-over-week change in NY Harbor spot cost x USD/PHP; no fitted coefficients.",
                ),
                sources=SOURCES,
                confidence=conf,
                coverage=coverage,
                data_through=sig.data_through.isoformat(),
                value={
                    "effective_date": effective.isoformat(),
                    "delta_php_per_l": delta,
                    "this_week_php_per_l": round(sig.current.php_per_l, 2),
                    "last_week_php_per_l": round(sig.previous.php_per_l, 2),
                    "trading_days_this_week": sig.current.n_days,
                    "recent_weekly_costs": [round(w.php_per_l, 2) for w in sig.history],
                },
                drivers=[
                    Driver(
                        feature="week_over_week_cost_php_per_l",
                        value=delta,
                        effect="+" if delta > 0 else "-" if delta < 0 else "0",
                    )
                ],
                evidence=[
                    Evidence(
                        kind="indicator",
                        label=f"{name_en} spot cost, this week (₱/L)",
                        value=round(sig.current.php_per_l, 2),
                    ),
                    Evidence(
                        kind="indicator",
                        label=f"{name_en} spot cost, last week (₱/L)",
                        value=round(sig.previous.php_per_l, 2),
                    ),
                ],
                caveats=[
                    "Uses US NY Harbor spot prices as a stand-in for the Singapore benchmarks DOE uses.",
                    "Not yet validated against official adjustments; treat as a direction, not a price.",
                    *(
                        [
                            f"Ignored an unexplained one-day price step on {', '.join(d.isoformat() for d in sig.jumps)} "
                            "(typically a seasonal grade switch, not a market move)."
                        ]
                        if sig.jumps
                        else []
                    ),
                ],
            )
        )
    return answers
