import os
from pathlib import Path

import pytest

# Tests read reference data from the repo, never from a developer's environment.
os.environ.pop("NIGHTFALL_REFERENCE", None)
os.environ.pop("NIGHTFALL_LAKE", None)


@pytest.fixture
def lake_dir(tmp_path: Path) -> Path:
    return tmp_path / "lake"


@pytest.fixture(autouse=True)
def isolated_reports(tmp_path_factory, monkeypatch):
    """Backtest reports are generated artifacts. Tests must not depend on whatever happens to be in
    eval/reports/, so every test starts with an empty reports directory (and may point elsewhere)."""
    empty = tmp_path_factory.mktemp("reports")
    for target in ("nightfall.answers.common.reports_dir", "nightfall.publish.bake.reports_dir"):
        monkeypatch.setattr(target, lambda empty=empty: empty)
