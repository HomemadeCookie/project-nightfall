"""Licence flags that travel with every record and gate what may be published."""

from __future__ import annotations

from enum import StrEnum


class License(StrEnum):
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    ATTRIBUTION = "ATTRIBUTION"  # needs credit (CC BY, ODbL, ...)
    SHARE_ALIKE = "SHARE_ALIKE"  # derived databases must be shared under the same terms
    UNCLEAR = "UNCLEAR"  # terms not verified for commercial use; blocks publishing
    NON_COMMERCIAL = "NON_COMMERCIAL"  # research only; blocks publishing


BLOCKING: frozenset[License] = frozenset({License.NON_COMMERCIAL, License.UNCLEAR})


def blocking(licenses: set[License] | frozenset[License] | list[License]) -> set[License]:
    """Licences in ``licenses`` that forbid commercial publication."""
    return {License(x) for x in licenses} & BLOCKING


def merge(*groups: list[License] | set[License] | frozenset[License]) -> list[License]:
    """Union of licence sets, in stable order. Lineage uses this to propagate licences."""
    seen: set[License] = set()
    for g in groups:
        seen.update(License(x) for x in g)
    return sorted(seen, key=lambda x: x.value)
