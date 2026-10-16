"""ports.pressure: is port activity unusually high or low, and what next week likely brings."""

from __future__ import annotations

from nightfall.answers.common import key_ports, load_report, make_answer, model_info, staleness_days
from nightfall.core.context import Context
from nightfall.core.contracts import Driver, Evidence, LocalizedText
from nightfall.indicators.ports import calls_series, forecast_next_week, pressure
from nightfall.indicators.waits import port_waits

QUESTION_ID, VERSION = "ports.pressure", 1
SOURCES = ["portwatch"]
Z_HIGH, Z_LOW = 1.0, -1.0
MIN_WEEKLY_CALLS = 10  # below this the weekly count is too small to read as a signal


def run(ctx: Context, prior=None) -> list:
    report = load_report(QUESTION_ID) or {}
    answers = []
    for port in key_ports():
        p = pressure(ctx, port["portwatch_id"])
        if p is None:
            continue
        stale = staleness_days(ctx, p.data_through)
        low_traffic = p.baseline_mean < MIN_WEEKLY_CALLS
        coverage = 0.0 if stale > 21 else (0.4 if low_traffic else 1.0)
        verdict = "elevated" if p.z >= Z_HIGH else "slack" if p.z <= Z_LOW else "normal"
        conf = "none" if coverage == 0 else "low" if low_traffic or stale > 10 else "medium"
        if coverage == 0:
            verdict = "insufficient_data"

        forecast = None
        best = (report.get("ports") or {}).get(port["port_id"], {})
        if best.get("ship_forecast"):
            vals = [v for _, v in calls_series(ctx, port["portwatch_id"])]
            forecast = round(forecast_next_week(vals, best["model"]), 1)

        name = port["name"]
        wait = port_waits(ctx, port["port_id"], (port["lat"], port["lon"]))
        ais = None
        if wait and wait.median_wait_h is not None:
            ais = {
                "median_wait_h": wait.median_wait_h,
                "p90_wait_h": wait.p90_wait_h,
                "waits_measured": wait.waits_measured,
                "window_days": wait.window_days,
                "vessels_seen": wait.vessels_seen,
            }
        word_en = {
            "elevated": "busier than usual",
            "slack": "quieter than usual",
            "normal": "about normal",
            "insufficient_data": "not readable",
        }[verdict]
        word_fil = {
            "elevated": "mas abala kaysa karaniwan",
            "slack": "mas tahimik kaysa karaniwan",
            "normal": "halos normal",
            "insufficient_data": "hindi mabasa",
        }[verdict]
        en = (
            f"{name} port activity is {word_en}: {p.calls_7d:.0f} vessel calls in the 7 days to "
            f"{p.data_through:%b %d} vs ~{p.baseline_mean:.0f} typical."
        )
        fil = (
            f"Ang aktibidad sa pantalan ng {name} ay {word_fil}: {p.calls_7d:.0f} barko sa nakaraang 7 araw "
            f"hanggang {p.data_through:%b %d}, kumpara sa karaniwang ~{p.baseline_mean:.0f}."
        )
        caveats = [
            "Vessel-call volume does not by itself measure berth wait time."
            if ais
            else "Measures vessel-call volume, not berth wait time; wait time needs live AIS (see roadmap).",
            f"Source data lags about a week (latest day: {p.data_through.isoformat()}).",
        ]
        if low_traffic:
            caveats.append("Low traffic port: weekly counts are small and noisy.")
        answers.append(
            make_answer(
                ctx,
                question_id=QUESTION_ID,
                version=VERSION,
                scope={"port": port["port_id"]},
                verdict=verdict,
                text=LocalizedText(en=en, fil=fil),
                sources=SOURCES + (["aisstream"] if ais else []),
                confidence=conf,
                coverage=coverage,
                data_through=p.data_through.isoformat(),
                model=model_info(
                    QUESTION_ID,
                    "weekly_zscore_vs_12w",
                    "2026-10",
                    "experimental",
                    "z-score of 7-day calls against the previous 12 weeks.",
                ),
                value={
                    "calls_7d": p.calls_7d,
                    "baseline_mean": round(p.baseline_mean, 1),
                    "zscore": round(p.z, 2),
                    "yoy_ratio": None if p.yoy_ratio is None else round(p.yoy_ratio, 2),
                    "forecast_calls_next_7d": forecast,
                    "port_name": name,
                    "ais": ais,
                },
                drivers=[
                    Driver(
                        feature="zscore_vs_12w",
                        value=round(p.z, 2),
                        effect="+" if p.z > 0 else "-" if p.z < 0 else "0",
                    )
                ],
                evidence=[Evidence(kind="indicator", label="Vessel calls, last 7 days", value=p.calls_7d)]
                + (
                    [
                        Evidence(
                            kind="indicator",
                            label="Median anchorage wait (h, AIS)",
                            value=ais["median_wait_h"],
                        )
                    ]
                    if ais
                    else []
                ),
                caveats=caveats,
            )
        )
    return answers
