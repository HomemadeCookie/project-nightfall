"""Command line: ``nightfall ingest|build|answer|backtest|publish|lineage``."""

from __future__ import annotations

import argparse
import sys
import traceback

from nightfall.core.http import Http
from nightfall.core.lake import Lake
from nightfall.core.settings import lake_root
from nightfall.core.time import utcnow


def cmd_ingest(args: argparse.Namespace) -> int:
    from nightfall.sources.registry import all_sources

    sources = all_sources()
    names = args.sources or sorted(sources)
    unknown = [n for n in names if n not in sources]
    if unknown:
        print(f"unknown sources: {unknown}; known: {sorted(sources)}", file=sys.stderr)
        return 2
    lake, now, failures = Lake(lake_root()), utcnow(), 0
    with Http() as http:
        for name in names:
            cls = sources[name]
            if args.cadence and cls.cadence != args.cadence:
                continue
            try:
                inc = getattr(cls, "incremental", None)
                known = lake.known_requests(cls.name, inc[0], inc[1]) if inc else set()
                envelopes = list(cls(http, lookback_days=args.lookback_days, known=known).fetch(now))
                paths = lake.write_raw(envelopes, skip_known=cls.snapshot)
                lake.record_fetch(name, now)
                print(f"ok   {name:<12} {len(envelopes)} envelope(s), {len(paths)} new file(s)")
            except Exception as exc:  # one broken source must not stop the others
                failures += 1
                lake.record_fetch(name, now, ok=False)
                print(f"FAIL {name:<12} {type(exc).__name__}: {exc}", file=sys.stderr)
                if args.verbose:
                    traceback.print_exc()
    return 1 if failures else 0


def _context(args: argparse.Namespace):
    from nightfall.core.context import Context
    from nightfall.core.time import parse_iso

    as_of = parse_iso(args.as_of) if getattr(args, "as_of", None) else utcnow()
    return Lake(lake_root()), Context.from_lake(Lake(lake_root()), as_of)


def cmd_stage(args: argparse.Namespace) -> int:
    from nightfall.stage import stage_all

    for name, n in stage_all(Lake(lake_root())).items():
        print(f"staged {name:<20}{n:>9} rows")
    return 0


def _persist_answers(lake: Lake, result, as_of) -> None:
    import json

    import pyarrow as pa

    rows = [
        {
            "question_id": a.question_id,
            "scope": json.dumps(a.scope, sort_keys=True),
            "as_of": a.as_of.isoformat(),
            "verdict": a.verdict,
            "confidence": a.confidence,
            "coverage": a.coverage,
            "answer_json": a.model_dump_json(),
        }
        for a in result.flat()
    ]
    if rows:
        lake.write_table("answers", f"run_{as_of:%Y%m%dt%H%M}", pa.Table.from_pylist(rows))


def cmd_answer(args: argparse.Namespace) -> int:
    from nightfall.answers.engine import run_all

    lake, ctx = _context(args)
    result = run_all(ctx, set(args.only) if args.only else None)
    _persist_answers(lake, result, ctx.as_of)
    for qid, answers in result.answers.items():
        print(f"{qid:<28}{len(answers):>4} answers")
    for qid, err in result.errors.items():
        print(f"ERROR {qid}:\n{err}", file=sys.stderr)
    if args.show:
        for a in result.flat():
            if a.question_id in (args.show or []):
                print(f"- [{a.verdict}/{a.confidence}] {a.text.en}")
    return 1 if result.errors else 0


def cmd_backtest(args: argparse.Namespace) -> int:
    from nightfall.eval import backtests
    from nightfall.eval.report import write_report

    _, ctx = _context(args)
    jobs = {
        "ports.pressure": backtests.backtest_ports,
        "staples.price_direction": backtests.backtest_prices,
        "fuel.next_week": backtests.backtest_fuel,
        "lastmile.flood_access": backtests.backtest_flood,
    }
    for qid, fn in jobs.items():
        if args.only and qid not in args.only:
            continue
        body = fn(ctx)
        path = write_report(qid, body)
        print(f"{qid:<26}{body['status']:<13}{body.get('summary', '')}\n  -> {path}")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    from nightfall.answers.engine import run_all
    from nightfall.core.settings import dist_root
    from nightfall.publish.bake import bake

    lake, ctx = _context(args)
    from nightfall.indicators.flood import sync_triggers

    n = sync_triggers(lake, ctx)
    print(f"flood triggers {n}")
    result = run_all(ctx)
    _persist_answers(lake, result, ctx.as_of)
    manifest = bake(lake, ctx, result, dist_root(), mode=args.mode)
    c = manifest["counts"]
    print(
        f"published {c['answers']} answers ({c['blocked']} blocked, {c['errors']} errors) "
        f"to {dist_root()} [{args.mode}]"
    )
    return 1 if c["errors"] else 0


