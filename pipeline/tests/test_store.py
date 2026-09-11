"""The immutable landing zone (invariant 2)."""

from __future__ import annotations

import gzip
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nightfall.store import LocalRawStore, object_path, request_hash, suffix_for

AT = datetime(2026, 9, 11, 17, 29, 9, tzinfo=UTC)


def test_suffix_follows_the_wire_format() -> None:
    """DuckDB picks its JSON reader and its gzip handling from the filename extension.

    A single JSON document named `.jsonl` is read as one malformed line, so the extension is
    load-bearing rather than cosmetic.
    """
    assert suffix_for("application/json") == ".json.gz"
    assert suffix_for("application/x-ndjson") == ".jsonl.gz"
    with pytest.raises(ValueError, match="no landing-zone suffix"):
        suffix_for("text/csv")


def test_object_path_is_partitioned_and_stamped() -> None:
    path = object_path("adsb_lol", "point/14.5/121.0/250", AT, "application/json")
    assert path.startswith("raw/adsb_lol/dt=2026-09-11/")
    assert path.endswith(".json.gz")
    assert "20260911T172909Z" in path
    assert request_hash("point/14.5/121.0/250") in path


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValueError, match="naive datetime"):
        object_path("adsb_lol", "k", datetime(2026, 9, 11, 17, 0), "application/json")  # noqa: DTZ001


def test_raw_objects_are_immutable(tmp_path: Path) -> None:
    store = LocalRawStore(tmp_path)
    store.put(
        source="adsb_lol",
        request_key="k",
        body=b"{}",
        observed_at=AT,
        content_type="application/json",
    )
    with pytest.raises(FileExistsError, match="immutable"):
        store.put(
            source="adsb_lol",
            request_key="k",
            body=b'{"different": true}',
            observed_at=AT,
            content_type="application/json",
        )


def test_stored_bytes_are_reproducible(tmp_path: Path) -> None:
    """Two stores of the same body must be byte-identical.

    gzip records an mtime by default, which would make every rerun of the pipeline produce
    different bytes for identical inputs and quietly break the reproducibility half of the
    accuracy guarantee.
    """
    first = LocalRawStore(tmp_path / "a")
    second = LocalRawStore(tmp_path / "b")
    body = b'{"hello": "world"}'
    arguments = {
        "source": "adsb_lol",
        "request_key": "k",
        "body": body,
        "observed_at": AT,
        "content_type": "application/json",
    }
    left = (tmp_path / "a" / first.put(**arguments)).read_bytes()  # type: ignore[arg-type]
    right = (tmp_path / "b" / second.put(**arguments)).read_bytes()  # type: ignore[arg-type]
    assert left == right
    assert gzip.decompress(left) == body
