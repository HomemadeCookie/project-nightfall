import pytest
import yaml

from nightfall.answers import engine
from nightfall.core.contracts import Answer, QuestionSpec
from nightfall.core.reference import reference_dir


def test_every_question_spec_loads_and_ids_are_unique():
    specs = engine.load_specs()
    assert len(specs) == 11
    assert {s.tier for s in specs.values()} == {1, 2, 3}


def test_specs_and_modules_match_exactly():
    import importlib

    specs = engine.load_specs()
    module_ids = {
        importlib.import_module(f"nightfall.answers.questions.{m}").QUESTION_ID for m in engine.MODULES
    }
    implemented = {k for k, s in specs.items() if s.implemented}
    assert module_ids == implemented
    for qid in set(specs) - implemented:
        assert specs[qid].status == "planned"


def test_every_spec_states_how_it_will_be_validated():
    for s in engine.load_specs().values():
        assert s.baseline and s.ship_when and s.decision and s.buyers and s.ask.fil


def test_spec_rejects_unknown_fields_and_bad_ids():
    base = yaml.safe_load(
        (next((reference_dir().parent / "questions").rglob("fuel.next_week.yaml"))).read_text()
    )
    QuestionSpec.model_validate(base)
    with pytest.raises(ValueError):
        QuestionSpec.model_validate({**base, "surprise": 1})
    with pytest.raises(ValueError):
        QuestionSpec.model_validate({**base, "id": "nodot"})


def test_answer_rejects_out_of_range_coverage():
    with pytest.raises(ValueError):
        Answer.model_validate(
            {
                "question_id": "a.b",
                "question_version": 1,
                "scope": {},
                "as_of": "2026-01-01T00:00:00Z",
                "verdict": "x",
                "confidence": "low",
                "coverage": 1.5,
                "text": {"en": "x"},
                "model": {"name": "m", "version": "1", "status": "unvalidated"},
                "license": [],
            }
        )


def test_checked_in_json_schemas_are_current():
    import json

    out = reference_dir().parent / "contracts"
    for name, model in {"answer": Answer, "question": QuestionSpec}.items():
        path = out / f"{name}.schema.json"
        assert path.exists(), "run `nightfall contracts`"
        assert json.loads(path.read_text()) == model.model_json_schema(), (
            f"{name} schema is stale: run `nightfall contracts`"
        )


def test_reference_data_is_consistent():
    from nightfall.core import reference

    ports = {p["port_id"]: p for p in reference.ports()}
    regions = {r["region_code"]: r for r in reference.regions()}
    routes = {r["route_id"] for r in reference.ferry_routes()}
    for r in regions.values():
        assert r["primary_port_id"] in ports, r["region_code"]
        assert set(r["ferry_route_ids"]) <= routes, r["region_code"]
    assert len({p["portwatch_id"] for p in ports.values()}) == len(ports)
    items = reference.price_items()
    assert len({i["item_id"] for i in items}) == len(items)
    commodity_ids = {c["commodity_id"] for c in reference.commodities()}
    assert {i["commodity_id"] for i in items if i["commodity_id"]} <= commodity_ids
    for r in reference.ferry_routes():
        for lat, lon in r["line"]:
            assert 4 < lat < 22 and 115 < lon < 130, f"{r['route_id']} point outside the Philippines"