def cmd_build(args: argparse.Namespace) -> int:
    rc = cmd_stage(args)
    return rc or cmd_publish(args)


def cmd_lineage(args: argparse.Namespace) -> int:
    from nightfall.answers.engine import load_specs
    from nightfall.publish.license_gate import source_status

    specs = load_specs()
    if args.question not in specs:
        print(f"unknown question {args.question!r}; known: {sorted(specs)}", file=sys.stderr)
        return 2
    spec = specs[args.question]
    print(f"{spec.id} (tier {spec.tier}, {spec.status}) inputs:")
    for item in spec.inputs:
        name = item.split(".")[0]
        try:
            ok, why = source_status(name)
            print(f"  {item:<36}{'OK ' if ok else 'BLOCKED'}  {why}")
        except KeyError:
            print(f"  {item:<36}(derived or planned)")
    return 0


def cmd_exposure(args: argparse.Namespace) -> int:
    from pathlib import Path

    from nightfall.answers.questions.typhoon_exposure import load_sites, run

    _, ctx = _context(args)
    for a in run(ctx, sites=load_sites(Path(args.sites))):
        print(f"[{a.verdict}] {a.text.en}")
    return 0


def cmd_flood_infer(args: argparse.Namespace) -> int:
    from pathlib import Path

    import numpy as np

    from nightfall.indicators.terramind import TerraMindUnavailable, build_input, predict

    data = np.load(args.stack)
    try:
        mask = predict(build_input(data["s2"], data["s1"], data["dem"]), args.config, args.checkpoint)
    except TerraMindUnavailable as exc:
        print(exc, file=sys.stderr)
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.save(out, mask)
    print(f"wrote {out} {mask.shape}")
    return 0


def cmd_contracts(args: argparse.Namespace) -> int:
    import json

    from nightfall.core.contracts import Answer, QuestionSpec
    from nightfall.core.envelope import Envelope
    from nightfall.core.reference import reference_dir

    out = reference_dir().parent / "contracts"
    out.mkdir(exist_ok=True)
    for name, model in {"answer": Answer, "question": QuestionSpec, "envelope": Envelope}.items():
        (out / f"{name}.schema.json").write_text(json.dumps(model.model_json_schema(), indent=2) + "\n")
        print(f"wrote contracts/{name}.schema.json")
    return 0


def cmd_collect_ais(args: argparse.Namespace) -> int:
    """Run the AIS source in 10-minute chunks until ``--seconds`` have passed."""
    import os
    import time

    from nightfall.sources.ships.aisstream import AisStream

    if not os.environ.get("AISSTREAM_API_KEY"):
        print(
            "AISSTREAM_API_KEY is not set. Get a free key at https://aisstream.io (GitHub sign-in).",
            file=sys.stderr,
        )
        return 2
    lake, end, total = Lake(lake_root()), time.monotonic() + args.seconds, 0
    with Http() as http:
        while time.monotonic() < end:
            src = AisStream(http)
            src.listen_seconds = min(600.0, end - time.monotonic())
            envs = list(src.fetch(utcnow()))
            lake.write_raw(envs)
            total += sum(len(e.payload) for e in envs)
    print(f"wrote {total} AIS records")
    return 0


