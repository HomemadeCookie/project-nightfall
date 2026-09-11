"""Fetch the self-hosted basemap from the archive into the serving set.

The basemap is built on its own schedule (`build-basemap.yml`) because a monthly OpenStreetMap
extract has no business being rebuilt four times a day, and it is kept in the archive because
Pages offers no way to carry a large asset from one deployment to the next — every deployment
replaces the whole site.

Absence is a supported state, not an error. The app draws positions without geographic context
and says why, which is why this runs with `continue-on-error` and exits zero when there is
nothing to fetch. A missing basemap must not stop the observations from reaching the page.
"""

from __future__ import annotations

import logging
import shutil
import time

from nightfall.config import Settings

log = logging.getLogger("nightfall.basemap")

#: Where the basemap lives in the archive, and what it is called in the serving set. The
#: filename is fixed rather than content-hashed: the app requests it by name, and a basemap
#: that changes monthly does not need a cache-busting URL.
ARCHIVE_PATH = "basemap/ph.pmtiles"
SERVING_NAME = "basemap.pmtiles"


LOG_FORMAT = "%(asctime)sZ %(levelname)s %(name)s %(message)s"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    logging.Formatter.converter = time.gmtime

    settings = Settings()
    if settings.archive_repo is None:
        log.info("no archive configured; the map will draw without a basemap")
        return 0

    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import EntryNotFoundError, RepositoryNotFoundError

    try:
        downloaded = hf_hub_download(
            repo_id=settings.archive_repo,
            repo_type="dataset",
            filename=ARCHIVE_PATH,
            token=settings.hf_token.get_secret_value() if settings.hf_token else None,
        )
    except (EntryNotFoundError, RepositoryNotFoundError):
        log.warning("no basemap in %s yet; run the build-basemap workflow", settings.archive_repo)
        return 0

    settings.serving_dir.mkdir(parents=True, exist_ok=True)
    target = settings.serving_dir / SERVING_NAME
    # Copied rather than symlinked: the Pages artifact is a tarball of real files.
    shutil.copyfile(downloaded, target)
    log.info("basemap ready bytes=%d", target.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
