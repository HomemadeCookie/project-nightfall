"""Bake answers, datasets and the manifest into a static ``dist/`` folder.

Two modes:
  research    publish everything; every answer is labelled with whether it is cleared for commercial use.
  commercial  publish only answers whose every input source is cleared; list the rest in blocked.json.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from nightfall import __version__
from nightfall.answers.common import reports_dir
from nightfall.answers.engine import RunResult, load_specs
from nightfall.core.context import Context
from nightfall.core.lake import Lake
from nightfall.publish import datasets, license_gate
from nightfall.publish.manifest import source_freshness, utc_iso


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")


def bake(lake: Lake, ctx: Context, result: RunResult, out: Path, mode: str = "research") -> dict:
    if mode not in ("research", "commercial"):
        raise ValueError(mode)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    specs = load_specs()

    published, blocked = [], []
    for answer in result.flat():
        gate = license_gate.check(answer)
        row = answer.model_dump(mode="json")
        row["commercial_ok"] = gate.commercial_ok
        if mode == "commercial" and not gate.commercial_ok:
            blocked.append(
                {"question_id": answer.question_id, "scope": answer.scope, "reasons": gate.reasons}
            )
            continue
        published.append(row)

    by_q: dict[str, list[dict]] = {}
    for row in published:
        by_q.setdefault(row["question_id"], []).append(row)
    for qid, rows in by_q.items():
        _write(out / "answers" / f"{qid}.json", rows)
    _write(out / "answers" / "index.json", published)

    for name, body in datasets.build_all(ctx).items():
        _write(out / "data" / f"{name}.json", body)

    reports = {}
    if reports_dir().exists():
        for path in sorted(reports_dir().glob("*.json")):
            reports[path.stem] = json.loads(path.read_text(encoding="utf-8"))
            _write(out / "eval" / path.name, reports[path.stem])

    questions = []
    for qid, spec in sorted(specs.items(), key=lambda kv: (kv[1].tier, kv[0])):
        rows = by_q.get(qid, [])
        report = reports.get(qid, {})
        questions.append(
            {
                "id": qid,
                "tier": spec.tier,
                "ask": spec.ask.model_dump(),
                "buyers": spec.buyers,
                "decision": spec.decision,
                "implemented": spec.implemented,
                "model_status": report.get("status", "unvalidated" if spec.implemented else "planned"),
                "report_summary": report.get("summary"),
                "n_answers": len(rows),
                "error": result.errors.get(qid),
                "ship_when": spec.ship_when,
            }
        )

    fresh = {f["source"]: f for f in source_freshness(lake, ctx.as_of)}
    manifest = {
        "version": __version__,
        "mode": mode,
        "generated_at": utc_iso(ctx.as_of),
        "banner": (
            "Research preview. Some inputs are not yet cleared for commercial use; see the Data page."
            if mode == "research"
            else None
        ),
        "sources": [{**src, "fresh": fresh.get(src["name"])} for src in license_gate.source_table()],
        "questions": questions,
        "counts": {"answers": len(published), "blocked": len(blocked), "errors": len(result.errors)},
    }
    _write(out / "manifest.json", manifest)
    if mode == "commercial":
        _write(out / "blocked.json", blocked)
    return manifest


def parse_as_of(value: str | None, default: datetime) -> datetime:
    from nightfall.core.time import parse_iso

    return parse_iso(value) if value else default
