"""aircargo.activity: freighter traffic near Manila, Clark and Cebu from adsb.lol snapshots."""

from __future__ import annotations

import csv

from nightfall.answers.common import make_answer, model_info
from nightfall.core.context import Context
from nightfall.core.contracts import LocalizedText
from nightfall.core.reference import reference_dir

QUESTION_ID, VERSION = "aircargo.activity", 1
SOURCES = ["adsb_lol"]
MIN_DAYS = 14


def cargo_prefixes() -> set[str]:
    with open(reference_dir() / "cargo_operators.csv", newline="", encoding="utf-8") as fh:
        return {r["icao_prefix"] for r in csv.DictReader(fh)}


def run(ctx: Context, prior=None) -> list:
    rows = ctx.rows("aircraft_obs")
    prefixes = cargo_prefixes()
    days = {r["observed_at"].date() for r in rows}
    cargo = [r for r in rows if r["callsign"] and r["callsign"][:3] in prefixes]
    answers = []
    for airport in ("MNL", "CRK", "CEB"):
        mine = {r["registration"] or r["hex"] for r in cargo if r["airport"] == airport}
        enough = len(days) >= MIN_DAYS
        en = (
            f"{airport}: {len(mine)} freighter aircraft seen nearby so far; need {MIN_DAYS} days of "
            "history before comparing with normal."
            if not enough
            else f"{airport}: {len(mine)} distinct freighters seen in the collected window."
        )
        fil = (
            f"{airport}: {len(mine)} cargo plane na namataan; kailangan ng {MIN_DAYS} araw na datos bago maihambing."
            if not enough
            else f"{airport}: {len(mine)} cargo plane sa nakolektang panahon."
        )
        answers.append(
            make_answer(
                ctx,
                question_id=QUESTION_ID,
                version=VERSION,
                scope={"airport": airport},
                verdict="normal" if enough else "collecting_data",
                text=LocalizedText(en=en, fil=fil),
                sources=SOURCES,
                confidence="none",
                coverage=min(len(days) / MIN_DAYS, 1.0),
                model=model_info(QUESTION_ID, "distinct_freighters", "2026-10", "unvalidated"),
                value={"distinct_freighters": len(mine), "days_collected": len(days)},
                caveats=[
                    "Hourly snapshots miss most traffic; this is a trend signal, not a flight count.",
                    "adsb.lol data is ODbL: derived databases must be shared under the same licence.",
                ],
            )
        )
    return answers
