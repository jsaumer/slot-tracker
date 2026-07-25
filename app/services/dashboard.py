"""Dashboard aggregation, computed in SQL.

This used to fetch every bonus row and aggregate in Python, which was fine at a
few hundred rows and wasteful at tens of thousands — the cost grew with the table
on every page view. The maths now happens in the database.

The pure helpers in ``app.services.aggregate`` are deliberately kept: they define
the distribution bands and are unit-tested directly, and ``tests/test_dashboard_sql.py``
asserts that these queries agree with them on seeded data. That pairing is stronger
than either alone — the helpers pin the intended semantics, the agreement test pins
the SQL to those semantics.

Portability note: the suite runs on SQLite, so nothing here may use PostgreSQL-only
constructs. Median therefore uses an ordered offset rather than ``percentile_cont``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.orm import Session

from app.models import Bonus
from app.services.aggregate import (
    BandCount,
    BetRow,
    YearRow,
    as_decimal,
)
from app.services.bands import BANDS, LABELS
from app.services.sorting import Sort

# Sortable columns on the two dashboard breakdown tables. Both are small Python
# lists, so they sort in Python.
YEAR_SORTS = {
    "year": lambda r: r.year,
    "count": lambda r: r.count,
    "won": lambda r: r.total_win,
}

BET_SORTS = {
    "bet": lambda r: r.bet,
    "count": lambda r: r.count,
    "won": lambda r: r.total_win,
}

DEFAULT_YEAR_SORT = Sort(key="year", descending=True)
DEFAULT_BET_SORT = Sort(key="count", descending=True)

# How many months of trend to show. Labelled in the UI — never silently truncated.
TREND_MONTHS = 24


@dataclass
class MonthRow:
    year: int
    month: int
    count: int
    total_win: Decimal

    @property
    def label(self) -> str:
        return f"{self.year}-{self.month:02d}"


@dataclass
class ProvenanceRow:
    """One of bought / natural / unknown. ``unknown`` is not a rounding error: it
    is every row whose provenance was never recorded, and folding it into either
    of the others would misstate the split."""

    key: str
    label: str
    count: int
    total_win: Decimal
    total_cost: Decimal | None
    mean_multiplier: Decimal | None

    @property
    def net(self) -> Decimal | None:
        """Winnings minus what was paid to trigger them. Only meaningful for
        bought bonuses, where the cost is known."""
        if self.total_cost is None:
            return None
        return self.total_win - self.total_cost


@dataclass
class Dashboard:
    total_bonuses: int
    total_win: Decimal
    mean_multiplier: Decimal | None
    median_multiplier: Decimal | None
    best_multiplier: Decimal | None
    notable_count: int
    suspect_count: int
    distribution: list[BandCount]
    by_year: list[YearRow]
    by_bet: list[BetRow]
    by_month: list[MonthRow] = field(default_factory=list)
    provenance: list[ProvenanceRow] = field(default_factory=list)
    # Rows with no date at all. They can never appear in a date-filtered view, so
    # the count is surfaced rather than letting the totals quietly disagree.
    undated_excluded: int = 0
    date_from: date | None = None
    date_to: date | None = None

    @property
    def is_filtered(self) -> bool:
        return self.date_from is not None or self.date_to is not None


def build_dashboard(
    session: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Dashboard:
    conditions: list[Any] = []
    if date_from is not None:
        conditions.append(Bonus.played_on >= date_from)
    if date_to is not None:
        conditions.append(Bonus.played_on <= date_to)

    headline = session.execute(
        select(
            func.count(Bonus.id),
            func.coalesce(func.sum(Bonus.win), 0),
            func.avg(Bonus.multiplier),
            func.max(Bonus.multiplier),
            func.coalesce(func.sum(case((Bonus.notable.is_(True), 1), else_=0)), 0),
            func.coalesce(func.sum(case((Bonus.date_suspect.is_(True), 1), else_=0)), 0),
        ).where(*conditions)
    ).one()
    count, total_win, mean_x, best_x, notable, suspect = headline

    undated = 0
    if conditions:
        undated = (
            session.scalar(
                select(func.count()).select_from(Bonus).where(Bonus.played_on.is_(None))
            )
            or 0
        )

    return Dashboard(
        total_bonuses=count,
        total_win=Decimal(total_win),
        mean_multiplier=_quantize(as_decimal(mean_x)),
        median_multiplier=_median(session, conditions),
        best_multiplier=as_decimal(best_x),
        notable_count=notable,
        suspect_count=suspect,
        distribution=_distribution(session, conditions, count),
        by_year=_by_year(session, conditions),
        by_bet=_by_bet(session, conditions),
        by_month=_by_month(session, conditions),
        provenance=_provenance(session, conditions),
        undated_excluded=undated,
        date_from=date_from,
        date_to=date_to,
    )


def _quantize(value: Decimal | None) -> Decimal | None:
    return value.quantize(Decimal("0.01")) if value is not None else None


def _scoped(stmt: Select, conditions: list[Any]) -> Select:
    return stmt.where(*conditions) if conditions else stmt


def _median(session: Session, conditions: list[Any]) -> Decimal | None:
    """Median multiplier without ``percentile_cont``, which is PostgreSQL-only and
    would break the SQLite test suite. Two cheap queries against the existing
    ``bonus_multiplier_idx``; the even-count case averages the two middle values,
    matching ``aggregate.median``."""
    scoped = [*conditions, Bonus.multiplier.is_not(None)]
    total = session.scalar(select(func.count()).select_from(Bonus).where(*scoped)) or 0
    if total == 0:
        return None

    middle = session.execute(
        select(Bonus.multiplier)
        .where(*scoped)
        .order_by(Bonus.multiplier.asc())
        .offset((total - 1) // 2)
        .limit(1 if total % 2 else 2)
    ).scalars()
    values = [as_decimal(value) for value in middle]
    if not values:
        return None
    average = sum(values, Decimal(0)) / Decimal(len(values))
    return _quantize(average)


def _distribution(session: Session, conditions: list[Any], total: int) -> list[BandCount]:
    """One row of conditional sums rather than one query per band."""
    columns = []
    for key, _label, lo, hi in BANDS:
        predicate = Bonus.multiplier >= lo
        if hi is not None:
            predicate = and_(predicate, Bonus.multiplier < hi)
        columns.append(func.coalesce(func.sum(case((predicate, 1), else_=0)), 0).label(key))

    row = session.execute(select(*columns).where(*conditions)).one()
    counts = dict(zip([key for key, *_ in BANDS], row, strict=True))

    out: list[BandCount] = []
    for key, _label, _lo, _hi in BANDS:
        band_count = int(counts[key])
        pct = (
            (Decimal(band_count) / Decimal(total) * 100).quantize(Decimal("0.1"))
            if total
            else Decimal("0.0")
        )
        out.append(BandCount(key=key, label=LABELS[key], count=band_count, pct=pct))
    return out


def _by_year(session: Session, conditions: list[Any]) -> list[YearRow]:
    year = func.extract("year", Bonus.played_on)
    rows = session.execute(
        select(year, func.count(Bonus.id), func.coalesce(func.sum(Bonus.win), 0))
        .where(*conditions, Bonus.played_on.is_not(None))
        .group_by(year)
        .order_by(year.desc())
    ).all()
    return [
        YearRow(year=int(value), count=count, total_win=Decimal(total))
        for value, count, total in rows
    ]


def _by_bet(session: Session, conditions: list[Any], top: int = 12) -> list[BetRow]:
    rows = session.execute(
        select(Bonus.bet, func.count(Bonus.id), func.coalesce(func.sum(Bonus.win), 0))
        .where(*conditions)
        .group_by(Bonus.bet)
        .order_by(func.count(Bonus.id).desc())
        .limit(top)
    ).all()
    return [BetRow(bet=bet, count=count, total_win=Decimal(total)) for bet, count, total in rows]


def _by_month(session: Session, conditions: list[Any]) -> list[MonthRow]:
    year = func.extract("year", Bonus.played_on)
    month = func.extract("month", Bonus.played_on)
    rows = session.execute(
        select(year, month, func.count(Bonus.id), func.coalesce(func.sum(Bonus.win), 0))
        .where(*conditions, Bonus.played_on.is_not(None))
        .group_by(year, month)
        .order_by(year.desc(), month.desc())
        .limit(TREND_MONTHS)
    ).all()
    # Query newest-first so the limit keeps recent months; display oldest-first.
    return [
        MonthRow(year=int(y), month=int(m), count=count, total_win=Decimal(total))
        for y, m, count, total in reversed(rows)
    ]


def _provenance(session: Session, conditions: list[Any]) -> list[ProvenanceRow]:
    rows = session.execute(
        select(
            Bonus.bought,
            func.count(Bonus.id),
            func.coalesce(func.sum(Bonus.win), 0),
            func.sum(Bonus.cost),
            func.avg(Bonus.multiplier),
        )
        .where(*conditions)
        .group_by(Bonus.bought)
    ).all()

    by_key = {
        _provenance_key(bought): (count, total_win, total_cost, mean_x)
        for bought, count, total_win, total_cost, mean_x in rows
    }
    out: list[ProvenanceRow] = []
    for key, label in (("bought", "Bought"), ("natural", "Natural"), ("unknown", "Unknown")):
        count, total_win, total_cost, mean_x = by_key.get(key, (0, 0, None, None))
        out.append(
            ProvenanceRow(
                key=key,
                label=label,
                count=count,
                total_win=Decimal(total_win),
                total_cost=as_decimal(total_cost),
                mean_multiplier=_quantize(as_decimal(mean_x)),
            )
        )
    return out


def _provenance_key(bought: bool | None) -> str:
    if bought is None:
        return "unknown"
    return "bought" if bought else "natural"
