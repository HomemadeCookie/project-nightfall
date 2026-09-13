"""The immutable raw landing zone (invariant 2).

Raw objects are append-only: one object per fetch, keyed by request hash and observation
time, gzip-compressed, never edited and never deleted. Every later stage is a pure function of
this directory plus pinned code, which is what makes both reproducibility and accuracy
verification possible at all.

`LocalRawStore` is where collectors write. `Archive` mirrors that directory to a Hugging Face
dataset repository, which is the archive of record. Neither has a billing relationship
(invariant 0).
"""

from __future__ import annotations

import gzip
import hashlib
import os
from collections.abc import Sequence
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


class Archive:
    """Hugging Face dataset repository as the archive of record.

    Deliberately not a `RawStore`. Collectors write to the local filesystem and the archive is
    synchronised afterwards, in one commit per run, because a per-object upload would mean
    forty-odd commits for a single sampling window — a rate no free service should be asked to
    absorb, and one that makes the archive's history unreadable besides.

    The archive is the source of truth for history (invariant 2), but the read path never
    depends on reaching it (invariant 3): a run whose upload fails still publishes, and a run
    that cannot restore simply serves the window it collected itself.
    """

    def __init__(self, repo_id: str, token: str | None = None) -> None:
        from huggingface_hub import HfApi

        self._repo_id = repo_id
        self._token = token or os.environ.get("HF_TOKEN")
        self._api = HfApi(token=self._token)

    def ensure(self) -> None:
        self._api.create_repo(self._repo_id, repo_type="dataset", exist_ok=True)

    def upload(self, root: Path, *, run_id: str) -> None:
        """Add this run's raw objects to the archive in a single commit.

        Raw objects are immutable and named by content, so an upload that repeats an existing
        path is a no-op rather than an edit; nothing here can overwrite history.
        """
        self.ensure()
        self._api.upload_folder(
            repo_id=self._repo_id,
            repo_type="dataset",
            folder_path=str(root),
            path_in_repo="raw",
            allow_patterns=["**/*.gz"],
            commit_message=f"collect: run {run_id}",
        )

    def restore(self, root: Path, *, dates: Sequence[str]) -> Path:
        """Fetch the raw partitions for the given `YYYY-MM-DD` dates into `root`.

        Only the partitions the transform will actually read, because the archive grows
        without bound and the runner disk does not.
        """
        from huggingface_hub import snapshot_download

        root.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=self._repo_id,
            repo_type="dataset",
            token=self._token,
            local_dir=str(root),
            allow_patterns=[f"raw/*/dt={date}/*" for date in dates],
        )
        return root
