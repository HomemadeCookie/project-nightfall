"""The serving manifest: the only document the browser fetches by a fixed name.

Everything else is content-hashed and therefore immutable, so this is where freshness,
provenance, and budget accounting live. Three rules shape it.

Invariant 7 — every rendered number is traceable. Each layer carries what it was built from
and when it was observed, so the UI can attribute a figure without guessing.

Invariant 3 — the read path never depends on upstream liveness. A failed collection leaves the
previous artifacts serving, and the manifest is what marks them stale rather than letting them
pass as current.

Section 4 of `.cursorrules` — licence attributions are generated from the source registry, so
the credits shown to users cannot drift out of date.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from nightfall.clock import isoformat_z, utc_now

#: How old a layer's newest observation may be before it stops counting as current. Both
#: collectors are scheduled well inside this, so exceeding it means a run was missed rather
#: than that the sky went quiet.
FRESH_AFTER = timedelta(hours=1)

#: Past this, the layer is not merely late — the pipeline has stopped. The UI must say so
#: rather than continue presenting the artifact as a picture of now.
STALE_AFTER = timedelta(hours=6)

FreshnessState = Literal["fresh", "late", "stale", "absent"]


def freshness(observed_at: datetime | None, *, now: datetime | None = None) -> FreshnessState:
    if observed_at is None:
        return "absent"
    age = (now or utc_now()) - observed_at
    if age <= FRESH_AFTER:
        return "fresh"
    if age <= STALE_AFTER:
        return "late"
    return "stale"


class Attribution(BaseModel):
    source: str
    licence: str
    url: str
    text: str


class Budget(BaseModel):
    """What the artifact actually costs, against the limit it was checked against.

    Published rather than merely asserted in CI, so a layer that is close to its ceiling is
    visible before it becomes a build failure.
    """

    path_vertices: int
    path_vertex_limit: int
    points: int
    point_limit: int
    bytes: int


class Layer(BaseModel):
    """One renderable artifact."""

    id: str
    kind: Literal["tracks", "points"]
    url: str
    format: Literal["arrow-ipc"] = "arrow-ipc"
    schema_version: int
    #: Zoom range this artifact is simplified for. Tracks are only drawn at zoom 9 and above.
    min_zoom: int
    max_zoom: int
    #: Seconds in `timestamps` are relative to this instant; float32 cannot carry a Unix time.
    epoch: str
    observed_from: str | None = None
    observed_at: str | None = None
    freshness: FreshnessState
    feature_count: int
    budget: Budget


class SourceHealth(BaseModel):
    source: str
    state: str
    observed_at: str | None = None
    detail: str | None = None


class Manifest(BaseModel):
    """`serving/manifest.json`."""

    schema_version: int
    run_id: str
    generated_at: str = Field(default_factory=lambda: isoformat_z(utc_now()))
    #: EPSG:4326, [west, south, east, north].
    bounds: tuple[float, float, float, float]
    initial_view: dict[str, float]
    layers: list[Layer] = Field(default_factory=list)
    attributions: list[Attribution] = Field(default_factory=list)
    sources: list[SourceHealth] = Field(default_factory=list)
    #: Rendered verbatim in the UI. Sampled collection is a real limitation of a zero-cost
    #: design and the interface must not imply otherwise (README § Hard Constraint: Zero Cost).
    sampling_notice: str
