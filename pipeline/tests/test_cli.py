import json
from datetime import UTC, datetime

import pytest

from nightfall import cli
from nightfall.core.lake import Lake
from nightfall.core.license import License
from nightfall.sources.base import Source
from tests.helpers import full_lake, put


@pytest.fixture
def env(tmp_path, monkeypatch):
    lake = full_lake(tmp_path / "lake")
    monkeypatch.setenv("NIGHTFALL_LAKE", str(tmp_path / "lake"))
    monkeypatch.setenv("NIGHTFALL_DIST", str(tmp_path / "dist"))
    return lake, tmp_path


AS_OF = "2026-10-16T12:00:00Z"


def test_stage_reports_row_counts(env, capsys):
    assert cli.main(["stage"]) == 0
    out = capsys.readouterr().out
    assert "staged eia_spot" in out and "staged port_daily" in out


def test_answer_prints_and_persists_every_run(env, capsys):
    _, tmp = env
    assert cli.main(["answer", "--as-of", AS_OF, "--show", "fuel.next_week"]) == 0
    out = capsys.readouterr().out
    assert "fuel.next_week" in out and "Tuesday" in out
    runs = list((tmp / "lake" / "answers").glob("run_*.parquet"))
    assert len(runs) == 1 and runs[0].name == "run_20261016t1200.parquet"
    con = Lake(tmp / "lake").connect()
    row = con.execute("SELECT question_id, answer_json FROM answers_run_20261016t1200 LIMIT 1").fetchone()
    assert json.loads(row[1])["question_id"] == row[0]


def test_answer_only_runs_the_requested_question(env, capsys):
    assert cli.main(["answer", "--as-of", AS_OF, "--only", "ports.pressure"]) == 0
    out = capsys.readouterr().out
    assert "ports.pressure" in out and "fuel.next_week" not in out


def test_publish_bakes_the_site_data(env, capsys):
    _, tmp = env
    assert cli.main(["publish", "--as-of", AS_OF]) == 0
    assert (tmp / "dist" / "manifest.json").exists()
    assert "[research]" in capsys.readouterr().out
    assert cli.main(["publish", "--as-of", AS_OF, "--mode", "commercial"]) == 0
    assert (tmp / "dist" / "blocked.json").exists()


def test_lineage_shows_which_inputs_block_commercial_use(env, capsys):
    assert cli.main(["lineage", "ferry.suspension"]) == 0
    out = capsys.readouterr().out
    assert "open_meteo.route_forecast" in out and "BLOCKED" in out and "NON_COMMERCIAL" in out
    assert cli.main(["lineage", "fuel.next_week"]) == 0
    assert "BLOCKED" not in capsys.readouterr().out
    assert cli.main(["lineage", "no.such"]) == 2


def test_exposure_reads_customer_sites(env, capsys, tmp_path):
    sites = tmp_path / "sites.csv"
    sites.write_text("site_id,name,lat,lon\nx,Tacloban depot,11.24,125.0\n")
    assert cli.main(["exposure", "--sites", str(sites), "--as-of", AS_OF]) == 0
    assert "Tacloban depot" in capsys.readouterr().out


def test_events_extracts_candidates_and_appends_ground_truth(env, capsys, tmp_path, monkeypatch):
    lake, tmp = env
    put(
        lake,
        "news_rss",
        "items",
        {
            "feed": "f",
            "items": [
                {
                    "title": "Diesel prices to go down by P1.25 per liter next week",
                    "url": "https://x/1",
                    "published": "2026-10-16T02:00:00Z",
                    "teaser": "",
                },
                {
                    "title": "Sea trips suspended in Matnog",
                    "url": "https://x/2",
                    "published": "2026-10-16T03:00:00Z",
                    "teaser": "",
                },
            ],
        },
    )
    cli.main(["stage"])
    monkeypatch.setattr("nightfall.core.reference.reference_dir", lambda: tmp_path / "reference")
    assert cli.main(["events", "--as-of", AS_OF, "--append-ground-truth"]) == 0
    out = capsys.readouterr().out
    assert "1 fuel-adjustment candidates, 1 sea-trip notices" in out and "-1.25" in out
    written = (tmp_path / "eval" / "ground_truth" / "fuel_adjustments.csv").read_text()
    assert "2026-10-20,diesel,-1.25,https://x/1" in written
    assert cli.main(["events", "--as-of", AS_OF, "--append-ground-truth"]) == 0  # idempotent
    assert (tmp_path / "eval" / "ground_truth" / "fuel_adjustments.csv").read_text().count("diesel") == 1


