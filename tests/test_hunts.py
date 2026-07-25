"""Hunt cost / net / ROI formulas (docs/build-brief.md)."""

from __future__ import annotations

from decimal import Decimal

from app.services.hunts import hunt_result


def test_after_opening_basic() -> None:
    r = hunt_result(
        start_balance=Decimal("100.00"),
        end_balance=Decimal("80.00"),
        end_convention="after_opening",
        total_bonus_win=Decimal("500.00"),  # ignored by this convention
    )
    assert r.cost == Decimal("100.00")
    assert r.net == Decimal("-20.00")
    assert r.roi == Decimal("-0.2000")


def test_spin_end_basic() -> None:
    r = hunt_result(
        start_balance=Decimal("100.00"),
        end_balance=Decimal("40.00"),
        end_convention="spin_end",
        total_bonus_win=Decimal("50.00"),
    )
    assert r.cost == Decimal("60.00")  # start - end
    assert r.net == Decimal("-10.00")  # total_win - cost
    assert r.roi == Decimal("-0.1667")


def test_after_opening_missing_end_gives_no_net() -> None:
    r = hunt_result(
        start_balance=Decimal("100.00"),
        end_balance=None,
        end_convention="after_opening",
        total_bonus_win=Decimal("0"),
    )
    assert r.cost == Decimal("100.00")
    assert r.net is None
    assert r.roi is None


def test_spin_end_missing_end_gives_no_cost() -> None:
    r = hunt_result(
        start_balance=Decimal("100.00"),
        end_balance=None,
        end_convention="spin_end",
        total_bonus_win=Decimal("50.00"),
    )
    assert r.cost is None
    assert r.net is None


def test_zero_cost_roi_is_none() -> None:
    r = hunt_result(
        start_balance=Decimal("0.00"),
        end_balance=Decimal("0.00"),
        end_convention="after_opening",
        total_bonus_win=Decimal("0"),
    )
    assert r.cost == Decimal("0.00")
    assert r.net == Decimal("0.00")
    assert r.roi is None  # no division by zero


def test_profitable_hunt() -> None:
    r = hunt_result(
        start_balance=Decimal("200.00"),
        end_balance=Decimal("250.00"),
        end_convention="after_opening",
        total_bonus_win=Decimal("0"),
    )
    assert r.net == Decimal("50.00")
    assert r.roi == Decimal("0.2500")
