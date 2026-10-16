"""Run every implemented question for one ``as_of`` and collect answers."""

from __future__ import annotations

import importlib
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from nightfall.core.context import Context
from nightfall.core.contracts import Answer, QuestionSpec, load_spec
from nightfall.core.reference import reference_dir

# Order matters: retail.stock_up reads the others.
MODULES = [
    "fuel_next_week",
    "ports_pressure",
    "ferry_suspension",
    "staples_arrivals",
    "staples_price_direction",
    "lanes_upstream",
    "typhoon_exposure",
    "aircargo",
    "retail_stock_up",
]


@dataclass
class RunResult:
    answers: dict[str, list[Answer]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    def flat(self) -> list[Answer]:
        return [a for lst in self.answers.values() for a in lst]


def questions_dir() -> Path:
    return reference_dir().parent / "questions"


def load_specs() -> dict[str, QuestionSpec]:
    specs = {}
    for path in sorted(questions_dir().rglob("*.yaml")):
        spec = load_spec(path)
        if spec.id in specs:
            raise ValueError(f"duplicate question id {spec.id}")
        specs[spec.id] = spec
    return specs


def run_all(ctx: Context, only: set[str] | None = None) -> RunResult:
    result = RunResult()
    specs = load_specs()
    for name in MODULES:
        mod = importlib.import_module(f"nightfall.answers.questions.{name}")
        qid = mod.QUESTION_ID
        if qid not in specs:
            result.errors[qid] = "no questions/*.yaml spec for this module"
            continue
        if only and qid not in only:
            continue
        try:
            answers = mod.run(ctx, result.answers)
        except Exception:  # one broken question must not hide the others
            result.errors[qid] = traceback.format_exc(limit=4)
            continue
        floor = specs[qid].min_coverage
        for a in answers:
            if a.coverage < floor and a.verdict not in ("insufficient_data", "collecting_data", "no_call"):
                a.verdict, a.confidence = "insufficient_data", "none"
        result.answers[qid] = answers
    return result
