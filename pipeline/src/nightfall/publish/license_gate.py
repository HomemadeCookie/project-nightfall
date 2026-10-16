"""The licence gate: decides which answers may be sold or redistributed commercially."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache

import yaml

from nightfall.core.contracts import Answer
from nightfall.core.license import BLOCKING
from nightfall.core.reference import reference_dir
from nightfall.sources.registry import all_sources


@cache
def reviews() -> dict[str, dict]:
    path = reference_dir() / "license_reviews.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@dataclass
class GateResult:
    commercial_ok: bool
    reasons: list[str] = field(default_factory=list)


def source_status(name: str) -> tuple[bool, str]:
    """(cleared for commercial use, human reason). Flags decide first; a review can clear the rest."""
    cls = all_sources()[name]
    blocking = [x.value for x in cls.license if x in BLOCKING]
    if not blocking:
        return True, "licence allows commercial use"
    review = reviews().get(name, {})
    if review.get("approved") is True:
        return True, review.get("basis", "approved in licence review")
    return False, f"{'/'.join(blocking)}: {review.get('action', 'needs licence review')}"


def check(answer: Answer) -> GateResult:
    reasons = []
    for name in answer.sources:
        ok, why = source_status(name)
        if not ok:
            reasons.append(f"{name} - {why}")
    return GateResult(not reasons, reasons)


def source_table() -> list[dict]:
    rows = []
    for name, cls in sorted(all_sources().items()):
        ok, why = source_status(name)
        rows.append(
            {
                "name": name,
                "license": [x.value for x in cls.license],
                "attribution": cls.attribution,
                "cadence": cls.cadence,
                "commercial_ok": ok,
                "reason": why,
            }
        )
    return rows
