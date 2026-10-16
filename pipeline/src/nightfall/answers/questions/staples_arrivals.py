"""staples.arrivals: are bulk grain/sugar and fuel cargoes arriving at a normal pace?

v1 is a nowcast of the last 28 days of estimated import tonnage by vessel class. A forward-looking
30-day pipeline needs live AIS (vessel destinations and ETAs); see the roadmap.
"""

from __future__ import annotations

from nightfall.answers.common import key_ports, make_answer, model_info, staleness_days
from nightfall.core.context import Context
from nightfall.core.contracts import Driver, Evidence, LocalizedText
from nightfall.indicators.arrivals import arrivals

QUESTION_ID, VERSION = "staples.arrivals", 1
SOURCES = ["portwatch"]
BAND = 0.15
GROUPS = {
    "dry_bulk": ("Grain, sugar and feed (dry bulk)", "Butil, asukal at pakain (dry bulk)"),
    "tanker": ("Fuel and oil (tankers)", "Gasolina at langis (tanker)"),
}


def run(ctx: Context, prior=None) -> list:
    all_ports = [r["portid"] for r in ctx.rows("port_ref")] or None
    scopes: list[tuple[str, str, list[str] | None]] = [("PH", "Philippines", all_ports)]
    scopes += [(p["port_id"], p["name"], [p["portwatch_id"]]) for p in key_ports()]
    answers = []
    for vclass, (label_en, label_fil) in GROUPS.items():
        for scope_id, scope_name, ids in scopes:
            a = arrivals(ctx, vclass, ids)
            if a is None or a.norm_28d < 5_000:  # skip ports with negligible tonnage
                continue
            stale = staleness_days(ctx, a.data_through)
            coverage = 0.0 if stale > 28 else 1.0
            verdict = (
                "insufficient_data"
                if coverage == 0
                else "above_normal"
                if a.pct_vs_norm >= BAND
                else "below_normal"
                if a.pct_vs_norm <= -BAND
                else "normal"
            )
            pct = a.pct_vs_norm * 100
            en = (
                f"{label_en} arrivals at {scope_name} are {verdict.replace('_', ' ')}: "
                f"{a.tonnes_28d / 1000:,.0f}k t over 28 days ({pct:+.0f}% vs the previous months)."
            )
            fil = (
                f"Ang pagdating ng {label_fil} sa {scope_name} ay {verdict.replace('_', ' ')}: "
                f"{a.tonnes_28d / 1000:,.0f}k t sa 28 araw ({pct:+.0f}% kumpara sa mga nakaraang buwan)."
            )
            answers.append(
                make_answer(
                    ctx,
                    question_id=QUESTION_ID,
                    version=VERSION,
                    scope={"vessel_class": vclass, "port": scope_id},
                    verdict=verdict,
                    text=LocalizedText(en=en, fil=fil),
                    sources=SOURCES,
                    confidence="none" if coverage == 0 else "low" if scope_id != "PH" else "medium",
                    coverage=coverage,
                    data_through=a.data_through.isoformat(),
                    model=model_info(QUESTION_ID, "tonnage_vs_trailing_norm", "2026-10", "experimental"),
                    value={
                        "tonnes_28d": round(a.tonnes_28d),
                        "norm_28d": round(a.norm_28d),
                        "pct_vs_norm": round(a.pct_vs_norm, 3),
                        "pct_vs_last_year": None
                        if a.pct_vs_last_year is None
                        else round(a.pct_vs_last_year, 3),
                        "scope_name": scope_name,
                        "group": label_en,
                    },
                    drivers=[
                        Driver(
                            feature="pct_vs_norm",
                            value=round(a.pct_vs_norm, 3),
                            effect="+" if a.pct_vs_norm > 0 else "-" if a.pct_vs_norm < 0 else "0",
                        )
                    ],
                    evidence=[
                        Evidence(
                            kind="indicator",
                            label="Estimated imports, last 28 days (t)",
                            value=round(a.tonnes_28d),
                        )
                    ],
                    caveats=[
                        "Vessel class is a proxy for cargo: a bulk carrier may carry grain, sugar, coal or cement.",
                        "Backward-looking nowcast; expected-arrival forecasts need AIS voyage data.",
                    ],
                )
            )
    return answers
