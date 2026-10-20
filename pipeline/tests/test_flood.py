"""Flood squares: catalog records, date slots, masks, and the answer that refuses to call early."""

from datetime import UTC, datetime

import httpx
import numpy as np

from nightfall.answers.questions.flood_access import run
from nightfall.core.context import Context
from nightfall.core.lake import Lake
from nightfall.indicators.flood import (
    choose_dates,
    crop_window,
    flood_iou,
    flooded_fraction,
    score_flood_references,
    sync_triggers,
)
from nightfall.indicators.terramind import build_input
from nightfall.sources.registry import all_sources
from nightfall.stage import stage_all
from tests.helpers import NOW, put, seed_storm
from tests.test_sources import run as fetch


def test_catalog_stores_scene_ids_and_drops_pixels():
    def body(req):
        collection = req.url.params["collections"]
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "id": f"{collection}_test",
                        "collection": collection,
                        "properties": {"datetime": "2026-10-10T02:21:00Z", "eo:cloud_cover": 12.5},
                        "assets": {"B04": {"href": "https://example.com/B04.tif?sig=SECRET"}},
                    }
                ]
            },
        )

    envs, _ = fetch(all_sources()["planetary_stac"], {"planetarycomputer": body})
    assert len(envs) == 12  # 4 squares x 3 collections
    blob = envs[0].model_dump_json()
    assert "SECRET" not in blob and "assets" not in envs[0].payload
    assert envs[0].payload["item_href"].endswith("/items/sentinel-1-rtc_test") or envs[0].payload[
        "item_href"
    ].endswith("_test")
    seen = envs[0].request["seen_key"]
    again, _ = fetch(all_sources()["planetary_stac"], {"planetarycomputer": body}, known={seen})
    assert len(again) == 11
    assert all(e.request["seen_key"] != seen for e in again)


def test_cloudy_optical_does_not_fill_a_slot_and_a_missing_date_stays_missing():
    split = datetime(2026, 10, 12, tzinfo=UTC)
    scenes = [
        {
            "collection": "sentinel-2-l2a",
            "sensing_time": datetime(2026, 10, 1, tzinfo=UTC),
            "cloud_cover": 10,
            "item_id": "opt-pre",
        },
        {
            "collection": "sentinel-2-l2a",
            "sensing_time": datetime(2026, 10, 5, tzinfo=UTC),
            "cloud_cover": 90,
            "item_id": "cloudy",
        },
        {
            "collection": "sentinel-1-rtc",
            "sensing_time": datetime(2026, 10, 8, tzinfo=UTC),
            "cloud_cover": None,
            "item_id": "sar-pre",
        },
        {
            "collection": "sentinel-1-rtc",
            "sensing_time": datetime(2026, 10, 14, tzinfo=UTC),
            "cloud_cover": None,
            "item_id": "sar-post",
        },
    ]
    recipe = choose_dates(scenes, split)
    assert recipe.slot("pre_optical").item_id == "opt-pre"
    assert recipe.slot("pre_radar").item_id == "sar-pre"
    assert recipe.slot("post_radar").item_id == "sar-post"
    assert recipe.slot("post_optical").missing
    assert recipe.filled == 3


def test_fraction_ignores_nodata_and_iou_uses_the_reference_flood_class():
    mask = np.array([[2, 0], [2, 255]], dtype=np.uint8)
    assert flooded_fraction(mask) == 2 / 3
    ref = np.array([[1, 0], [0, 1]], dtype=np.uint8)
    assert flood_iou(mask, ref) == 0.5


def test_crop_window_takes_the_north_west_of_a_north_up_image():
    image = np.arange(16).reshape(4, 4)
    chip = crop_window(image, (0, 0, 4, 4), (0, 2, 2, 4))
    assert chip.shape == (2, 2)
    assert chip.tolist() == [[0, 1], [4, 5]]


