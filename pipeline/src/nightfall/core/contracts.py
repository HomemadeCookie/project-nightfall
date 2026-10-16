"""Typed contracts shared by the pipeline, the published JSON, and the web/bot clients.

JSON Schemas in ``contracts/`` are generated from these models (``nightfall contracts``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from nightfall.core.license import License

Confidence = Literal["high", "medium", "low", "none"]
# Honest status of the model behind an answer.
Status = Literal["validated", "experimental", "unvalidated", "planned"]


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str  # indicator | article | storm | forecast | price
    label: str
    ref: str | None = None
    url: str | None = None
    value: Any = None


class Driver(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feature: str
    value: Any
    effect: Literal["+", "-", "0"] = "0"


class LocalizedText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    en: str
    fil: str | None = None


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    version: str
    status: Status
    backtest_ref: str | None = None
    notes: str | None = None


class Answer(BaseModel):
    """One question evaluated for one scope at one point in time."""

    model_config = ConfigDict(extra="forbid")
    question_id: str
    question_version: int
    scope: dict[str, str]
    as_of: datetime
    valid_until: datetime | None = None
    data_through: str | None = None  # newest date the inputs actually cover
    verdict: str
    value: dict[str, Any] = Field(default_factory=dict)
    confidence: Confidence
    coverage: float = Field(ge=0.0, le=1.0)
    drivers: list[Driver] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    text: LocalizedText
    model: ModelInfo
    license: list[License]
    sources: list[str] = Field(default_factory=list)
    attributions: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)

    @property
    def key(self) -> str:
        scope = ",".join(f"{k}={v}" for k, v in sorted(self.scope.items()))
        return f"{self.question_id}[{scope}]"


class Horizon(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hours: list[int] = Field(default_factory=list)


class Metric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    primary: str
    secondary: list[str] = Field(default_factory=list)


class QuestionSpec(BaseModel):
    """``questions/**/*.yaml``. The spec is the product; code exists to satisfy it."""

    model_config = ConfigDict(extra="forbid")
    id: str
    version: int
    tier: Literal[1, 2, 3]
    status: Status
    buyers: list[str]
    decision: str
    ask: LocalizedText
    scope: dict[str, str]
    cadence: str
    inputs: list[str]
    baseline: str
    metric: Metric
    ship_when: str
    min_coverage: float = Field(default=0.5, ge=0.0, le=1.0)
    outputs: list[str] = Field(default_factory=lambda: ["web"])
    notes: str | None = None
    implemented: bool = True

    @model_validator(mode="after")
    def _id_shape(self) -> QuestionSpec:
        if self.id.count(".") != 1:
            raise ValueError("question id must look like 'domain.name'")
        return self


def load_spec(path) -> QuestionSpec:
    with open(path, encoding="utf-8") as fh:
        return QuestionSpec.model_validate(yaml.safe_load(fh))
