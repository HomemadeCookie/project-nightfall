"""typhoon.asset_exposure: which sites will a tracked storm come close to, and when."""

from __future__ import annotations

import csv
from pathlib import Path

from nightfall.answers.common import make_answer, model_info
from nightfall.core.context import Context
from nightfall.core.contracts import Driver, Evidence, LocalizedText
from nightfall.core.reference import reference_dir
from nightfall.indicators.storms import current_tracks, exposure

QUESTION_ID, VERSION = "typhoon.asset_exposure", 1
SOURCES = ["gdacs"]
HORIZON_H = 120
NEAR_KM = 500.0


def load_sites(path: Path | None = None) -> list[dict]:
    path = path or reference_dir() / "example_sites.csv"
    with open(path, newline="", encoding="utf-8") as fh:
        return [{**r, "lat": float(r["lat"]), "lon": float(r["lon"])} for r in csv.DictReader(fh)]


def run(ctx: Context, prior=None, sites: list[dict] | None = None) -> list:
    sites = sites if sites is not None else load_sites()
    tracks = current_tracks(ctx)
    answers = []
    for site in sites:
        exps = [exposure(t, [(site["lat"], site["lon"])], ctx.as_of, HORIZON_H) for t in tracks]
        exps = [e for e in exps if e.min_distance_km != float("inf")]
        worst = min(exps, key=lambda e: (-e.hours_inside, e.min_distance_km)) if exps else None
        if worst is None:
            verdict, en = "clear", f"No tracked storm is forecast near {site['name']} in the next 5 days."
            fil = f"Walang bagyong inaasahang lalapit sa {site['name']} sa susunod na 5 araw."
        elif worst.hours_inside > 0:
            verdict = "direct_exposure"
            en = (
                f"{worst.name} may bring damaging winds to {site['name']} (closest approach "
                f"{worst.min_distance_km:.0f} km, ~{worst.hours_inside} h inside its wind field)."
            )
            fil = (
                f"Maaaring magdala ng malakas na hangin ang {worst.name} sa {site['name']} "
                f"(pinakamalapit: {worst.min_distance_km:.0f} km)."
            )
        elif worst.min_distance_km <= NEAR_KM:
            verdict = "near"
            en = f"{worst.name} passes within {worst.min_distance_km:.0f} km of {site['name']}; monitor."
            fil = f"Dadaan ang {worst.name} sa loob ng {worst.min_distance_km:.0f} km ng {site['name']}; subaybayan."
        else:
            verdict = "clear"
            en = f"{worst.name} stays {worst.min_distance_km:.0f} km or more from {site['name']}."
            fil = f"Mananatiling {worst.min_distance_km:.0f} km o higit ang layo ng {worst.name} sa {site['name']}."
        answers.append(
            make_answer(
                ctx,
                question_id=QUESTION_ID,
                version=VERSION,
                scope={"site": site["site_id"]},
                verdict=verdict,
                text=LocalizedText(en=en, fil=fil),
                sources=SOURCES,
                confidence="low" if worst else "medium",
                coverage=1.0,
                model=model_info(
                    QUESTION_ID,
                    "track_proximity",
                    "2026-10",
                    "experimental",
                    "Distance from interpolated forecast centre to the site; wind-field radius from GDACS.",
                ),
                value={
                    "site": site["name"],
                    "horizon_h": HORIZON_H,
                    "storm": None if worst is None else worst.name,
                    "min_distance_km": None if worst is None else round(worst.min_distance_km),
                    "hours_inside": None if worst is None else worst.hours_inside,
                    "first_inside": None
                    if worst is None or worst.first_inside is None
                    else worst.first_inside.isoformat(),
                },
                drivers=[]
                if worst is None
                else [Driver(feature="min_distance_km", value=round(worst.min_distance_km))],
                evidence=[]
                if worst is None
                else [Evidence(kind="storm", label=worst.name, value=worst.alert)],
                caveats=[
                    "Track forecasts carry error that grows with lead time (hundreds of km at day 5).",
                    "Reflects the GDACS/JTWC track, not local rainfall or flooding.",
                ],
            )
        )
    return answers
