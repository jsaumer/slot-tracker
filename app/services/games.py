"""Game resolution and lookup for the entry form and stats."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.importer.normalize import normalize_name
from app.models import Bonus, Game, GameAlias
from app.services.aggregate import as_decimal
from app.services.sorting import Sort, order_by


def all_game_names(session: Session) -> list[str]:
    """Canonical names for the entry-form datalist."""
    return list(session.execute(select(Game.name).order_by(Game.name)).scalars())


def game_by_name(session: Session, name: str) -> Game | None:
    """Exact canonical-name lookup (used by the merge/alias management forms)."""
    return session.scalar(select(Game).where(Game.name == normalize_name(name)))


def merge_games(session: Session, source_id: int, target_id: int) -> Game | None:
    """Fold ``source`` into ``target``: reparent every bonus and alias, record the
    source's name as an alias of the target so future entry auto-corrects, then
    delete the source game. Returns the surviving target, or None if the merge is
    a no-op (same game, or either id missing).

    Durability note: this fixes live data *and* the entry form (via the DB
    ``game_alias`` table). It does **not** change ``app/importer/aliases.py``,
    which the importer consults independently — a full re-import would recreate
    the source spelling as a fresh game. For permanent fixes, also add the
    spelling to ``ALIAS_MAP``. See DEPLOY.md §3.
    """
    if source_id == target_id:
        return None
    source = session.get(Game, source_id)
    target = session.get(Game, target_id)
    if source is None or target is None:
        return None

    session.execute(update(Bonus).where(Bonus.game_id == source_id).values(game_id=target_id))
    session.execute(
        update(GameAlias).where(GameAlias.game_id == source_id).values(game_id=target_id)
    )

    alias_key = normalize_name(source.name)
    if alias_key != target.name:
        existing = session.get(GameAlias, alias_key)
        if existing is None:
            session.add(GameAlias(alias=alias_key, game_id=target_id))
        else:
            existing.game_id = target_id

    session.execute(delete(Game).where(Game.id == source_id))
    session.flush()
    return target


def add_alias(session: Session, alias: str, game_id: int) -> bool:
    """Teach the entry form a new spelling for a game. Idempotent — an existing
    alias is repointed at ``game_id``."""
    game = session.get(Game, game_id)
    if game is None:
        return False
    alias_key = normalize_name(alias)
    if not alias_key or alias_key == game.name:
        return False
    existing = session.get(GameAlias, alias_key)
    if existing is None:
        session.add(GameAlias(alias=alias_key, game_id=game_id))
    else:
        existing.game_id = game_id
    session.flush()
    return True


def resolve_game_id(session: Session, raw_name: str) -> int:
    """Resolve a typed game name to a game id, applying the alias table
    (typo-correction) and creating the game if it is genuinely new."""
    name = normalize_name(raw_name)
    alias = session.get(GameAlias, name)
    if alias is not None:
        return alias.game_id
    game = session.scalar(select(Game).where(Game.name == name))
    if game is None:
        game = Game(name=name)
        session.add(game)
        session.flush()
    return game.id


# Per-game aggregate expressions, defined once so the SELECT and the ORDER BY
# always agree.
_COUNT = func.count(Bonus.id)
_WON = func.coalesce(func.sum(Bonus.win), 0)
_MEAN = func.avg(Bonus.multiplier)
_BEST = func.max(Bonus.multiplier)
_WORST = func.min(Bonus.multiplier)
_FIRST = func.min(Bonus.played_on)
_LAST = func.max(Bonus.played_on)

_STAT_COLUMNS = (Game.id, Game.name, _COUNT, _WON, _MEAN, _BEST, _WORST, _FIRST, _LAST)

# Sortable columns on the games table. Whitelisted by app.services.sorting.
GAME_SORTS = {
    "game": Game.name,
    "count": _COUNT,
    "won": _WON,
    "mean": _MEAN,
    "best": _BEST,
    "worst": _WORST,
    "first": _FIRST,
    "last": _LAST,
}

DEFAULT_GAME_SORT = Sort(key="count", descending=True)


@dataclass
class GameStat:
    id: int
    name: str
    count: int
    total_win: Decimal
    mean_multiplier: Decimal | None
    best_multiplier: Decimal | None
    worst_multiplier: Decimal | None
    first_played: date | None
    last_played: date | None


@dataclass
class GamePage:
    rows: list[GameStat]
    total: int
    limit: int
    offset: int

    @property
    def has_next(self) -> bool:
        return self.offset + self.limit < self.total

    @property
    def next_offset(self) -> int:
        return self.offset + self.limit


@dataclass
class GameDetail:
    stat: GameStat
    aliases: list[str]
    top_hits: list[Bonus]
    recent: list[Bonus]


def game_stats(
    session: Session,
    *,
    q: str | None = None,
    sort: Sort | None = None,
    limit: int = 50,
    offset: int = 0,
) -> GamePage:
    """Per-game aggregates: count, total win, mean/best/worst X, first/last.

    Outer-joined, so a game with no bonuses still appears — alias targets seeded
    by the importer can exist without any bonus referencing them directly, and
    silently hiding them made the games list disagree with the game count.
    """
    sort = sort or DEFAULT_GAME_SORT
    conditions = [Game.name.ilike(f"%{q}%")] if q else []

    total = session.scalar(select(func.count()).select_from(Game).where(*conditions)) or 0

    stmt = (
        select(*_STAT_COLUMNS)
        .outerjoin(Bonus, Bonus.game_id == Game.id)
        .where(*conditions)
        .group_by(Game.id, Game.name)
        .order_by(*order_by(sort, GAME_SORTS, tiebreaker=Game.name.asc()))
        .limit(limit)
        .offset(offset)
    )
    return GamePage(
        rows=[_stat(row) for row in session.execute(stmt)],
        total=total,
        limit=limit,
        offset=offset,
    )


def game_detail(
    session: Session,
    game_id: int,
    *,
    top_n: int = 10,
    recent_n: int = 20,
) -> GameDetail | None:
    row = session.execute(
        select(*_STAT_COLUMNS)
        .outerjoin(Bonus, Bonus.game_id == Game.id)
        .where(Game.id == game_id)
        .group_by(Game.id, Game.name)
    ).one_or_none()
    if row is None:
        return None

    aliases = list(
        session.execute(
            select(GameAlias.alias).where(GameAlias.game_id == game_id).order_by(GameAlias.alias)
        ).scalars()
    )
    top_hits = list(
        session.execute(
            select(Bonus)
            .where(Bonus.game_id == game_id)
            .order_by(Bonus.multiplier.desc().nullslast(), Bonus.id.desc())
            .limit(top_n)
        ).scalars()
    )
    recent = list(
        session.execute(
            select(Bonus)
            .where(Bonus.game_id == game_id)
            .order_by(Bonus.played_on.desc().nullslast(), Bonus.id.desc())
            .limit(recent_n)
        ).scalars()
    )
    return GameDetail(stat=_stat(row), aliases=aliases, top_hits=top_hits, recent=recent)


def _stat(row: Any) -> GameStat:
    game_id, name, count, total, mean, best, worst, first, last = row
    return GameStat(
        id=game_id,
        name=name,
        count=count,
        total_win=Decimal(total),
        mean_multiplier=as_decimal(mean),
        best_multiplier=as_decimal(best),
        worst_multiplier=as_decimal(worst),
        first_played=first,
        last_played=last,
    )
