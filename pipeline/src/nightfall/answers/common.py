"""Helpers shared by question modules."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from nightfall.core import reference
from nightfall.core.context import Context
from nightfall.core.contracts import Answer, LocalizedText, ModelInfo, Status
from nightfall.core.license import merge
from nightfall.core.reference import reference_dir
from nightfall.core.time import to_manila


def reports_dir() -> Path:
    return reference_dir().parent / "eval" / "reports"


def load_report(question_id: str) -> dict | None:
    path = reports_dir() / f"{question_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def model_info(
    question_id: str, name: str, version: str, default: Status = "unvalidated", notes: str | None = None
) -> ModelInfo:
    """Model metadata whose status comes from the backtest report, never from the code."""
    report = load_report(question_id)
    status: Status = default
    ref = None
    if report:
        status = report.get("status", default)
        ref = f"eval/reports/{question_id}.json"
    return ModelInfo(name=name, version=version, status=status, backtest_ref=ref, notes=notes)


def lineage(source_names: list[str]) -> tuple[list, list[str]]:
    """Licences and attributions for the sources an answer used."""
    from nightfall.sources.registry import get

    classes = [get(n) for n in source_names]
    return merge(*[c.license for c in classes]), sorted({c.attribution for c in classes if c.attribution})


def make_answer(
    ctx: Context,
    *,
    question_id: str,
    version: int,
    scope: dict[str, str],
    verdict: str,
    text: LocalizedText,
    model: ModelInfo,
    sources: list[str],
    confidence: str,
    coverage: float,
    **kw,
) -> Answer:
    licenses, attributions = lineage(sources)
    return Answer(
        question_id=question_id,
        question_version=version,
        scope=scope,
        as_of=ctx.as_of,
        valid_until=kw.pop("valid_until", ctx.as_of + timedelta(hours=24)),
        verdict=verdict,
        confidence=confidence,
        coverage=round(max(0.0, min(1.0, coverage)), 2),
        text=text,
        model=model,
        license=licenses,
        sources=sorted(sources),
        attributions=attributions,
        **kw,
    )


def fmt_date(d, lang: str = "en") -> str:
    months_fil = ["Ene", "Peb", "Mar", "Abr", "May", "Hun", "Hul", "Ago", "Set", "Okt", "Nob", "Dis"]
    months_en = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    m = (months_fil if lang == "fil" else months_en)[d.month - 1]
    return f"{d.day} {m}" if lang == "fil" else f"{m} {d.day}"


def manila_today(ctx: Context):
    return to_manila(ctx.as_of).date()


def key_ports() -> list[dict]:
    return [p for p in reference.ports() if p["key_port"]]


def staleness_days(ctx: Context, data_through) -> int:
    return (ctx.as_of.date() - data_through).days
