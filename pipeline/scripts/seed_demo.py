"""Build a serving set from the recorded fixture, with no network access.

Two users. A developer who wants the map on screen without waiting for a collection window or
holding an API key, and CI, which needs real baked bytes to run the cross-language contract
suite against — an empty serving set would let that suite pass while proving nothing.

The data is the recorded adsb.lol response flown forward synthetically plus AIS frames built
from the provider's published schema, so it is representative of shape and emphatically not of
reality. It writes to `build/` like a real run, and the manifest it produces carries the run id
`demo` so nothing downstream can mistake it for an observation.

    uv run --project pipeline python pipeline/scripts/seed_demo.py
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
import time
from datetime import timedelta
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
# The fixture builders live with the tests, which is the right place for them: they are not
# part of what ships. Reaching them needs the repository on the path, not the installed wheel.
sys.path.insert(0, str(PIPELINE_ROOT))

from tests.conftest import seed_ais_window, seed_window

from nightfall.bake import bake
from nightfall.clock import utc_now
from nightfall.config import Settings
from nightfall.transform import transform

log = logging.getLogger("nightfall.demo")

LOG_FORMAT = "%(asctime)sZ %(levelname)s %(name)s %(message)s"

#: The window is placed in the recent past rather than at the fixture's own instant, so the
#: baked manifest reads as fresh and the freshness badge can be seen working.
SWEEPS = 8
SWEEP_INTERVAL_S = 20.0

#: The vessels are put in the Manila Bay approaches, drifting up the bay towards the harbour,
#: and given the same window as the aircraft. Their defaults sit offshore of Mindoro and at the
#: fixture's own instant, which is fine for a unit test and wrong for a demo: the two layers
#: would share neither the opening viewport nor a moment in time, so a reader scrubbing through
#: the window would never see aircraft and vessels at once and would reasonably conclude the
#: vessel layer was broken.
AIS_WINDOW_S = 180.0
AIS_ORIGIN = (120.62, 14.40)
AIS_SPACING = (0.1, 0.08)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    logging.Formatter.converter = time.gmtime

    # Anchored to the repository rather than the working directory. `build/` is where the dev
    # server and the contract suite both look, and a relative path quietly produces a second
    # serving set that nothing reads when this is run from anywhere but the root.
    settings = Settings(data_root=PIPELINE_ROOT.parent / "build", run_id="demo")
    if settings.data_root.exists():
        shutil.rmtree(settings.data_root)

    document = json.loads(
        (PIPELINE_ROOT / "tests" / "fixtures" / "adsb_lol_point_manila.json").read_bytes()
    )
    # Rebase the recorded response onto now, so the demo is not permanently stale.
    now = utc_now()
    document["now"] = (now - timedelta(seconds=SWEEPS * SWEEP_INTERVAL_S)).timestamp() * 1000.0

    seed_window(settings, document, sweeps=SWEEPS, interval_s=SWEEP_INTERVAL_S)
    seed_ais_window(
        settings,
        window_s=AIS_WINDOW_S,
        start=now - timedelta(seconds=AIS_WINDOW_S),
        origin=AIS_ORIGIN,
        spacing=AIS_SPACING,
    )
    transform(settings, project_dir=PIPELINE_ROOT / "transform", now=now)
    manifest = bake(settings, now=now)

    for layer in manifest.layers:
        log.info(
            "%-22s zoom %2d-%-2d features=%4d vertices=%6d points=%5d %8dB %s",
            layer.id,
            layer.min_zoom,
            layer.max_zoom,
            layer.feature_count,
            layer.budget.path_vertices,
            layer.budget.points,
            layer.budget.bytes,
            layer.freshness,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
