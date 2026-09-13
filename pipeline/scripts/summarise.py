"""Render a baked manifest as a GitHub Actions run summary.

Stands in for the dashboard this project cannot have: a hosted metrics service is a metered
billing relationship (invariant 0), so the run's own page is where a reader finds out what was
observed, what was missed, and how close the artifacts are to their budgets.

Standard library only, and tolerant of a missing manifest, because it runs after a failure too
— which is when it matters most.

    python3 .github/scripts/summarise.py build/serving/manifest.json >> "$GITHUB_STEP_SUMMARY"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: summarise.py <manifest.json>", file=sys.stderr)
        return 2

    path = Path(argv[1])
    print("## Serving set\n")
    if not path.is_file():
        print("No manifest was produced, so nothing was published this run.")
        return 0

    manifest = json.loads(path.read_text())
    print(f"Generated `{manifest['generated_at']}` by run `{manifest['run_id']}`.\n")
    print(f"Observation kind: `{manifest.get('observation_kind', 'live')}`.\n")
    if manifest.get("available_from") and manifest.get("available_until"):
        print(
            f"Observed window (UTC): `{manifest['available_from']}` → "
            f"`{manifest['available_until']}`.\n"
        )
    census = manifest.get("census")
    if isinstance(census, dict):
        print("| mode | unique | fixes | track segments | isolated points |")
        print("| --- | --- | --- | --- | --- |")
        for mode in ("air", "sea"):
            row = census.get(mode, {})
            print(
                f"| {mode} | {row.get('unique_entities', 0)} | {row.get('position_fixes', 0)} "
                f"| {row.get('track_segments', 0)} | {row.get('isolated_points', 0)} |"
            )
        print()

    print("| layer | zooms | features | vertices | points | bytes | freshness |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for layer in manifest["layers"]:
        budget = layer["budget"]
        used = budget["path_vertices"] or budget["points"]
        limit = budget["path_vertex_limit"] if budget["path_vertices"] else budget["point_limit"]
        print(
            f"| `{layer['id']}` | {layer['min_zoom']}-{layer['max_zoom']} "
            f"| {layer['feature_count']} | {budget['path_vertices']} | {budget['points']} "
            f"| {budget['bytes']} | {layer['freshness']} ({used * 100 // max(limit, 1)}% of "
            "budget) |"
        )

    print("\n### Sources\n")
    for source in manifest["sources"]:
        detail = f" - {source['detail']}" if source.get("detail") else ""
        print(f"- **{source['source']}**: {source['state']}{detail}")

    credited = ", ".join(entry["source"] for entry in manifest["attributions"]) or "none"
    print(f"\nCredited in this build: {credited}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
