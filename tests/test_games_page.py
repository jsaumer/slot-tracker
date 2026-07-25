"""Games listing: search, sort, pagination, and the per-game detail."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models import Game, GameAlias
from app.services.bonuses import create_bonus
from app.services.games import game_by_name, game_detail, game_stats
from app.services.sorting import Sort
from tests.support import make_sessionmaker


def _seed(session) -> None:
    # Big Bass: 2 bonuses. Sugar Rush: 1. Orphan Game: none at all.
    create_bonus(
        session,
        game_name="Big Bass",
        played_on=date(2024, 1, 1),
        bet=Decimal("0.20"),
        win=Decimal("10.00"),
    )
    create_bonus(
        session,
        game_name="Big Bass",
        played_on=date(2024, 3, 1),
        bet=Decimal("0.20"),
        win=Decimal("100.00"),
    )
    create_bonus(
        session,
        game_name="Sugar Rush",
        played_on=date(2024, 2, 1),
        bet=Decimal("0.50"),
        win=Decimal("25.00"),
    )
    session.add(Game(name="Orphan Game"))
    session.commit()


def _names(page) -> list[str]:
    return [row.name for row in page.rows]


def test_lists_games_with_no_bonuses() -> None:
    """Outer-joined: an alias target seeded without bonuses must still appear, or
    the games list silently disagrees with the game count."""
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        page = game_stats(s)
        assert page.total == 3
        assert "Orphan Game" in _names(page)
        orphan = next(r for r in page.rows if r.name == "Orphan Game")
        assert orphan.count == 0
        assert orphan.total_win == Decimal(0)
        assert orphan.mean_multiplier is None


def test_search_narrows_rows_and_total() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        page = game_stats(s, q="bass")
        assert page.total == 1
        assert _names(page) == ["Big Bass"]


def test_sort_by_count_and_by_name() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        by_count = game_stats(s, sort=Sort("count", descending=True))
        assert _names(by_count)[0] == "Big Bass"  # 2 bonuses

        ascending = game_stats(s, sort=Sort("game", descending=False))
        assert _names(ascending) == ["Big Bass", "Orphan Game", "Sugar Rush"]


def test_sort_by_aggregate_puts_null_means_last() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        page = game_stats(s, sort=Sort("mean", descending=True))
        # Orphan Game has no multiplier at all; nulls sort last either way.
        assert _names(page)[-1] == "Orphan Game"


def test_pagination_splits_and_reports_total() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        first = game_stats(s, sort=Sort("game", descending=False), limit=2, offset=0)
        assert _names(first) == ["Big Bass", "Orphan Game"]
        assert first.total == 3
        assert first.has_next is True

        second = game_stats(s, sort=Sort("game", descending=False), limit=2, offset=2)
        assert _names(second) == ["Sugar Rush"]
        assert second.has_next is False


def test_game_detail_reports_stats_aliases_and_hits() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        game = game_by_name(s, "Big Bass")
        assert game is not None
        s.add(GameAlias(alias="Bigg Bass", game_id=game.id))
        s.commit()

        detail = game_detail(s, game.id)
        assert detail is not None
        assert detail.stat.name == "Big Bass"
        assert detail.stat.count == 2
        assert detail.stat.total_win == Decimal("110.00")
        assert detail.aliases == ["Bigg Bass"]
        # Best hit first: 100.00 / 0.20 = 500x beats 10.00 / 0.20 = 50x.
        assert detail.top_hits[0].win == Decimal("100.00")
        # Recent is newest-first by played_on.
        assert detail.recent[0].played_on == date(2024, 3, 1)


def test_game_detail_missing_id_is_none() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        assert game_detail(s, 9999) is None
