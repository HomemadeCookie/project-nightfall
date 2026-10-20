"""Registry of source adapters, keyed by name."""

from __future__ import annotations

from nightfall.sources.base import Source

_REGISTRY: dict[str, type[Source]] = {}


def register(cls: type[Source]) -> type[Source]:
    if cls.name in _REGISTRY:
        raise ValueError(f"duplicate source {cls.name!r}")
    _REGISTRY[cls.name] = cls
    return cls


def all_sources() -> dict[str, type[Source]]:
    _load()
    return dict(_REGISTRY)


def get(name: str) -> type[Source]:
    _load()
    return _REGISTRY[name]


def _load() -> None:
    # Importing the modules runs their @register decorators.
    from nightfall.sources.flights import adsb_lol  # noqa: F401
    from nightfall.sources.markets import da_prices, eia, frankfurter, worldbank  # noqa: F401
    from nightfall.sources.satellite import planetary_stac  # noqa: F401
    from nightfall.sources.ships import aisstream, portwatch  # noqa: F401
    from nightfall.sources.text import gdelt, rss  # noqa: F401
    from nightfall.sources.weather import gdacs, ibtracs, noaa_gfs, open_meteo  # noqa: F401
