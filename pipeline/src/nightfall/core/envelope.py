"""The raw envelope: every fetched record, with provenance and licence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from nightfall.core.license import License
from nightfall.core.time import ensure_utc, iso


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Envelope(BaseModel):
    source: str
    source_version: str = "1"
    dataset: str  # which table/endpoint within the source
    license: list[License]
    fetched_at: datetime
    event_time: datetime | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    payload: Any
    payload_sha256: str = ""

    def model_post_init(self, __context: Any) -> None:
        self.fetched_at = ensure_utc(self.fetched_at)
        if self.event_time is not None:
            self.event_time = ensure_utc(self.event_time)
        if not self.payload_sha256:
            self.payload_sha256 = hashlib.sha256(canonical_json(self.payload).encode("utf-8")).hexdigest()

    def to_row(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_version": self.source_version,
            "dataset": self.dataset,
            "license": canonical_json([x.value for x in self.license]),
            "fetched_at": iso(self.fetched_at),
            "event_time": iso(self.event_time) if self.event_time else None,
            "request": canonical_json(self.request),
            "payload_sha256": self.payload_sha256,
            "payload": canonical_json(self.payload),
        }
