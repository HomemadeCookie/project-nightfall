"""The source registry.

Single place that knows which sources exist. Two things read it: the CLI, to dispatch a
collector, and the bake stage, to generate UI attribution from licence metadata so the
credits shown to users cannot drift out of date (README § Risks, licence terms).
"""

from __future__ import annotations

from collections.abc import Collection

from nightfall.sources.adsb_lol import AdsbLolAdapter
from nightfall.sources.aisstream import AisStreamAdapter
from nightfall.sources.base import CommercialUse, Licence, SourceAdapter, SourceFamily
from nightfall.sources.boc_tdp import BocTdpAdapter
from nightfall.sources.ppa import PpaAdapter
from nightfall.sources.psa_imts import PsaImtsAdapter
from nightfall.sources.un_comtrade import UnComtradeAdapter

ADAPTERS: tuple[type[SourceAdapter], ...] = (
    AdsbLolAdapter,
    AisStreamAdapter,
    BocTdpAdapter,
    PpaAdapter,
    PsaImtsAdapter,
    UnComtradeAdapter,
)


def mobility_adapters() -> tuple[type[SourceAdapter], ...]:
    """Adapters that feed the map overlay. Statistics sources are collected separately."""
    return tuple(adapter for adapter in ADAPTERS if adapter.family is SourceFamily.MOBILITY)


#: The project is non-commercial today (README § Risks). Flipping this to True must be a
#: deliberate decision: it would also end the $0.00 guarantee, because the commercial escape
#: hatch is a paid weather endpoint and a licensed AIS feed.
COMMERCIAL_USE = False


def by_name(name: str) -> type[SourceAdapter]:
    for adapter in ADAPTERS:
        if adapter.name == name:
            return adapter
    known = ", ".join(sorted(a.name for a in ADAPTERS))
    raise KeyError(f"unknown source {name!r}; known sources: {known}")


def licences() -> dict[str, Licence]:
    return {adapter.name: adapter.licence for adapter in ADAPTERS}


def attributions(sources: Collection[str] | None = None) -> list[dict[str, str]]:
    """Attribution entries for the UI, derived from the registry rather than hand-maintained.

    Restricted to the sources that actually contributed to the build being credited. Crediting
    a source that supplied nothing is not merely redundant: "Vessel positions © aisstream.io"
    printed under a map with no vessels on it tells the reader that vessel coverage is being
    shown and is empty, when in fact it was never collected.

    Membership is decided by the served data, not by the collectors' current health, because a
    source that failed this cycle may still be the origin of rows within the window.
    """
    return [
        {
            "source": adapter.name,
            "licence": adapter.licence.name,
            "url": adapter.licence.url,
            "text": adapter.licence.attribution,
        }
        for adapter in sorted(ADAPTERS, key=lambda a: a.name)
        if sources is None or adapter.name in sources
    ]


def commercial_use_violations() -> list[str]:
    """Sources whose licence forbids the current commercial-use posture.

    Returns an empty list while the project is non-commercial. CI asserts it stays empty, so
    turning `COMMERCIAL_USE` on without swapping the offending sources fails the build instead
    of quietly breaching a licence.
    """
    if not COMMERCIAL_USE:
        return []
    return [
        adapter.name
        for adapter in ADAPTERS
        if adapter.licence.commercial_use is CommercialUse.PROHIBITED
    ]
