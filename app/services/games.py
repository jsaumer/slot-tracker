"""Game resolution and lookup for the entry form and stats."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher, get_close_matches
from itertools import combinations
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import Bonus, Game, GameAlias
from app.services.aggregate import as_decimal
from app.services.naming import normalize_name
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


# --------------------------------------------------------------------------- #
# duplicate detection
# --------------------------------------------------------------------------- #
# Everything that isn't alphanumeric, for the "same after aggressive
# normalization" tier: "Stack'Em"/"Stack'em" and "Hop'n'Pop"/"Hop 'n' Pop" all
# collapse to one fingerprint.
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# A trailing sequel marker: "Money Train 2", "Chaos Crew II", "xWays Hoarder 2".
_TRAILING_ORDINAL = re.compile(r"^(.*?)\s*(\d+|i{1,3}|iv|vi{0,3}|ix|x)$", re.IGNORECASE)

_ROMAN = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
    "x": 10,
}


@dataclass
class GameRef:
    id: int
    name: str
    count: int


@dataclass
class MergeSuggestion:
    """A candidate duplicate pair. ``source`` is the proposed casualty and
    ``target`` the proposed survivor, defaulting to whichever has more bonuses —
    but the caller can swap them, because the more common spelling is not always
    the correct one."""

    source: GameRef
    target: GameRef
    similarity: Decimal
    certain: bool


def _fingerprint(name: str) -> str:
    return _NON_ALNUM.sub("", name.lower())


def _ordinal_value(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return _ROMAN.get(token.lower())


def _split_ordinal(name: str) -> tuple[str, int] | None:
    """Split "Money Train 2" into ("money train", 2). Roman numerals resolve to
    the same value as their arabic form, so "Chaos Crew II" and "Chaos Crew 2"
    are recognized as the *same* entry rather than different sequels."""
    match = _TRAILING_ORDINAL.match(name.strip())
    if match is None:
        return None
    stem, token = match.group(1).strip(), match.group(2)
    value = _ordinal_value(token)
    if not stem or value is None:
        return None
    return stem.lower(), value


def are_distinct_sequels(a: str, b: str) -> bool:
    """True when two similar names are different entries in a series.

    This guard is the difference between a useful tool and a destructive one:
    "Money Train 2" and "Money Train 3" are ~0.95 similar but are separate games,
    and the build brief is explicit that sequels stay distinct. Also catches a base
    game against its own sequel ("Big Bass" vs "Big Bass 2").
    """
    left, right = _split_ordinal(a), _split_ordinal(b)
    if left and right:
        # Same series, different number -> distinct. Same number (e.g. 2 vs II)
        # -> not distinct, so it can still be offered as a duplicate.
        return left[0] == right[0] and left[1] != right[1]
    if left:
        return left[0] == b.strip().lower()
    if right:
        return right[0] == a.strip().lower()
    return False


def suggest_merges(
    session: Session,
    *,
    threshold: float = 0.87,
    limit: int = 50,
) -> list[MergeSuggestion]:
    """Find likely duplicate games, so the merge tool is usable without eyeballing
    hundreds of names.

    Two tiers: names identical once punctuation, case and spacing are stripped
    (certain), and names above a similarity threshold (likely). Sequels are
    excluded from both — see ``are_distinct_sequels``.
    """
    rows = session.execute(
        select(Game.id, Game.name, func.count(Bonus.id))
        .outerjoin(Bonus, Bonus.game_id == Game.id)
        .group_by(Game.id, Game.name)
    ).all()
    refs = {name: GameRef(id=game_id, name=name, count=count) for game_id, name, count in rows}
    names = sorted(refs)

    seen: set[tuple[str, str]] = set()
    certain: list[MergeSuggestion] = []
    likely: list[MergeSuggestion] = []

    def add(bucket: list[MergeSuggestion], a: str, b: str, similarity: float, is_certain: bool):
        pair = (a, b) if a < b else (b, a)
        if pair in seen or are_distinct_sequels(a, b):
            return
        seen.add(pair)
        first, second = refs[a], refs[b]
        # Higher bonus count survives by default.
        target, source = (first, second) if first.count >= second.count else (second, first)
        bucket.append(
            MergeSuggestion(
                source=source,
                target=target,
                similarity=Decimal(str(round(similarity, 3))),
                certain=is_certain,
            )
        )

    by_fingerprint: dict[str, list[str]] = {}
    for name in names:
        by_fingerprint.setdefault(_fingerprint(name), []).append(name)
    for group in by_fingerprint.values():
        for a, b in combinations(group, 2):
            add(certain, a, b, 1.0, True)

    for name in names:
        others = [other for other in names if other != name]
        for match in get_close_matches(name, others, n=5, cutoff=threshold):
            add(likely, name, match, SequenceMatcher(None, name, match).ratio(), False)

    certain.sort(key=lambda s: -(s.source.count + s.target.count))
    likely.sort(key=lambda s: (-s.similarity, -(s.source.count + s.target.count)))
    return (certain + likely)[:limit]


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
