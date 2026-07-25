"""Pure aggregation helpers over already-fetched bonus data.

Kept free of SQLAlchemy so exact Decimal math is unit-tested directly, without a
database. The dashboard service fetches rows and feeds them here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.bands import BANDS, LABELS, classify


@dataclass
class BandCount:
    key: str
    label: str
    count: int
    pct: Decimal


@dataclass
class YearRow:
    year: int
    count: int
    total_win: Decimal


@dataclass
class BetRow:
    bet: Decimal
    count: int
    total_win: Decimal


def as_decimal(value: object) -> Decimal | None:
    """Coerce a SQL aggregate result to Decimal.

    SQLite returns floats from AVG where PostgreSQL returns Decimal, so results
    go through ``str`` to avoid inheriting binary-float error.
    """
    if value is None:
        return None
    return Decimal(str(value))


def mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return (sum(values, Decimal(0)) / Decimal(len(values))).quantize(Decimal("0.01"))


def median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        result = ordered[mid]
    else:
        result = (ordered[mid - 1] + ordered[mid]) / Decimal(2)
    return Decimal(result).quantize(Decimal("0.01"))


def distribution(multipliers: list[Decimal]) -> list[BandCount]:
    counts = {key: 0 for key, *_ in BANDS}
    for m in multipliers:
        counts[classify(m)] += 1
    total = len(multipliers)
    out: list[BandCount] = []
    for key, _label, _lo, _hi in BANDS:
        c = counts[key]
        pct = (
            (Decimal(c) / Decimal(total) * 100).quantize(Decimal("0.1"))
            if total
            else Decimal("0.0")
        )
        out.append(BandCount(key=key, label=LABELS[key], count=c, pct=pct))
    return out


def by_year(rows: list[tuple[int, Decimal]]) -> list[YearRow]:
    """rows: (year, win). Returns newest year first."""
    agg: dict[int, list[Decimal]] = {}
    for year, win in rows:
        agg.setdefault(year, []).append(win)
    result = [
        YearRow(year=y, count=len(wins), total_win=sum(wins, Decimal(0))) for y, wins in agg.items()
    ]
    result.sort(key=lambda r: r.year, reverse=True)
    return result


def by_bet(rows: list[tuple[Decimal, Decimal]], top: int = 12) -> list[BetRow]:
    """rows: (bet, win). Returns the busiest bet sizes first."""
    agg: dict[Decimal, list[Decimal]] = {}
    for bet, win in rows:
        agg.setdefault(bet, []).append(win)
    result = [
        BetRow(bet=b, count=len(wins), total_win=sum(wins, Decimal(0))) for b, wins in agg.items()
    ]
    result.sort(key=lambda r: r.count, reverse=True)
    return result[:top]
