"""Bonus creation and the searchable/filterable log query."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Bonus, Game
from app.services.aggregate import as_decimal
from app.services.bands import band_bounds
from app.services.games import resolve_game_id
from app.services.sorting import Sort, order_by


def last_bet(session: Session) -> Decimal | None:
    """Most recently used bet, to default the entry form."""
    return session.scalar(select(Bonus.bet).order_by(Bonus.id.desc()).limit(1))


def get_bonus(session: Session, bonus_id: int) -> Bonus | None:
    return session.get(Bonus, bonus_id)


def update_bonus(
    session: Session,
    bonus_id: int,
    *,
    game_name: str,
    played_on: date | None,
    bet: Decimal,
    win: Decimal,
    notes: str | None = None,
    replay_url: str | None = None,
    notable: bool = False,
) -> Bonus | None:
    """Edit an existing bonus. ``multiplier`` is a generated column — never set
    here; it recomputes from win/bet on flush. Game name is re-resolved through
    the alias table, exactly as on entry, so a corrected spelling still lands on
    the right game.

    Note: editing a row imported from a workbook (``import_ref`` non-null) would be
    overwritten by a re-import, which rewrites game/date/bet/win/notes/replay/notable
    from the source. App-entered rows (``import_ref`` NULL) are never touched.
    """
    bonus = session.get(Bonus, bonus_id)
    if bonus is None:
        return None
    bonus.game_id = resolve_game_id(session, game_name)
    bonus.played_on = played_on
    bonus.bet = bet
    bonus.win = win
    bonus.notes = notes or None
    bonus.replay_url = replay_url or None
    bonus.notable = notable
    session.flush()
    session.refresh(bonus)  # repopulate the generated multiplier
    return bonus


def delete_bonus(session: Session, bonus_id: int) -> bool:
    bonus = session.get(Bonus, bonus_id)
    if bonus is None:
        return False
    session.delete(bonus)
    session.flush()
    return True


def create_bonus(
    session: Session,
    *,
    game_name: str,
    played_on: date,
    bet: Decimal,
    win: Decimal,
    notes: str | None = None,
    replay_url: str | None = None,
    notable: bool = False,
    hunt_id: int | None = None,
    session_id: int | None = None,
) -> Bonus:
    bonus = Bonus(
        game_id=resolve_game_id(session, game_name),
        played_on=played_on,
        bet=bet,
        win=win,
        notes=notes or None,
        replay_url=replay_url or None,
        notable=notable,
        hunt_id=hunt_id,
        session_id=session_id,
    )
    session.add(bonus)
    session.flush()
    # Refresh so the generated multiplier is populated for immediate display.
    session.refresh(bonus)
    return bonus


# Sortable log columns. Keys are public — they appear in URLs — and whitelisted
# by app.services.sorting so a hand-edited ?sort= can never reach ORDER BY.
LOG_SORTS = {
    "date": Bonus.played_on,
    "game": Game.name,
    "bet": Bonus.bet,
    "win": Bonus.win,
    "x": Bonus.multiplier,
    "notes": Bonus.notes,
}

DEFAULT_LOG_SORT = Sort(key="date", descending=True)

# Python-side sorts for already-fetched ``(Bonus, game_name)`` rows — the hunt-detail
# and session-detail tables. Small result sets, so no need to push into SQL.
BONUS_ROW_SORTS = {
    "date": lambda row: row[0].played_on,
    "game": lambda row: row[1].lower(),
    "bet": lambda row: row[0].bet,
    "win": lambda row: row[0].win,
    "x": lambda row: row[0].multiplier,
}

DEFAULT_BONUS_ROW_SORT = Sort(key="date", descending=True)


@dataclass(frozen=True)
class LogFilters:
    """Parsed log filters, shared by the log view and the CSV export so both
    always narrow the data the same way. Routers parse raw query strings into
    this; services only ever see typed values."""

    q: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    bet: Decimal | None = None
    band: str | None = None
    notable: bool = False
    suspect: bool = False
    has_replay: bool = False


@dataclass
class LogRow:
    bonus: Bonus
    game_name: str


@dataclass
class LogSummary:
    """Aggregates over the whole filtered set, not just the visible page."""

    count: int
    total_win: Decimal
    mean_multiplier: Decimal | None
    best_multiplier: Decimal | None


@dataclass
class LogPage:
    rows: list[LogRow]
    summary: LogSummary
    limit: int
    offset: int

    @property
    def total(self) -> int:
        return self.summary.count

    @property
    def has_next(self) -> bool:
        return self.offset + self.limit < self.total

    @property
    def next_offset(self) -> int:
        return self.offset + self.limit


def query_log(
    session: Session,
    *,
    filters: LogFilters | None = None,
    sort: Sort | None = None,
    limit: int = 50,
    offset: int = 0,
) -> LogPage:
    filters = filters or LogFilters()
    sort = sort or DEFAULT_LOG_SORT
    conditions = log_conditions(filters)

    rows_stmt = (
        select(Bonus, Game.name)
        .join(Game, Bonus.game_id == Game.id)
        .where(*conditions)
        .order_by(*order_by(sort, LOG_SORTS, tiebreaker=Bonus.id.desc()))
        .limit(limit)
        .offset(offset)
    )
    rows = [LogRow(bonus=b, game_name=name) for b, name in session.execute(rows_stmt)]

    count, total_win, mean_x, best_x = session.execute(
        select(
            func.count(Bonus.id),
            func.coalesce(func.sum(Bonus.win), 0),
            func.avg(Bonus.multiplier),
            func.max(Bonus.multiplier),
        )
        .select_from(Bonus)
        .join(Game, Bonus.game_id == Game.id)
        .where(*conditions)
    ).one()

    return LogPage(
        rows=rows,
        summary=LogSummary(
            count=count,
            total_win=Decimal(total_win),
            mean_multiplier=as_decimal(mean_x),
            best_multiplier=as_decimal(best_x),
        ),
        limit=limit,
        offset=offset,
    )


def log_conditions(filters: LogFilters) -> list[Any]:
    """WHERE clauses for a set of log filters. Public because the CSV export
    reuses it — an export that ignored the active filters would contradict the
    UI it sits in."""
    conditions: list[Any] = []
    if filters.q:
        # Search game name *and* notes — thousands of imported rows carry notes
        # that are otherwise only visible on the edit form.
        pattern = f"%{filters.q}%"
        conditions.append(or_(Game.name.ilike(pattern), Bonus.notes.ilike(pattern)))
    if filters.date_from is not None:
        conditions.append(Bonus.played_on >= filters.date_from)
    if filters.date_to is not None:
        conditions.append(Bonus.played_on <= filters.date_to)
    if filters.bet is not None:
        conditions.append(Bonus.bet == filters.bet)
    if filters.band:
        bounds = band_bounds(filters.band)
        if bounds is not None:
            lo, hi = bounds
            conditions.append(Bonus.multiplier >= lo)
            if hi is not None:
                conditions.append(Bonus.multiplier < hi)
    if filters.notable:
        conditions.append(Bonus.notable.is_(True))
    if filters.suspect:
        conditions.append(Bonus.date_suspect.is_(True))
    if filters.has_replay:
        conditions.append(Bonus.replay_url.is_not(None))
    return conditions