def test_prune_only_touches_hourly_and_stream_sources(env, capsys):
    lake, tmp = env
    put(lake, "gdacs", "tc_current", [], at=datetime(2025, 1, 1, tzinfo=UTC))
    put(lake, "eia", "spot_prices", [], at=datetime(2025, 1, 1, tzinfo=UTC))
    assert cli.main(["prune", "--keep-days", "30"]) == 0
    out = capsys.readouterr().out
    assert "pruned gdacs" in out and "pruned eia" not in out
    assert not (tmp / "lake" / "raw" / "source=gdacs" / "dataset=tc_current" / "date=2025-01-01").exists()
    assert (tmp / "lake" / "raw" / "source=eia" / "dataset=spot_prices" / "date=2025-01-01").exists()


def test_contracts_command_writes_schemas(env, capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("nightfall.core.reference.reference_dir", lambda: tmp_path / "reference")
    assert cli.main(["contracts"]) == 0
    assert (tmp_path / "contracts" / "answer.schema.json").exists()


# -- ingest ----------------------------------------------------------------------------------------
class GoodSource(Source):
    name = "good"
    license = [License.PUBLIC_DOMAIN]
    cadence = "daily"

    def fetch(self, now):
        yield self.envelope("things", {"n": 1}, now=now)


class BadSource(Source):
    name = "bad"
    license = [License.PUBLIC_DOMAIN]
    cadence = "daily"

    def fetch(self, now):
        raise RuntimeError("upstream is down")
        yield  # pragma: no cover


class HourlySource(GoodSource):
    name = "hourly_one"
    cadence = "hourly"


def test_ingest_isolates_failures_and_logs_them(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NIGHTFALL_LAKE", str(tmp_path / "lake"))
    monkeypatch.setattr(
        "nightfall.sources.registry.all_sources",
        lambda: {"good": GoodSource, "bad": BadSource, "hourly_one": HourlySource},
    )
    rc = cli.main(["ingest"])
    captured = capsys.readouterr()
    assert rc == 1  # a failure is visible to the scheduler...
    assert "ok   good" in captured.out and "FAIL bad" in captured.err  # ...but did not stop the others
    lake = Lake(tmp_path / "lake")
    assert lake.has_raw("good", "things")
    log = lake.fetch_log()
    assert "last_success" in log["good"] and "last_success" not in log["bad"] and "last_attempt" in log["bad"]


def test_ingest_filters_by_cadence_and_rejects_unknown_sources(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NIGHTFALL_LAKE", str(tmp_path / "lake"))
    monkeypatch.setattr(
        "nightfall.sources.registry.all_sources", lambda: {"good": GoodSource, "hourly_one": HourlySource}
    )
    assert cli.main(["ingest", "--cadence", "hourly"]) == 0
    out = capsys.readouterr().out
    assert "hourly_one" in out and "good" not in out
    assert cli.main(["ingest", "nope"]) == 2
    assert "unknown sources" in capsys.readouterr().err


def test_collect_ais_explains_the_missing_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NIGHTFALL_LAKE", str(tmp_path / "lake"))
    monkeypatch.delenv("AISSTREAM_API_KEY", raising=False)
    assert cli.main(["collect-ais", "--seconds", "1"]) == 2
    assert "AISSTREAM_API_KEY" in capsys.readouterr().err
