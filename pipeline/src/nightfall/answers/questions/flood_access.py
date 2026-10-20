"""lastmile.flood_access: is this Pampanga square flooded?

A storm over the square can say "likely". A satellite mask can state a fraction.
That fraction becomes a flood call only after the backtest report sets ship_satellite.
"""

from __future__ import annotations

from nightfall.answers.common import fmt_date, load_report, make_answer, model_info
from nightfall.core.context import Context
from nightfall.core.contracts import Driver, Evidence, LocalizedText, ModelInfo
from nightfall.core.reference import flood_chips
from nightfall.indicators.flood import (
    FLOOD_FRACTION,
    choose_dates,
    flooded_fraction,
    load_mask,
    scenes_for,
    split_for,
    storm_over,
)

QUESTION_ID, VERSION = "lastmile.flood_access", 1
SOURCES_STORM = ["gdacs"]
SOURCES_SAT = ["planetary_stac"]
SOURCES_QUIET = ["gdacs", "planetary_stac"]


def _pct(fraction: float) -> int:
    return int(round(fraction * 100))


def _satellite_model() -> ModelInfo:
    return model_info(
        QUESTION_ID,
        "terramind_flood",
        "1.0-base",
        "unvalidated",
        "TerraMind-base-Flood classes on a 2.56 km square. A call ships only after the IoU bar.",
    )


def _storm_model() -> ModelInfo:
    return ModelInfo(
        name="storm_proximity",
        version="2026-10",
        status="unvalidated",
        notes="The storm wind field covers this square. This is not a flood photo.",
    )


def run(ctx: Context, prior=None) -> list:
    report = load_report(QUESTION_ID) or {}
    ship = bool(report.get("ship_satellite"))
    caveats = [
        "Each square is 2.6 km on a town centre, not the official barangay boundary.",
        "Fishponds and rivers are permanent water and are not counted as flood.",
    ]
    answers = []
    for chip in flood_chips():
        scope = {"chip": chip["chip_id"]}
        base = {
            "chip_id": chip["chip_id"],
            "name": chip["name"],
            "province": chip["province"],
            "lat": chip["lat"],
            "lon": chip["lon"],
            "h3": chip["h3"],
        }
        split = split_for(ctx, chip["lat"], chip["lon"])
        recipe = choose_dates(scenes_for(ctx, chip["chip_id"]), split)
        post = recipe.slot("post_radar")
        mask = None if post.missing else load_mask(chip["chip_id"], post.item_id or "")
        fraction = None if mask is None else flooded_fraction(mask)
        exp = storm_over(ctx, chip["lat"], chip["lon"])
        if fraction is not None and post.sensing_time is not None:
            when = fmt_date(post.sensing_time)
            pct = _pct(fraction)
            coverage = recipe.filled / 4
            evidence = [
                Evidence(
                    kind="satellite",
                    label=f"{post.collection} {post.item_id}",
                    ref=post.item_id,
                    value=round(fraction, 3),
                )
            ]
            value = {
                **base,
                "basis": "satellite",
                "flooded_fraction": round(fraction, 3),
                "sensing_time": post.sensing_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "slots_filled": recipe.filled,
                "storm": None if exp is None else exp.name,
            }
            if ship and coverage >= 0.5 and fraction >= FLOOD_FRACTION:
                verdict, confidence = "flooded", "medium"
                en = f"As of the satellite pass on {when}, {pct}% of the {chip['name']} square was flood water."
                fil = f"Sa satellite pass noong {when}, {pct}% ng parisukat ng {chip['name']} ang binaha."
            elif ship and coverage >= 0.5:
                verdict, confidence = "dry", "medium"
                en = (
                    f"As of the satellite pass on {when}, the {chip['name']} square was not flooded "
                    f"({pct}% flood water)."
                )
                fil = (
                    f"Sa satellite pass noong {when}, hindi binaha ang parisukat ng {chip['name']} "
                    f"({pct}% ang tubig-baha)."
                )
            else:
                verdict, confidence = "unvalidated", "none"
                en = (
                    f"A satellite pass on {when} marked {pct}% of the {chip['name']} square as flood water. "
                    "It has not cleared the accuracy check, so this is not a flood call."
                )
                fil = (
                    f"Sa satellite pass noong {when}, {pct}% ng parisukat ng {chip['name']} ang minarkahang baha. "
                    "Hindi pa ito pumapasa sa pagsusuri, kaya hindi ito isang tawag na baha."
                )
            answers.append(
                make_answer(
                    ctx,
                    question_id=QUESTION_ID,
                    version=VERSION,
                    scope=scope,
                    verdict=verdict,
                    text=LocalizedText(en=en, fil=fil),
                    model=_satellite_model(),
                    sources=SOURCES_SAT,
                    confidence=confidence,
                    coverage=coverage,
                    value=value,
                    evidence=evidence,
                    caveats=caveats,
                    data_through=post.sensing_time.date().isoformat(),
                    drivers=[Driver(feature="flooded_fraction", value=round(fraction, 3), effect="+")],
                )
            )
            continue
        if exp is not None:
            en = (
                f"{exp.name} is over {chip['name']}. Flooding is likely. "
                "This comes from the storm track; the satellite has not confirmed it."
            )
            fil = (
                f"Nasa ibabaw ng {chip['name']} ang {exp.name}. Malamang na may baha. "
                "Galing ito sa daanan ng bagyo; hindi pa ito kinukumpirma ng satellite."
            )
            answers.append(
                make_answer(
                    ctx,
                    question_id=QUESTION_ID,
                    version=VERSION,
                    scope=scope,
                    verdict="likely",
                    text=LocalizedText(en=en, fil=fil),
                    model=_storm_model(),
                    sources=SOURCES_STORM,
                    confidence="low",
                    coverage=1.0,
                    value={**base, "basis": "storm", "flooded_fraction": None, "storm": exp.name},
                    evidence=[
                        Evidence(kind="storm", label=exp.name, ref=exp.storm_id, value=exp.min_distance_km)
                    ],
                    caveats=caveats,
                    drivers=[
                        Driver(feature="storm_distance_km", value=round(exp.min_distance_km, 1), effect="+")
                    ],
                )
            )
            continue
        en = f"No tracked storm covers {chip['name']}, and no satellite pass is on file for this 2.6 km square."
        fil = f"Walang bagyong tumatama sa {chip['name']}, at wala pang satellite pass para sa parisukat na ito."
        answers.append(
            make_answer(
                ctx,
                question_id=QUESTION_ID,
                version=VERSION,
                scope=scope,
                verdict="no_signal",
                text=LocalizedText(en=en, fil=fil),
                model=_storm_model(),
                sources=SOURCES_QUIET,
                confidence="none",
                coverage=1.0,
                value={**base, "basis": "none", "flooded_fraction": None, "storm": None},
                caveats=caveats,
            )
        )
    return answers
