"""Backtest reports: the only source of an answer's 'validated/experimental' status."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from nightfall.answers.common import reports_dir


def write_report(question_id: str, body: dict, directory: Path | None = None) -> Path:
    directory = directory or reports_dir()
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "question_id": question_id,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **body,
    }
    path = directory / f"{question_id}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return path
