"""Runtime settings, read from the environment."""

from __future__ import annotations

import os
from pathlib import Path


def lake_root() -> Path:
    return Path(os.environ.get("NIGHTFALL_LAKE", "lake")).resolve()


def dist_root() -> Path:
    return Path(os.environ.get("NIGHTFALL_DIST", "dist")).resolve()
