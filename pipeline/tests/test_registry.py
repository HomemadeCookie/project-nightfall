"""The source registry.

CI reads this, so it has to stay accurate: licence obligations that live only in a comment are
obligations nobody enforces.
"""

from __future__ import annotations

import pytest

from nightfall.sources import registry
from nightfall.sources.base import CommercialUse


def test_every_adapter_declares_its_obligations() -> None:
    for adapter in registry.ADAPTERS:
        assert adapter.name
        assert adapter.licence.name
        assert adapter.licence.url.startswith("https://")
        assert adapter.licence.attribution
        assert isinstance(adapter.licence.commercial_use, CommercialUse)
        assert adapter.quota.source


def test_lookup_by_name() -> None:
    assert registry.by_name("adsb_lol").name == "adsb_lol"
    with pytest.raises(KeyError, match="unknown source"):
        registry.by_name("opensky")


def test_attributions_are_generated_from_the_registry() -> None:
    """Generated rather than hand-maintained, so the credits shown to users cannot drift."""
    entries = registry.attributions()
    assert {entry["source"] for entry in entries} == {adapter.name for adapter in registry.ADAPTERS}
    assert all(entry["text"] and entry["licence"] and entry["url"] for entry in entries)


def test_only_contributing_sources_are_credited() -> None:
    """A credit for a source that supplied nothing reads as coverage that is merely empty.

    "Vessel positions © aisstream.io" under a map with no vessels on it says vessel coverage
    was collected and found nothing, when in fact it was never collected at all.
    """
    entries = registry.attributions({"adsb_lol"})
    assert [entry["source"] for entry in entries] == ["adsb_lol"]
    assert registry.attributions(set()) == []


def test_no_licence_is_breached_while_the_project_is_non_commercial() -> None:
    assert registry.COMMERCIAL_USE is False
    assert registry.commercial_use_violations() == []


def test_turning_commercial_on_would_be_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """The escape hatch for commercial use is a paid endpoint and a licensed feed, which ends
    the zero-cost guarantee. It must fail the build rather than quietly breach a licence."""
    monkeypatch.setattr(registry, "COMMERCIAL_USE", True)
    assert "aisstream" in registry.commercial_use_violations()
