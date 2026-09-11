"""The single UTC/Asia-Manila boundary (invariant 6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from nightfall.clock import PH_TZ, from_unix, isoformat_z, require_utc, to_manila, utc_now


def test_naive_datetimes_are_rejected() -> None:
    """A silent local-time assumption would shift every seasonal window the product produces."""
    with pytest.raises(ValueError, match="naive datetime"):
        require_utc(datetime(2026, 9, 11, 17, 0))  # noqa: DTZ001


def test_non_utc_datetimes_are_rejected() -> None:
    manila = datetime(2026, 9, 12, 1, 0, tzinfo=timezone(timedelta(hours=8)))
    with pytest.raises(ValueError, match="expected UTC"):
        require_utc(manila)


def test_manila_is_eight_hours_ahead() -> None:
    converted = to_manila(datetime(2026, 9, 11, 17, 0, tzinfo=UTC))
    assert converted.hour == 1
    assert converted.day == 12
    assert converted.tzinfo == PH_TZ


def test_isoformat_carries_a_literal_z() -> None:
    assert isoformat_z(datetime(2026, 9, 11, 17, 29, 9, tzinfo=UTC)) == "2026-09-11T17:29:09Z"


def test_from_unix_is_aware() -> None:
    assert from_unix(1_789_147_749.5).tzinfo == UTC


def test_utc_now_is_aware() -> None:
    assert require_utc(utc_now())
