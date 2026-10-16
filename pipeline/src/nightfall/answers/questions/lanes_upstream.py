"""lanes.upstream_disruption: unusual drops or surges in transits through chokepoints PH trade uses."""

from __future__ import annotations

from nightfall.answers.common import make_answer, model_info, staleness_days
from nightfall.core.context import Context
from nightfall.core.contracts import Driver, Evidence, LocalizedText
from nightfall.indicators.chokepoints import pressure
from nightfall.sources.ships.portwatch import CHOKEPOINTS

QUESTION_ID, VERSION = "lanes.upstream_disruption", 1
SOURCES = ["portwatch"]
PCT, Z = 0.25, 1.5


def run(ctx: Context, prior=None) -> list:
    answers = []
    for cid, name in CHOKEPOINTS.items():
        p = pressure(ctx, cid)
        if p is None:
            continue
        stale = staleness_days(ctx, p.data_through)
        if stale > 21:
            continue
        verdict = (
            "disrupted"
            if p.pct_vs_baseline <= -PCT and p.z <= -Z
            else "surge"
            if p.pct_vs_baseline >= PCT and p.z >= Z
            else "normal"
        )
        pct = p.pct_vs_baseline * 100
        en = {
            "disrupted": f"{name}: transits are down {abs(pct):.0f}% vs normal; watch for knock-on delays.",
            "surge": f"{name}: transits are up {pct:.0f}% vs normal.",
            "normal": f"{name}: transits are normal ({pct:+.0f}% vs the last 12 weeks).",
        }[verdict]
        fil = {
            "disrupted": f"{name}: bumaba ng {abs(pct):.0f}% ang daloy ng barko; posibleng may pagkaantala.",
            "surge": f"{name}: tumaas ng {pct:.0f}% ang daloy ng barko.",
            "normal": f"{name}: normal ang daloy ng barko ({pct:+.0f}%).",
        }[verdict]
        answers.append(
            make_answer(
                ctx,
                question_id=QUESTION_ID,
                version=VERSION,
                scope={"chokepoint": cid},
                verdict=verdict,
                text=LocalizedText(en=en, fil=fil),
                sources=SOURCES,
                confidence="low",
                coverage=1.0,
                data_through=p.data_through.isoformat(),
                model=model_info(QUESTION_ID, "transit_change_vs_12w", "2026-10", "experimental"),
                value={
                    "name": name,
                    "transits_7d": p.transits_7d,
                    "baseline": round(p.baseline_mean, 1),
                    "pct_vs_baseline": round(p.pct_vs_baseline, 3),
                    "zscore": round(p.z, 2),
                },
                drivers=[Driver(feature="pct_vs_baseline", value=round(p.pct_vs_baseline, 3))],
                evidence=[Evidence(kind="indicator", label="Transits, last 7 days", value=p.transits_7d)],
                caveats=[
                    "The lag between a disruption here and effects at Philippine ports is not yet measured."
                ],
            )
        )
    return answers
