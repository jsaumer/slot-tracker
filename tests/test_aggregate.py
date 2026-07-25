"""Dashboard aggregation helpers."""

from __future__ import annotations

from decimal import Decimal

from app.services.aggregate import by_bet, by_year, distribution, mean, median


def test_mean() -> None:
    assert mean([]) is None
    assert mean([Decimal(10), Decimal(20), Decimal(30)]) == Decimal("20.00")


def test_median_odd_even_empty() -> None:
    assert median([]) is None
    assert median([Decimal(3), Decimal(1), Decimal(2)]) == Decimal("2.00")
    assert median([Decimal(1), Decimal(2), Decimal(3), Decimal(4)]) == Decimal("2.50")


def test_distribution_bands_and_pct() -> None:
    mults = [
        Decimal("5"),  # <10
        Decimal("10"),  # 10-50 (lower bound inclusive)
        Decimal("48"),  # 10-50
        Decimal("50"),  # 50-100
        Decimal("120"),  # 100-500
        Decimal("600"),  # 500-1000
        Decimal("1500"),  # 1000+
        Decimal("12625"),  # 1000+
    ]
    dist = {b.key: b for b in distribution(mults)}
    assert dist["u10"].count == 1
    assert dist["10_50"].count == 2
    assert dist["50_100"].count == 1
    assert dist["100_500"].count == 1
    assert dist["500_1000"].count == 1
    assert dist["o1000"].count == 2
    # Percentages sum to 100 across the eight values.
    assert sum(b.count for b in distribution(mults)) == 8
    assert dist["10_50"].pct == Decimal("25.0")


def test_distribution_empty() -> None:
    dist = distribution([])
    assert all(b.count == 0 and b.pct == Decimal("0.0") for b in dist)


def test_by_year() -> None:
    rows = [
        (2023, Decimal("10.00")),
        (2023, Decimal("5.00")),
        (2024, Decimal("20.00")),
    ]
    result = by_year(rows)
    assert [r.year for r in result] == [2024, 2023]  # newest first
    assert result[1].count == 2
    assert result[1].total_win == Decimal("15.00")


def test_by_bet_sorted_by_count() -> None:
    rows = [
        (Decimal("0.10"), Decimal("1")),
        (Decimal("0.10"), Decimal("2")),
        (Decimal("0.20"), Decimal("3")),
    ]
    result = by_bet(rows)
    assert result[0].bet == Decimal("0.10")  # busiest first
    assert result[0].count == 2
    assert result[0].total_win == Decimal("3")
