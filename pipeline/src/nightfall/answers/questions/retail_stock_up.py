"""retail.stock_up: plain-language advice for a store in a region, from the other answers.

No new model: transparent rules over answers that already carry their own confidence. When the
inputs are weak, the advice says so instead of guessing.
"""

from __future__ import annotations

from nightfall.answers.common import make_answer, model_info
from nightfall.core import reference
from nightfall.core.context import Context
from nightfall.core.contracts import Answer, Evidence, LocalizedText
from nightfall.indicators.storms import worst_exposure

QUESTION_ID, VERSION = "retail.stock_up", 1
SOURCES = ["da_prices", "eia", "frankfurter", "gdacs", "open_meteo", "portwatch"]

ITEMS = {  # item group -> (English, Filipino)
    "rice": ("Rice", "Bigas"),
    "sugar": ("Sugar", "Asukal"),
    "cooking_oil": ("Cooking oil", "Mantika"),
    "canned_noodles": ("Canned goods and noodles", "De-lata at pancit"),
    "water_light": ("Water, candles, batteries", "Tubig, kandila, baterya"),
    "fuel": ("Fuel for deliveries", "Gasolina para sa deliveries"),
}
PRICE_ITEM_GROUP = {
    "rice_regular": "rice",
    "rice_wellmilled": "rice",
    "sugar_refined": "sugar",
    "sugar_brown": "sugar",
    "cooking_oil_palm_1l": "cooking_oil",
    "cooking_oil_coconut_1l": "cooking_oil",
}
MATERIAL_FUEL_PHP = 1.50  # smaller moves are not worth telling a store owner about
RANK = {"low": 0, "watch": 1, "likely": 2}


def _by(answers: list[Answer], key: str) -> dict[str, Answer]:
    return {a.scope.get(key, ""): a for a in answers}


def _upstream_coverage(prior: dict[str, list[Answer]], keys: tuple[str, ...]) -> float:
    """Mean coverage of the answers this advice leans on; a missing or empty input counts as zero."""
    per_input = [(sum(a.coverage for a in prior[k]) / len(prior[k])) if prior.get(k) else 0.0 for k in keys]
    return sum(per_input) / len(per_input)


