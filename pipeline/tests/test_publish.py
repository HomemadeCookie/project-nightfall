import json

import pytest

from nightfall.answers import engine
from nightfall.core.context import Context
from nightfall.core.contracts import Answer, LocalizedText, ModelInfo
from nightfall.publish import license_gate
from nightfall.publish.bake import bake
from tests.helpers import NOW, full_lake


def fake_answer(sources):
    return Answer(
        question_id="x.y",
        question_version=1,
        scope={"a": "b"},
        as_of=NOW,
        verdict="ok",
        confidence="low",
        coverage=1.0,
        text=LocalizedText(en="hi"),
        sources=sources,
        license=[],
        model=ModelInfo(name="m", version="1", status="unvalidated"),
    )


def test_gate_clears_public_domain_and_approved_sources():
    assert license_gate.check(fake_answer(["eia", "frankfurter"])).commercial_ok
    assert license_gate.check(
        fake_answer(["worldbank", "adsb_lol"])
    ).commercial_ok  # approved in the register


def test_gate_blocks_non_commercial_and_unreviewed_sources():
    g = license_gate.check(fake_answer(["eia", "open_meteo", "portwatch"]))
    assert not g.commercial_ok and len(g.reasons) == 2
    assert any("NON_COMMERCIAL" in r and "open_meteo" in r for r in g.reasons)
    assert any("UNCLEAR" in r and "portwatch" in r for r in g.reasons)


def test_a_licence_review_can_clear_a_source(monkeypatch):
    monkeypatch.setattr(
        license_gate, "reviews", lambda: {"portwatch": {"approved": True, "basis": "IMF email 2026-11-01"}}
    )
    assert license_gate.check(fake_answer(["portwatch"])).commercial_ok
    assert not license_gate.check(fake_answer(["gdacs"])).commercial_ok  # still unreviewed


def test_default_register_never_clears_non_commercial_without_evidence():
    for name, row in ((r["name"], r) for r in license_gate.source_table()):
        if "NON_COMMERCIAL" in row["license"]:
            assert not row["commercial_ok"], f"{name} must stay blocked until a licence is bought or swapped"


@pytest.fixture
def baked(tmp_path):
    lake = full_lake(tmp_path / "lake")
    ctx = Context.from_lake(lake, NOW)
    result = engine.run_all(ctx)
    return lake, ctx, result


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_research_mode_publishes_everything_and_labels_commercial_status(baked, tmp_path):
    lake, ctx, result = baked
    m = bake(lake, ctx, result, tmp_path / "dist", mode="research")
    out = tmp_path / "dist"
    index = read(out / "answers" / "index.json")
    assert len(index) == len(result.flat()) == m["counts"]["answers"] and m["counts"]["blocked"] == 0
    by_q = {}
    for a in index:
        by_q.setdefault(a["question_id"], set()).add(a["commercial_ok"])
    assert by_q["fuel.next_week"] == {True}  # eia + frankfurter only
    assert by_q["ferry.suspension"] == {False}  # open_meteo is non-commercial
    assert m["banner"] and "Research preview" in m["banner"]
    assert (out / "answers" / "fuel.next_week.json").exists() and not (out / "blocked.json").exists()


def test_commercial_mode_drops_blocked_answers_and_explains_why(baked, tmp_path):
    lake, ctx, result = baked
    m = bake(lake, ctx, result, tmp_path / "dist", mode="commercial")
    out = tmp_path / "dist"
    index = read(out / "answers" / "index.json")
    assert index and all(a["commercial_ok"] for a in index)
    # Only questions whose every input is cleared survive: eia/frankfurter (fuel) and adsb.lol (air cargo).
    assert {a["question_id"] for a in index} == {"fuel.next_week", "aircargo.activity"}
    blocked = read(out / "blocked.json")
    assert m["counts"]["blocked"] == len(blocked) > 0
    assert all(b["reasons"] for b in blocked)
    assert m["banner"] is None
    assert not (out / "answers" / "ferry.suspension.json").exists()


def test_manifest_lists_sources_questions_and_freshness(baked, tmp_path):
    lake, ctx, result = baked
    m = bake(lake, ctx, result, tmp_path / "dist")
    srcs = {s["name"]: s for s in m["sources"]}
    assert srcs["eia"]["commercial_ok"] and not srcs["open_meteo"]["commercial_ok"]
    assert srcs["eia"]["fresh"]["status"] == "ok" and srcs["eia"]["fresh"]["data_through"] == "2026-10-15"
    assert srcs["gdelt"]["fresh"]["status"] == "missing"  # nothing ingested in this lake
    qs = {q["id"]: q for q in m["questions"]}
    assert (
        qs["lastmile.flood_access"]["model_status"] == "planned"
        and not qs["lastmile.flood_access"]["implemented"]
    )
    assert qs["fuel.next_week"]["n_answers"] == 2 and qs["fuel.next_week"]["error"] is None
    assert read(tmp_path / "dist" / "manifest.json")["generated_at"] == "2026-10-16T12:00:00Z"


def test_bake_writes_chart_datasets(baked, tmp_path):
    lake, ctx, result = baked
    bake(lake, ctx, result, tmp_path / "dist")
    d = tmp_path / "dist" / "data"
    fuel = read(d / "fuel_weekly.json")
    assert len(fuel["diesel"]) >= 8 and fuel["diesel"][0]["php_per_l"] > 0
    ports = read(d / "ports_daily.json")
    assert ports["MNL"]["series"] and ports["MNL"]["lat"] > 14
    assert read(d / "chokepoints.json")["chokepoint5"]["series"]
    assert "rice_regular" in read(d / "prices.json")
    storms = read(d / "storms.json")
    assert storms["storms"][0]["name"] == "TESTSTORM" and storms["storms"][0]["points"]
    ref = read(d / "reference.json")
    assert len(ref["ferry_routes"]) == 8 and len(ref["regions"]) == 17


def test_bake_is_idempotent_and_replaces_old_output(baked, tmp_path):
    lake, ctx, result = baked
    out = tmp_path / "dist"
    bake(lake, ctx, result, out)
    (out / "stale.json").write_text("{}")
    bake(lake, ctx, result, out)
    assert not (out / "stale.json").exists()


def test_bake_rejects_unknown_mode(baked, tmp_path):
    lake, ctx, result = baked
    with pytest.raises(ValueError):
        bake(lake, ctx, result, tmp_path / "d", mode="yolo")


def test_answers_carry_attribution_for_every_source(baked):
    _, _, result = baked
    for a in result.flat():
        assert a.attributions, f"{a.key} has no attribution"


def test_bake_refuses_to_delete_a_directory_it_did_not_create(baked, tmp_path):
    lake, ctx, result = baked
    precious = tmp_path / "documents"
    precious.mkdir()
    (precious / "thesis.docx").write_text("do not delete")
    with pytest.raises(RuntimeError, match="refusing to delete"):
        bake(lake, ctx, result, precious)
    assert (precious / "thesis.docx").exists()
    empty = tmp_path / "empty"
    empty.mkdir()
    bake(lake, ctx, result, empty)  # an empty directory is fine
    assert (empty / "manifest.json").exists()


def test_manifest_lists_what_exists_so_clients_do_not_probe_for_files(baked, tmp_path):
    lake, ctx, result = baked
    m = bake(lake, ctx, result, tmp_path / "dist")
    assert {"fuel_weekly", "ports_daily", "reference", "storms"} <= set(m["datasets"])
    assert m["reports"] == []  # tests run with an empty reports directory