def test_terramind_input_repeats_the_dem_and_refuses_the_wrong_band_count():
    s2 = np.zeros((4, 12, 2, 2))
    s1 = np.zeros((4, 2, 2, 2))
    dem = np.ones((2, 2))
    stack = build_input(s2, s1, dem)
    assert stack["S2L2A"].shape == (1, 12, 4, 2, 2)
    assert stack["DEM"].shape == (1, 1, 4, 2, 2)
    assert np.all(stack["DEM"] == 1)
    try:
        build_input(np.zeros((4, 3, 2, 2)), s1, dem)
    except ValueError as exc:
        assert "s2" in str(exc)
    else:
        raise AssertionError("expected a shape error")


def test_reference_bar_needs_three_passing_events(tmp_path):
    assert score_flood_references(tmp_path).get("ship_satellite") is False
    pred = np.array([[2, 0]], dtype=np.uint8)
    ref = np.array([[1, 0]], dtype=np.uint8)
    for name in ("a", "b", "c"):
        np.savez(tmp_path / f"{name}.npz", pred=pred, ref=ref)
    scored = score_flood_references(tmp_path)
    assert scored["ship_satellite"] is True and scored["status"] == "experimental"


def _scene(chip, item, collection, sensing):
    return {
        "chip_id": chip,
        "item_id": item,
        "collection": collection,
        "sensing_time": sensing.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cloud_cover": 5,
        "west": 120.5,
        "south": 14.9,
        "east": 120.6,
        "north": 15.0,
        "item_href": f"https://example.test/{item}",
    }


def test_a_mask_is_shown_and_not_called_a_flood(lake_dir, monkeypatch, tmp_path):
    lake = Lake(lake_dir)
    sensing = datetime(2026, 10, 14, tzinfo=UTC)
    put(
        lake,
        "planetary_stac",
        "scenes",
        _scene("pampanga-lubao", "SAR_POST", "sentinel-1-rtc", sensing),
        at=datetime(2026, 10, 15, tzinfo=UTC),
        event_time=sensing,
    )
    stage_all(lake)
    out = tmp_path / "masks" / "pampanga-lubao"
    out.mkdir(parents=True)
    np.save(out / "SAR_POST.npy", np.array([[2, 2], [0, 1]], dtype=np.uint8))
    monkeypatch.setenv("NIGHTFALL_FLOOD_MASKS", str(tmp_path / "masks"))
    answers = {a.scope["chip"]: a for a in run(Context.from_lake(lake, NOW))}
    lubao = answers["pampanga-lubao"]
    assert lubao.verdict == "unvalidated"
    assert lubao.value["flooded_fraction"] == 0.5
    assert "not a flood call" in lubao.text.en
    assert lubao.sources == ["planetary_stac"]
    assert answers["pampanga-guagua"].verdict == "no_signal"


def test_a_storm_over_a_square_says_likely_and_writes_a_trigger(lake_dir):
    lake = Lake(lake_dir)
    seed_storm(lake, lat=14.94, lon=120.60, radius_deg=0.4, name="LOCAL")
    stage_all(lake)
    ctx = Context.from_lake(lake, NOW)
    answers = {a.scope["chip"]: a for a in run(ctx)}
    assert answers["pampanga-lubao"].verdict == "likely"
    assert "LOCAL" in answers["pampanga-lubao"].text.en
    assert "satellite" in answers["pampanga-lubao"].text.en
    assert sync_triggers(lake, ctx) >= 1
    notes = list((lake_dir / "triggers").glob("flood_*.json"))
    assert notes and any("pampanga-lubao" in p.read_text() for p in notes)


def test_flood_infer_stops_when_the_weights_are_not_installed(tmp_path):
    from nightfall.cli import main

    stack = tmp_path / "stack.npz"
    np.savez(stack, s2=np.zeros((4, 12, 2, 2)), s1=np.zeros((4, 2, 2, 2)), dem=np.ones((2, 2)))
    code = main(
        [
            "flood-infer",
            "--stack",
            str(stack),
            "--config",
            "missing.yaml",
            "--checkpoint",
            "missing.pt",
            "--out",
            str(tmp_path / "mask.npy"),
        ]
    )
    assert code == 2
    assert not (tmp_path / "mask.npy").exists()