def run(ctx: Context, prior: dict[str, list[Answer]] | None = None) -> list:
    prior = prior or {}
    ferries = _by(prior.get("ferry.suspension", []), "ferry_route")
    ports = _by(prior.get("ports.pressure", []), "port")
    fuels = _by(prior.get("fuel.next_week", []), "product")
    prices = _by(prior.get("staples.price_direction", []), "item")
    answers = []
    for region in reference.regions():
        code = region["region_code"]
        reasons: dict[str, list[tuple[str, str, str]]] = {k: [] for k in ITEMS}  # (verdict, en, fil)

        # 1. Storm and sea-crossing hazards (all regions).
        storm = worst_exposure(ctx, [(region["lat"], region["lon"])], 72)
        hazard = 0
        if storm and storm.hours_inside > 0:
            hazard = 2
            msg = (
                f"{storm.name} may bring strong winds to your area within 3 days.",
                f"Maaaring magdala ng malakas na hangin ang {storm.name} sa inyong lugar sa loob ng 3 araw.",
            )
        elif storm and storm.min_distance_km <= 400:
            hazard = 1
            msg = (
                f"{storm.name} is passing within {storm.min_distance_km:.0f} km.",
                f"Dadaan ang {storm.name} sa loob ng {storm.min_distance_km:.0f} km.",
            )
        route_risk = max(
            (RANK.get(ferries[r].verdict, 0) for r in region["ferry_route_ids"] if r in ferries), default=0
        )
        if route_risk == 2:
            hazard = max(hazard, 2)
            fmsg = (
                "Ferry sailings that supply your area are likely to be suspended.",
                "Malamang makansela ang biyahe ng barkong nagsusuplay sa inyong lugar.",
            )
        elif route_risk == 1:
            hazard = max(hazard, 1)
            fmsg = (
                "Rough seas are possible on ferry routes that supply your area.",
                "Posibleng magaspang ang dagat sa mga rutang nagsusuplay sa inyong lugar.",
            )
        if hazard:
            for g in ("rice", "sugar", "cooking_oil", "canned_noodles", "water_light"):
                if hazard == 2 or g in ("canned_noodles", "water_light"):
                    for m in (
                        [msg] if storm and (storm.hours_inside > 0 or storm.min_distance_km <= 400) else []
                    ) + ([fmsg] if route_risk else []):
                        reasons[g].append(("stock_up", *m))

        # 2. Port pressure at the region's gateway.
        port = ports.get(region["primary_port_id"])
        if port and port.verdict == "elevated":
            for g in ("rice", "sugar", "cooking_oil"):
                reasons[g].append(
                    (
                        "stock_up",
                        "Your gateway port is busier than usual; deliveries may run late.",
                        "Mas abala ang pantalan na daanan ng suplay ninyo; maaaring maantala ang deliveries.",
                    )
                )

        # 3. Fuel (national).
        for product in ("diesel", "gasoline"):
            f = fuels.get(product)
            if f and f.verdict == "up" and f.value["delta_php_per_l"] >= MATERIAL_FUEL_PHP:
                reasons["fuel"].append(
                    (
                        "stock_up",
                        f"{product.title()} is expected to rise on Tuesday: fill up before then.",
                        f"Inaasahang tataas ang {product} sa Martes: magpakarga bago nito.",
                    )
                )
            elif f and f.verdict == "down" and f.value["delta_php_per_l"] <= -MATERIAL_FUEL_PHP:
                reasons["fuel"].append(
                    (
                        "wait",
                        f"{product.title()} is expected to fall on Tuesday: wait if you can.",
                        f"Inaasahang bababa ang {product} sa Martes: maghintay kung maaari.",
                    )
                )

        # 4. Local price direction (NCR only: that is all DA publishes weekly).
        if code == "NCR":
            for item_id, group in PRICE_ITEM_GROUP.items():
                a = prices.get(item_id)
                if a and a.verdict == "up":
                    reasons[group].append(
                        (
                            "stock_up",
                            f"{a.value['item']} is likely to get pricier over 4 weeks.",
                            f"Malamang tumaas ang presyo ng {a.value['item'].lower()} sa 4 na linggo.",
                        )
                    )
                elif a and a.verdict == "down":
                    reasons[group].append(
                        (
                            "wait",
                            f"{a.value['item']} is likely to get cheaper over 4 weeks.",
                            f"Malamang bumaba ang presyo ng {a.value['item'].lower()} sa 4 na linggo.",
                        )
                    )

        items_out = []
        for g, rs in reasons.items():
            verdicts = {r[0] for r in rs}
            v = "stock_up" if "stock_up" in verdicts else "wait" if "wait" in verdicts else "normal"
            items_out.append(
                {
                    "item": g,
                    "label_en": ITEMS[g][0],
                    "label_fil": ITEMS[g][1],
                    "verdict": v,
                    "reasons_en": sorted({r[1] for r in rs}),
                    "reasons_fil": sorted({r[2] for r in rs}),
                }
            )
        up = [i for i in items_out if i["verdict"] == "stock_up"]
        wait = [i for i in items_out if i["verdict"] == "wait"]
        overall = "stock_up" if up else "wait" if wait else "normal"
        if up:
            en = (
                f"{region['short']}: consider stocking up on "
                + ", ".join(i["label_en"].lower() for i in up)
                + "."
            )
            fil = (
                f"{region['short']}: magandang mag-imbak ng "
                + ", ".join(i["label_fil"].lower() for i in up)
                + "."
            )
        elif wait:
            en = (
                f"{region['short']}: no rush. Prices look soft for "
                + ", ".join(i["label_en"].lower() for i in wait)
                + "."
            )
            fil = (
                f"{region['short']}: walang pagmamadali. Mukhang bababa ang presyo ng "
                + ", ".join(i["label_fil"].lower() for i in wait)
                + "."
            )
        else:
            en = f"{region['short']}: nothing unusual this week. Restock as normal."
            fil = f"{region['short']}: walang kakaiba ngayong linggo. Mag-restock gaya ng dati."
        coverage = _upstream_coverage(prior, ("ferry.suspension", "ports.pressure", "fuel.next_week"))
        answers.append(
            make_answer(
                ctx,
                question_id=QUESTION_ID,
                version=VERSION,
                scope={"region": code},
                verdict=overall,
                text=LocalizedText(en=en, fil=fil),
                sources=SOURCES,
                confidence="low",
                coverage=coverage,
                model=model_info(
                    QUESTION_ID,
                    "rules_over_answers",
                    "2026-10",
                    "unvalidated",
                    "Rules over other answers; inherits their limits.",
                ),
                value={"region": region["name"], "items": items_out, "hazard_level": hazard},
                evidence=[Evidence(kind="answer", label=k, ref=k) for k in prior if prior[k]],
                caveats=[
                    "Advice, not a guarantee. Local prices are only tracked for Metro Manila.",
                    "Follow PAGASA and Coast Guard advisories in a storm.",
                ],
            )
        )
    return answers
