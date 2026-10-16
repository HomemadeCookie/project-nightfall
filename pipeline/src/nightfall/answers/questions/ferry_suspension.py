"""ferry.suspension: risk that sailings on a RoRo corridor are suspended in the next few days.

Output is an ordinal risk (low / watch / likely), not a probability. The ladder below is a
transparent heuristic anchored on PAGASA's wind-signal bands; it has not been validated against
real suspension notices yet, and the answer says so.
"""

from __future__ import annotations

from nightfall.answers.common import make_answer, model_info
from nightfall.core import reference
from nightfall.core.context import Context
from nightfall.core.contracts import Driver, Evidence, LocalizedText
from nightfall.indicators.route_weather import route_weather
from nightfall.indicators.storms import current_tracks, exposure

QUESTION_ID, VERSION = "ferry.suspension", 1
SOURCES = ["gdacs"]  # plus whichever weather provider fed the answer
HORIZONS = (24, 72, 120)
LEVELS = ["low", "watch", "likely"]


def risk_score(wind: float, gust: float, wave: float, storm_inside_h: int, storm_min_km: float) -> int:
    score = 0
    score += 2 if wind >= 62 else 1 if wind >= 39 else 0  # sustained wind ~ PAGASA signal 2 / signal 1
    score += 1 if gust >= 90 else 0
    score += 2 if wave >= 4.0 else 1 if wave >= 2.5 else 0
    score += 2 if storm_inside_h > 0 else 1 if storm_min_km <= 300 else 0
    return score


def level(score: int) -> str:
    return "likely" if score >= 4 else "watch" if score >= 2 else "low"


def run(ctx: Context, prior=None) -> list:
    tracks = current_tracks(ctx)
    answers = []
    for route in reference.ferry_routes():
        targets = route["line"]
        per_h: dict[str, dict] = {}
        have_weather = False
        providers: set[str] = set()
        for h in HORIZONS:
            rw = route_weather(ctx, route["route_id"], h)
            have_weather = have_weather or rw is not None
            if rw is not None:
                providers.add(rw.provider)
            exps = [exposure(t, targets, ctx.as_of, h) for t in tracks]
            exps = [e for e in exps if e.min_distance_km != float("inf")]
            worst = min(exps, key=lambda e: (-e.hours_inside, e.min_distance_km)) if exps else None
            score = risk_score(
                rw.peak_wind_kmh if rw else 0,
                rw.peak_gust_kmh if rw else 0,
                rw.peak_wave_m if rw else 0,
                worst.hours_inside if worst else 0,
                worst.min_distance_km if worst else 9999.0,
            )
            per_h[f"h{h}"] = {
                "risk": level(score),
                "score": score,
                "peak_wind_kmh": None if rw is None else round(rw.peak_wind_kmh),
                "peak_gust_kmh": None if rw is None else round(rw.peak_gust_kmh),
                "peak_wave_m": None if rw is None else round(rw.peak_wave_m, 1),
                "storm": None if worst is None else worst.name,
                "storm_min_km": None if worst is None else round(worst.min_distance_km),
                "storm_hours_inside": None if worst is None else worst.hours_inside,
            }
        if not have_weather and not tracks:
            coverage, conf, verdict = 0.0, "none", "insufficient_data"
        else:
            coverage = 1.0 if have_weather else 0.5
            verdict = per_h["h72"]["risk"]
            conf = "low"
        near = per_h["h72"]
        name = route["name"]
        en = {
            "low": f"No suspension signals for {name} in the next 3 days.",
            "watch": f"{name}: rough conditions possible in the next 3 days; watch advisories.",
            "likely": f"{name}: suspension of sailings is likely within 3 days.",
            "insufficient_data": f"No forecast data available for {name}.",
        }[verdict]
        fil = {
            "low": f"Walang senyales ng pagkansela ng biyahe sa {name} sa susunod na 3 araw.",
            "watch": f"{name}: posibleng magaspang ang dagat sa susunod na 3 araw; subaybayan ang abiso.",
            "likely": f"{name}: malamang makansela ang biyahe sa loob ng 3 araw.",
            "insufficient_data": f"Walang datos ng panahon para sa {name}.",
        }[verdict]
        drivers = [
            Driver(feature=k, value=v)
            for k, v in (
                ("peak_wave_m", near["peak_wave_m"]),
                ("peak_wind_kmh", near["peak_wind_kmh"]),
                ("storm_min_km", near["storm_min_km"]),
            )
            if v is not None
        ]
        answers.append(
            make_answer(
                ctx,
                question_id=QUESTION_ID,
                version=VERSION,
                scope={"ferry_route": route["route_id"]},
                verdict=verdict,
                text=LocalizedText(en=en, fil=fil),
                sources=SOURCES + sorted(providers),
                confidence=conf,
                coverage=coverage,
                model=model_info(
                    QUESTION_ID,
                    "risk_ladder",
                    "2026-10",
                    "unvalidated",
                    "Ordinal ladder over forecast wind, gust, wave and storm proximity at corridor waypoints.",
                ),
                value={
                    "route": name,
                    "horizons": per_h,
                    "weather_provider": sorted(providers)[0] if providers else None,
                    "serves": route["serves_regions"].split(";"),
                },
                drivers=drivers,
                evidence=[
                    Evidence(kind="forecast", label="Peak wave next 72 h (m)", value=near["peak_wave_m"]),
                    Evidence(
                        kind="forecast",
                        label="Peak sustained wind next 72 h (km/h)",
                        value=near["peak_wind_kmh"],
                    ),
                ]
                + (
                    [
                        Evidence(
                            kind="storm", label=f"Closest storm: {near['storm']}", value=near["storm_min_km"]
                        )
                    ]
                    if near["storm"]
                    else []
                ),
                caveats=[
                    "Heuristic risk ladder, not validated against real suspension notices yet.",
                    "Corridors are straight-line approximations between terminals.",
                    "Always follow Philippine Coast Guard and operator advisories.",
                ],
            )
        )
    return answers
