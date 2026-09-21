"""Pipeline health reporting.

Observability is a JSON artifact the UI reads, not a hosted log aggregator, because
aggregators meter and therefore bill (invariant 0). This is also the mechanism that makes a
stalled pipeline visible within one cycle: the freshness badge in the UI is derived from it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from nightfall.clock import isoformat_z, utc_now

SourceState = Literal["ok", "outage", "not_configured", "fixture", "archive"]


@dataclass(slots=True)
class SourceReport:
    source: str
    state: SourceState
    observed_at: str
    objects_written: int = 0
    detail: str | None = None


@dataclass(slots=True)
class HealthReport:
    """The `pipeline_health.json` artifact."""

    run_id: str
    generated_at: str = field(default_factory=lambda: isoformat_z(utc_now()))
    sources: list[SourceReport] = field(default_factory=list)

    def record(
        self,
        *,
        source: str,
        state: SourceState,
        objects_written: int = 0,
        detail: str | None = None,
        observed_at: datetime | None = None,
    ) -> None:
        self.sources.append(
            SourceReport(
                source=source,
                state=state,
                observed_at=isoformat_z(observed_at or utc_now()),
                objects_written=objects_written,
                detail=detail,
            )
        )

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n")
