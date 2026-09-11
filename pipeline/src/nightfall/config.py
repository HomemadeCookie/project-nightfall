"""Validated settings.

Nothing in this package reads `os.environ` directly except the credential lookups an adapter
owns. Paths, repository ids, and window lengths come from here so that a job running in GitHub
Actions and a developer running locally differ only in environment, never in code.

Upstream hostnames deliberately do *not* live here: each source's API root belongs to its one
adapter module, which owns that source's schema (`.cursorrules` § 5).
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Schema version stamped into curated Parquet and the serving manifest. Bump this whenever a
#: column changes meaning, so an old artifact can never be read as if it were a new one.
SCHEMA_VERSION = 1


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NIGHTFALL_",
        extra="ignore",
        # No env_file: a committed .env is forbidden, so reading one would only ever pick up a
        # file that should not exist.
        env_file=None,
    )

    #: Root of the local working tree for data. `raw/`, `curated/`, and `serving/` hang off it.
    #: Never committed; see .gitignore.
    data_root: Path = Path("build")

    #: Hugging Face dataset repository holding the archive of record. Unset means local-only,
    #: which is the correct default for tests and for a developer machine.
    archive_repo: str | None = None

    hf_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("NIGHTFALL_HF_TOKEN", "HF_TOKEN"),
    )

    aisstream_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("NIGHTFALL_AISSTREAM_API_KEY", "AISSTREAM_API_KEY"),
    )

    #: Length of one AIS sampling window. Bounded by construction: there is no persistent
    #: consumer, so this is a sample and everything downstream treats it as one.
    ais_window_s: float = Field(default=180.0, gt=0.0, le=1800.0)

    #: Length of one ADS-B sampling window, and how often the coverage circles are swept
    #: inside it. The sweep cadence is what decides whether consecutive fixes may be joined
    #: into a track at all, so it is configuration rather than a constant.
    adsb_window_s: float = Field(default=180.0, gt=0.0, le=1800.0)
    adsb_sweep_interval_s: float = Field(default=20.0, gt=0.0, le=600.0)

    #: Identifies the pipeline run in provenance fields (invariant 7). Defaults to the Actions
    #: run id when present so an artifact can be traced back to its job.
    run_id: str = Field(
        default_factory=lambda: os.environ.get("GITHUB_RUN_ID") or "local",
    )

    #: Where a provider should write if this project's traffic is a problem for them.
    #:
    #: Not decoration: adsb.lol rejects a generic User-Agent outright, and every one of these
    #: sources is a free service absorbing our requests. Defaulting to the repository means a
    #: fork identifies itself as itself, so a misbehaving fork cannot cost the original its
    #: access.
    contact: str = Field(
        default_factory=lambda: (
            f"https://github.com/{os.environ['GITHUB_REPOSITORY']}"
            if os.environ.get("GITHUB_REPOSITORY")
            else "https://github.com/HomemadeCookie/project-nightfall"
        )
    )

    @property
    def user_agent(self) -> str:
        """The identity every outbound request carries."""
        return f"project-nightfall/{SCHEMA_VERSION}.0 (+{self.contact})"

    @property
    def raw_root(self) -> Path:
        return self.data_root

    @property
    def curated_dir(self) -> Path:
        return self.data_root / "curated"

    @property
    def serving_dir(self) -> Path:
        return self.data_root / "serving"

    @property
    def health_path(self) -> Path:
        return self.serving_dir / "pipeline_health.json"

    @property
    def manifest_path(self) -> Path:
        return self.serving_dir / "manifest.json"
