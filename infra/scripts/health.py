#!/usr/bin/env python3
"""Fail loudly when published data is stale or a question errored, and open (or update) one GitHub issue.

Reads dist/manifest.json. Stdlib only so it runs anywhere. Exit code 1 means something needs attention.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

TITLE = "Pipeline health: stale data or failing question"


def problems(manifest: dict) -> list[str]:
    out = []
    for s in manifest.get("sources", []):
        fresh = s.get("fresh") or {}
        if fresh.get("status") == "stale":
            out.append(f"source `{s['name']}` is stale: data through {fresh.get('data_through')} "
                       f"({fresh.get('age_days')} days old, limit {fresh.get('stale_after_days')})")
    for q in manifest.get("questions", []):
        if q.get("error"):
            first = str(q["error"]).strip().splitlines()[-1]
            out.append(f"question `{q['id']}` failed: {first}")
    return out


def main(path: str = "dist/manifest.json") -> int:
    manifest = json.loads(Path(path).read_text())
    found = problems(manifest)
    if not found:
        print("healthy")
        return 0
    body = "Detected by the scheduled pipeline:\n\n" + "\n".join(f"- {p}" for p in found)
    print(body)
    if os.environ.get("GH_TOKEN"):
        existing = subprocess.run(["gh", "issue", "list", "--state", "open", "--search", TITLE, "--json", "number",
                                   "--jq", ".[0].number"], capture_output=True, text=True).stdout.strip()
        if existing:
            subprocess.run(["gh", "issue", "comment", existing, "--body", body], check=False)
        else:
            subprocess.run(["gh", "issue", "create", "--title", TITLE, "--body", body], check=False)
    return 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
