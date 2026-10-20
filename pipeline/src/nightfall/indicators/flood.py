"""Flood squares: four satellite dates, a class mask, and a storm-track trigger.

The number that leaves this module is a fraction of a 2.56 km square. Pixels are
not an answer. A missing date stays missing; nothing is copied into an empty slot.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from nightfall.core.context import Context
from nightfall.core.geo import haversine_km
from nightfall.core.reference import flood_chips
from nightfall.core.settings import lake_root
from nightfall.indicators.storms import current_tracks, position_at, worst_exposure

CLOUD_MAX = 40.0  # Sentinel-2 percent; radar has no cloud field
FLOOD_CLASS = 2  # TerraMind: 0 dry, 1 permanent water, 2 flood water
IGNORE = 255
NEAR_KM = 80.0
HORIZON_H = 48
FLOOD_FRACTION = 0.05
RECENT_PASS = timedelta(days=6)


@dataclass(frozen=True)
class Slot:
    role: str
    item_id: str | None
    sensing_time: datetime | None
    collection: str | None

    @property
    def missing(self) -> bool:
        return self.item_id is None


@dataclass(frozen=True)
class DateRecipe:
    split: datetime
    slots: tuple[Slot, ...]

    @property
    def filled(self) -> int:
        return sum(not s.missing for s in self.slots)

    def slot(self, role: str) -> Slot:
        for s in self.slots:
            if s.role == role:
                return s
        raise KeyError(role)


def mask_dir() -> Path:
    env = os.environ.get("NIGHTFALL_FLOOD_MASKS")
    return Path(env) if env else lake_root() / "flood_masks"


def crop_window(
    image: np.ndarray,
    image_bbox: tuple[float, float, float, float],
    chip_bbox: tuple[float, float, float, float],
) -> np.ndarray:
    """Cut a north-up array to a chip. Both boxes are west, south, east, north."""
    west, south, east, north = image_bbox
    cw, cs, ce, cn = chip_bbox
    if east <= west or north <= south:
        raise ValueError("image bbox is empty")
    height, width = image.shape[-2:]

    def col(lon: float) -> int:
        return int(round((lon - west) / (east - west) * width))

    def row(lat: float) -> int:
        return int(round((north - lat) / (north - south) * height))

    r0, r1 = max(0, row(cn)), min(height, row(cs))
    c0, c1 = max(0, col(cw)), min(width, col(ce))
    if r1 <= r0 or c1 <= c0:
        raise ValueError("chip is outside the image")
    return image[..., r0:r1, c0:c1]


def flooded_fraction(mask: np.ndarray, flood_class: int = FLOOD_CLASS) -> float | None:
    """Share of valid pixels in the flood class. 255 is ignored, not counted as dry."""
    valid = mask != IGNORE
    n = int(valid.sum())
    if n == 0:
        return None
    return float((mask[valid] == flood_class).sum()) / n


def flood_iou(
    pred: np.ndarray,
    ref: np.ndarray,
    *,
    pred_flood: int = FLOOD_CLASS,
    ref_flood: int = 1,
) -> float | None:
    """Intersection over union. Reference floods are class 1; model floods are class 2."""
    if pred.shape != ref.shape:
        raise ValueError(f"shape {pred.shape} != {ref.shape}")
    valid = (pred != IGNORE) & (ref != IGNORE)
    if not int(valid.sum()):
        return None
    p = (pred == pred_flood) & valid
    r = (ref == ref_flood) & valid
    union = int((p | r).sum())
    if union == 0:
        return None
    return float((p & r).sum()) / union


def _clear_optical(row: dict) -> bool:
    if row["collection"] != "sentinel-2-l2a":
        return True
    cover = row.get("cloud_cover")
    return cover is None or cover <= CLOUD_MAX


def _pick(
    rows: list[dict],
    *,
    after: datetime | None,
    before: datetime | None,
    collection: str,
    earliest: bool,
) -> dict | None:
    chosen = None
    for row in rows:
        if row["collection"] != collection or not _clear_optical(row):
            continue
        t = row["sensing_time"]
        if after is not None and t < after:
            continue
        if before is not None and t >= before:
            continue
        if chosen is None:
            chosen = row
            continue
        if earliest and t < chosen["sensing_time"]:
            chosen = row
        if not earliest and t > chosen["sensing_time"]:
            chosen = row
    return chosen


def _slot(role: str, row: dict | None) -> Slot:
    if row is None:
        return Slot(role, None, None, None)
    return Slot(role, row["item_id"], row["sensing_time"], row["collection"])


def choose_dates(scenes: list[dict], split: datetime) -> DateRecipe:
    """Four dates around ``split``. A role with no scene is an empty slot."""
    pre_opt = _pick(scenes, after=None, before=split, collection="sentinel-2-l2a", earliest=False)
    pre_sar = _pick(scenes, after=None, before=split, collection="sentinel-1-rtc", earliest=False)
    post_sar = _pick(scenes, after=split, before=None, collection="sentinel-1-rtc", earliest=True)
    post_opt = _pick(scenes, after=split, before=None, collection="sentinel-2-l2a", earliest=True)
    return DateRecipe(
        split,
        (
            _slot("pre_optical", pre_opt),
            _slot("pre_radar", pre_sar),
            _slot("post_radar", post_sar),
            _slot("post_optical", post_opt),
        ),
    )


def scenes_for(ctx: Context, chip_id: str) -> list[dict]:
    return ctx.rows("satellite_scenes", "chip_id = ?", [chip_id], order="sensing_time")


def arrival_time(ctx: Context, lat: float, lon: float) -> datetime | None:
    """Earliest track step at or before as_of whose wind field covers the square."""
    target = (lat, lon)
    found: datetime | None = None
    for track in current_tracks(ctx):
        if not track.points:
            continue
        t = track.points[0].time
        while t <= ctx.as_of:
            pos = position_at(track, t)
            if pos is not None and haversine_km((pos.lat, pos.lon), target) <= pos.radius_km:
                found = t if found is None else min(found, t)
                break
            t += timedelta(hours=3)
    return found


def split_for(ctx: Context, lat: float, lon: float) -> datetime:
    """When the 'after' pictures start.

    If a storm has already covered the square, the split is its arrival.
    Otherwise a pass in the last six days can still be the after image.
    """
    arrived = arrival_time(ctx, lat, lon)
    if arrived is not None:
        return arrived
    return ctx.as_of - RECENT_PASS


def storm_over(ctx: Context, lat: float, lon: float):
    """Storm that is, or will within two days be, on top of the square."""
    exp = worst_exposure(ctx, [(lat, lon)], HORIZON_H)
    if exp is None or exp.min_distance_km == float("inf"):
        return None
    if exp.hours_inside > 0 or exp.min_distance_km <= NEAR_KM:
        return exp
    return None


def load_mask(chip_id: str, item_id: str) -> np.ndarray | None:
    path = mask_dir() / chip_id / f"{item_id}.npy"
    if not path.exists():
        return None
    mask = np.load(path)
    if mask.ndim != 2:
        raise ValueError(f"{path} must be a 2-d class mask")
    return mask


def sync_triggers(lake, ctx: Context) -> int:
    """Replace lake/triggers/flood_*.json with one note per square a storm covers."""
    dest = lake.root / "triggers"
    dest.mkdir(parents=True, exist_ok=True)
    wanted: dict[str, dict] = {}
    for chip in flood_chips():
        exp = storm_over(ctx, chip["lat"], chip["lon"])
        if exp is None or exp.hours_inside <= 0:
            continue
        name = f"flood_{exp.storm_id}_{chip['chip_id']}.json"
        distance = exp.min_distance_km
        wanted[name] = {
            "chip_id": chip["chip_id"],
            "name": chip["name"],
            "storm_id": exp.storm_id,
            "storm": exp.name,
            "as_of": ctx.as_of.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "min_distance_km": None if distance == float("inf") else round(distance, 1),
        }
    for old in dest.glob("flood_*.json"):
        if old.name not in wanted:
            old.unlink()
    for name, body in wanted.items():
        (dest / name).write_text(json.dumps(body, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return len(wanted)


def score_flood_references(directory: Path) -> dict:
    """Score archived pred/ref pairs. A satellite call needs 3 events, each with IoU >= 0.6."""
    events = []
    if directory.exists():
        for path in sorted(directory.glob("*.npz")):
            data = np.load(path)
            iou = flood_iou(data["pred"], data["ref"])
            events.append({"event": path.stem, "iou": None if iou is None else round(float(iou), 3)})
    passing = [e for e in events if e["iou"] is not None and e["iou"] >= 0.6]
    ship = len(events) >= 3 and len(passing) == len(events)
    if not events:
        summary = "0 reference floods on file; satellite calls stay withheld until 3 events score IoU >= 0.6"
    else:
        summary = f"{len(passing)}/{len(events)} reference floods have IoU >= 0.6"
    return {
        "status": "experimental" if ship else "unvalidated",
        "ship_satellite": ship,
        "n_events": len(events),
        "n_passing": len(passing),
        "events": events,
        "summary": summary,
    }