def cmd_events(args: argparse.Namespace) -> int:
    """Extract news events; optionally append fuel adjustments to the ground-truth CSV."""
    import csv

    from nightfall.core.reference import reference_dir
    from nightfall.detect.text_events import extract_fuel_adjustments, extract_sea_trip_notices

    _, ctx = _context(args)
    items = ctx.rows("news_items", order="first_seen")
    fuel = extract_fuel_adjustments(items)
    sea = extract_sea_trip_notices(items)
    print(f"{len(items)} headlines -> {len(fuel)} fuel-adjustment candidates, {len(sea)} sea-trip notices")
    for e in fuel:
        print(f"  fuel  {e['effective_date']} {e['product']:<9}{e['delta_php_l']:+.2f}  {e['title'][:70]}")
    for e in sea:
        print(f"  sea   {e['kind']:<9}{','.join(e['routes']) or '-':<24}{(e['title'] or '')[:60]}")
    if args.append_ground_truth and fuel:
        path = reference_dir().parent / "eval" / "ground_truth" / "fuel_adjustments.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        have = set()
        if path.exists():
            with open(path, newline="", encoding="utf-8") as fh:
                have = {(r["effective_date"], r["product"]) for r in csv.DictReader(fh)}
        new = [e for e in fuel if (e["effective_date"].isoformat(), e["product"]) not in have]
        write_header = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if write_header:
                w.writerow(["effective_date", "product", "delta_php_l", "source_url"])
            for e in new:
                w.writerow([e["effective_date"].isoformat(), e["product"], e["delta_php_l"], e["url"]])
        print(f"appended {len(new)} new rows to {path} (review them before trusting)")
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    """Drop old raw files from high-volume sources so the lake stays inside free storage limits."""
    from datetime import timedelta

    from nightfall.sources.registry import all_sources

    lake, cutoff = Lake(lake_root()), utcnow() - timedelta(days=args.keep_days)
    for name, cls in sorted(all_sources().items()):
        if cls.cadence in ("hourly", "stream"):
            print(f"pruned {name:<12}{lake.prune_raw(name, cutoff):>5} files older than {args.keep_days} d")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nightfall")
    sub = p.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest", help="fetch sources into the raw lake")
    ing.add_argument("sources", nargs="*")
    ing.add_argument("--cadence", choices=["hourly", "daily", "weekly"])
    ing.add_argument("--lookback-days", type=int, help="override how far back to fetch (backfill)")
    ing.add_argument("-v", "--verbose", action="store_true")
    ing.set_defaults(func=cmd_ingest)
    for name, fn, help_ in [
        ("stage", cmd_stage, "build typed staging tables from raw"),
        ("answer", cmd_answer, "run questions and store answers"),
        ("backtest", cmd_backtest, "walk-forward backtests; write eval/reports"),
        ("publish", cmd_publish, "bake answers and datasets into dist/"),
        ("build", cmd_build, "stage + answer + publish"),
    ]:
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--as-of", help="ISO time; default now")
        sp.set_defaults(func=fn)
        if name in ("answer", "backtest"):
            sp.add_argument("--only", nargs="*")
        if name == "answer":
            sp.add_argument("--show", nargs="*", help="print answer text for these question ids")
        if name in ("publish", "build"):
            sp.add_argument("--mode", choices=["research", "commercial"], default="research")
    pr = sub.add_parser("prune", help="delete old raw files from hourly/stream sources")
    pr.add_argument("--keep-days", type=int, default=180)
    pr.set_defaults(func=cmd_prune)
    ev = sub.add_parser("events", help="extract fuel-adjustment and sea-trip events from news")
    ev.add_argument("--as-of")
    ev.add_argument("--append-ground-truth", action="store_true")
    ev.set_defaults(func=cmd_events)
    ca = sub.add_parser("collect-ais", help="listen to AISStream (needs AISSTREAM_API_KEY)")
    ca.add_argument("--seconds", type=float, default=3300)
    ca.set_defaults(func=cmd_collect_ais)
    lin = sub.add_parser("lineage", help="show a question's inputs and licence status")
    lin.add_argument("question")
    lin.set_defaults(func=cmd_lineage)
    exp = sub.add_parser("exposure", help="storm exposure for your own sites (CSV: site_id,name,lat,lon)")
    exp.add_argument("--sites", required=True)
    exp.add_argument("--as-of")
    exp.set_defaults(func=cmd_exposure)
    inf = sub.add_parser("flood-infer", help="run TerraMind on one chip stack (.npz with s2, s1, dem)")
    inf.add_argument("--stack", required=True)
    inf.add_argument("--config", required=True, help="TerraTorch yaml for TerraMind-base-Flood")
    inf.add_argument("--checkpoint", required=True)
    inf.add_argument("--out", required=True, help="where to write the uint8 class mask (.npy)")
    inf.set_defaults(func=cmd_flood_infer)
    con = sub.add_parser("contracts", help="write JSON Schemas to contracts/")
    con.set_defaults(func=cmd_contracts)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
