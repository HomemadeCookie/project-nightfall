"""The immutable raw landing zone (invariant 2).

Raw objects are append-only: one object per fetch, keyed by request hash and observation
time, gzip-compressed, never edited and never deleted. Every later stage is a pure function of
this directory plus pinned code, which is what makes both reproducibility and accuracy
verification possible at all.

Two backends. `LocalRawStore` is used in development and CI. `HuggingFaceRawStore` is the
archive of record. Neither has a billing relationship (invariant 0).
"""

from __future__ import annotations

import gzip
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from nightfall.clock import require_utc


def request_hash(request_key: str) -> str:
    """Short, stable digest of a request, so identical requests are recognisable in the zone."""
    return hashlib.sha256(request_key.encode("utf-8")).hexdigest()[:12]


#: Suffix per wire format. The extension is load-bearing: DuckDB picks its JSON reader and its
#: gzip handling from the filename, so a single JSON document must not be named `.jsonl`.
SUFFIX_BY_CONTENT_TYPE = {
    "application/json": ".json.gz",
    "application/x-ndjson": ".jsonl.gz",
}


def suffix_for(content_type: str) -> str:
    try:
        return SUFFIX_BY_CONTENT_TYPE[content_type]
    except KeyError:
        raise ValueError(f"no landing-zone suffix registered for {content_type!r}") from None


def object_path(source: str, request_key: str, observed_at: datetime, content_type: str) -> str:
    """`raw/<source>/dt=<date>/<timestamp>_<hash><suffix>` — sorted, partitioned, collision-free."""
    moment = require_utc(observed_at)
    return (
        f"raw/{source}"
        f"/dt={moment:%Y-%m-%d}"
        f"/{moment:%Y%m%dT%H%M%SZ}_{request_hash(request_key)}{suffix_for(content_type)}"
    )


@runtime_checkable
class RawStore(Protocol):
    def put(
        self,
        *,
        source: str,
        request_key: str,
        body: bytes,
        observed_at: datetime,
        content_type: str,
    ) -> str:
        """Write one raw object and return its path. Must never overwrite."""


class LocalRawStore:
    """Filesystem-backed landing zone."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def put(
        self,
        *,
        source: str,
        request_key: str,
        body: bytes,
        observed_at: datetime,
        content_type: str,
    ) -> str:
        rel = object_path(source, request_key, observed_at, content_type)
        target = self._root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f"raw objects are immutable, refusing to overwrite {rel}")
        # mtime=0 keeps the gzip envelope byte-stable so reruns are reproducible.
        target.write_bytes(gzip.compress(body, mtime=0))
        return rel


class HuggingFaceRawStore:
    """Hugging Face dataset repository as the archive of record."""

    def __init__(self, repo_id: str, token: str | None = None) -> None:
        from huggingface_hub import HfApi

        self._repo_id = repo_id
        self._api = HfApi(token=token or os.environ.get("HF_TOKEN"))

    def put(
        self,
        *,
        source: str,
        request_key: str,
        body: bytes,
        observed_at: datetime,
        content_type: str,
    ) -> str:
        rel = object_path(source, request_key, observed_at, content_type)
        self._api.upload_file(
            path_or_fileobj=gzip.compress(body, mtime=0),
            path_in_repo=rel,
            repo_id=self._repo_id,
            repo_type="dataset",
            commit_message=f"collect: {source} {rel}",
        )
        return rel
