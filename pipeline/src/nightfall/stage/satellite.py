"""Scene catalog rows. One row per chip and STAC item, newest fetch wins."""

from __future__ import annotations

from nightfall.core.lake import Lake
from nightfall.core.time import parse_iso
from nightfall.stage.common import make_table, num


def stage_satellite_scenes(lake: Lake):
    best: dict[tuple[str, str], tuple] = {}
    for rec in lake.iter_raw("planetary_stac", "scenes"):
        payload = rec["payload"]
        sensing = payload.get("sensing_time")
        chip_id, item_id = payload.get("chip_id"), payload.get("item_id")
        if not sensing or not chip_id or not item_id:
            continue
        key = (chip_id, item_id)
        prev = best.get(key)
        if prev is None or rec["fetched_at"] >= prev[0]:
            best[key] = (rec["fetched_at"], payload)
    rows = []
    for fetched_at, payload in best.values():
        rows.append(
            {
                "chip_id": payload["chip_id"],
                "item_id": payload["item_id"],
                "collection": payload.get("collection") or "",
                "sensing_time": parse_iso(payload["sensing_time"]),
                "available_on": fetched_at,
                "cloud_cover": num(payload.get("cloud_cover")),
                "west": float(payload["west"]),
                "south": float(payload["south"]),
                "east": float(payload["east"]),
                "north": float(payload["north"]),
                "item_href": payload.get("item_href") or "",
            }
        )
    cols = {
        "chip_id": "str",
        "item_id": "str",
        "collection": "str",
        "sensing_time": "ts",
        "available_on": "ts",
        "cloud_cover": "f",
        "west": "f",
        "south": "f",
        "east": "f",
        "north": "f",
        "item_href": "str",
    }
    return {"satellite_scenes": make_table(rows, cols)}
