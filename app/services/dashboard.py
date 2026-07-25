"""Dashboard aggregation. Fetches a lean projection and delegates the math to
the pure helpers in app.services.aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Bonus
from app.services.aggregate import (
    BandCount,
    BetRow,
    YearRow,
    by_bet,
    by_year,
    distribution,
    mean,
    median,
)
from app.services.sorting import Sort

# Sortable columns on the two dashboard breakdown tables. Both are small Python
# lists produced by the pure aggregate helpers, so they sort in Python.
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


def build_dashboard(session: Session) -> Dashboard:
    rows = session.execute(select(Bonus.played_on, Bonus.bet, Bonus.win, Bonus.multiplier)).all()

    multipliers = [Decimal(str(r.multiplier)) for r in rows if r.multiplier is not None]
    total_win = sum((r.win for r in rows), Decimal(0))

    notable_count = session.scalar(
        select(func.count()).select_from(Bonus).where(Bonus.notable.is_(True))
    )
    suspect_count = session.scalar(
        select(func.count()).select_from(Bonus).where(Bonus.date_suspect.is_(True))
    )

    return Dashboard(
        total_bonuses=len(rows),
        total_win=total_win,
        mean_multiplier=mean(multipliers),
        median_multiplier=median(multipliers),
        best_multiplier=max(multipliers) if multipliers else None,
        notable_count=notable_count or 0,
        suspect_count=suspect_count or 0,
        distribution=distribution(multipliers),
        by_year=by_year([(r.played_on.year, r.win) for r in rows if r.played_on]),
        by_bet=by_bet([(r.bet, r.win) for r in rows]),
    )
