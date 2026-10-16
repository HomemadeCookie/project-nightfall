import os
from pathlib import Path

import pytest

# Tests read reference data from the repo, never from a developer's environment.
os.environ.pop("NIGHTFALL_REFERENCE", None)
os.environ.pop("NIGHTFALL_LAKE", None)


@pytest.fixture
def lake_dir(tmp_path: Path) -> Path:
    return tmp_path / "lake"
