"""The lake: immutable raw envelopes plus replaceable derived tables, as Parquet on disk.

Layout::

    <root>/raw/source=<s>/dataset=<d>/date=<YYYY-MM-DD>/hour=<HH>/<sha>.parquet
    <root>/<layer>/<table>.parquet        # staging, entities, events, indicators, answers
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from nightfall.core.envelope import Envelope
from nightfall.core.time import parse_iso

RAW_SCHEMA = pa.schema(
    [
        ("source", pa.string()),
        ("source_version", pa.string()),
        ("dataset", pa.string()),
        ("license", pa.string()),
        ("fetched_at", pa.string()),
        ("event_time", pa.string()),
        ("request", pa.string()),
        ("payload_sha256", pa.string()),
        ("payload", pa.string()),
    ]
)

LAYERS = ("staging", "entities", "events", "features", "indicators", "answers")
_IDENT = re.compile(r"^[a-z][a-z0-9_]*$")


def _ident(value: str) -> str:
    if not _IDENT.match(value):
        raise ValueError(f"unsafe identifier: {value!r}")
    return value


def _lit(value: str) -> str:
    """SQL string literal (DuckDB cannot bind parameters inside CREATE VIEW)."""
    return "'" + value.replace("'", "''") + "'"


class Lake:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    # -- raw -----------------------------------------------------------------
    def write_raw(self, envelopes: Iterable[Envelope]) -> list[Path]:
        """Write envelopes, one Parquet file per (source, dataset, hour). Idempotent."""
        groups: dict[tuple[str, str, str, str], list[Envelope]] = {}
        for env in envelopes:
            day = env.fetched_at.strftime("%Y-%m-%d")
            hour = env.fetched_at.strftime("%H")
            groups.setdefault((_ident(env.source), _ident(env.dataset), day, hour), []).append(env)
        written: list[Path] = []
        for (source, dataset, day, hour), items in groups.items():
            rows = [e.to_row() for e in items]
            digest = hashlib.sha256("".join(sorted(r["payload_sha256"] for r in rows)).encode())
            folder = (
                self.root / "raw" / f"source={source}" / f"dataset={dataset}" / f"date={day}" / f"hour={hour}"
            )
            path = folder / f"{digest.hexdigest()[:16]}.parquet"
            if path.exists():
                continue
            folder.mkdir(parents=True, exist_ok=True)
            table = pa.Table.from_pylist(rows, schema=RAW_SCHEMA)
            tmp = path.with_suffix(".tmp")
            pq.write_table(table, tmp, compression="zstd")
            os.replace(tmp, path)
            written.append(path)
        return written

    def raw_glob(self, source: str, dataset: str) -> str:
        return str(
            self.root
            / "raw"
            / f"source={_ident(source)}"
            / f"dataset={_ident(dataset)}"
            / "*"
            / "*"
            / "*.parquet"
        )

    def has_raw(self, source: str, dataset: str) -> bool:
        base = self.root / "raw" / f"source={source}" / f"dataset={dataset}"
        return base.exists() and any(base.rglob("*.parquet"))

    def iter_raw(self, source: str, dataset: str) -> list[dict]:
        """All envelopes of a dataset, oldest fetch first, with JSON columns decoded."""
        if not self.has_raw(source, dataset):
            return []
        con = duckdb.connect(":memory:")
        rows = con.execute(
            "SELECT fetched_at, event_time, request, payload FROM read_parquet("
            f"{_lit(self.raw_glob(source, dataset))}) ORDER BY fetched_at"
        ).fetchall()
        return [
            {
                "fetched_at": parse_iso(f),
                "event_time": parse_iso(e) if e else None,
                "request": json.loads(r),
                "payload": json.loads(pl),
            }
            for f, e, r, pl in rows
        ]

    def known_requests(self, source: str, dataset: str, key: str) -> set[str]:
        """Values of ``request[key]`` already stored, so incremental sources skip them."""
        if not self.has_raw(source, dataset):
            return set()
        con = duckdb.connect(":memory:")
        rows = con.execute(
            f"SELECT DISTINCT json_extract_string(request, '$.{_ident(key)}') "
            f"FROM read_parquet({_lit(self.raw_glob(source, dataset))})"
        ).fetchall()
        return {r[0] for r in rows if r[0]}

    # -- derived tables ------------------------------------------------------
    def table_path(self, layer: str, name: str) -> Path:
        if layer not in LAYERS:
            raise ValueError(f"unknown layer {layer!r}")
        return self.root / layer / f"{_ident(name)}.parquet"

    def write_table(self, layer: str, name: str, table: pa.Table) -> Path:
        path = self.table_path(layer, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        pq.write_table(table, tmp, compression="zstd")
        os.replace(tmp, path)
        return path

    def has_table(self, layer: str, name: str) -> bool:
        return self.table_path(layer, name).exists()

    # -- query ---------------------------------------------------------------
    def connect(self) -> duckdb.DuckDBPyConnection:
        """In-memory DuckDB with a view per raw dataset (``raw_<source>__<dataset>``)
        and per derived table (``<layer>_<name>``)."""
        con = duckdb.connect(":memory:")
        con.execute("SET TimeZone = 'UTC'")  # timestamps come back as UTC, not the machine's zone
        raw = self.root / "raw"
        if raw.exists():
            for src_dir in sorted(raw.glob("source=*")):
                for ds_dir in sorted(src_dir.glob("dataset=*")):
                    s, d = src_dir.name[7:], ds_dir.name[8:]
                    glob = self.raw_glob(s, d)
                    con.execute(
                        f'CREATE VIEW "raw_{s}__{d}" AS SELECT * FROM read_parquet('
                        f"{_lit(glob)}, hive_partitioning=false, union_by_name=true)"
                    )
        for layer in LAYERS:
            for p in sorted((self.root / layer).glob("*.parquet")):
                con.execute(f'CREATE VIEW "{layer}_{p.stem}" AS SELECT * FROM read_parquet({_lit(str(p))})')
        return con
