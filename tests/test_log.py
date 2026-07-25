"""Log querying: the new filters, the filtered summary, and sort behaviour."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.bonuses import create_bonus, query_log
from app.services.sorting import Sort
from tests.support import make_sessionmaker


def _seed(session) -> None:
    create_bonus(
        session,
        game_name="Big Bass",
        played_on=date(2024, 1, 1),
        bet=Decimal("0.20"),
        win=Decimal("10.00"),
        notes="early tease",
    )
    create_bonus(
        session,
        game_name="Sugar Rush",
        played_on=date(2024, 2, 1),
        bet=Decimal("0.20"),
        win=Decimal("100.00"),
        notable=True,
        replay_url="https://example.test/replay/1",
    )
    suspect = create_bonus(
        session,
        game_name="Gates of Olympus",
        played_on=date(2024, 3, 1),
        bet=Decimal("1.00"),
        win=Decimal("50.00"),
        notes="retrigger city",
    )
    suspect.date_suspect = True
    session.commit()


def _games(page) -> list[str]:
    return [row.game_name for row in page.rows]


def test_search_matches_game_name() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        assert _games(query_log(s, q="bass")) == ["Big Bass"]


def test_search_also_matches_notes() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        # "retrigger" appears only in a notes field, never in a game name.
        assert _games(query_log(s, q="retrigger")) == ["Gates of Olympus"]


def test_notable_replay_and_suspect_filters() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        assert _games(query_log(s, notable=True)) == ["Sugar Rush"]
        assert _games(query_log(s, has_replay=True)) == ["Sugar Rush"]
        assert _games(query_log(s, suspect=True)) == ["Gates of Olympus"]


def test_summary_aggregates_the_whole_filtered_set() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)

        unfiltered = query_log(s).summary
        assert unfiltered.count == 3
        assert unfiltered.total_win == Decimal("160.00")
        assert unfiltered.best_multiplier == Decimal("500")  # 100.00 / 0.20

        # Summary follows the filter, not the page.
        filtered = query_log(s, notable=True).summary
        assert filtered.count == 1
        assert filtered.total_win == Decimal("100.00")


def test_summary_is_empty_safe() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        summary = query_log(s, q="no-such-game").summary
        assert summary.count == 0
        assert summary.total_win == Decimal(0)
        assert summary.mean_multiplier is None
        assert summary.best_multiplier is None


def test_sort_by_win_both_directions() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        ascending = query_log(s, sort=Sort("win", descending=False))
        assert [r.bonus.win for r in ascending.rows] == [
            Decimal("10.00"),
            Decimal("50.00"),
            Decimal("100.00"),
        ]
        descending = query_log(s, sort=Sort("win", descending=True))
        assert [r.bonus.win for r in descending.rows] == [
            Decimal("100.00"),
            Decimal("50.00"),
            Decimal("10.00"),
        ]


def test_pagination_is_stable_when_sort_values_tie() -> None:
    """Every sort appends `id` as a tiebreaker. Without it, paging over rows that
    share a sort value can repeat or skip rows."""
    Session = make_sessionmaker()
    with Session() as s:
        for _ in range(6):
            create_bonus(
                session=s,
                game_name="Same Game",
                played_on=date(2024, 5, 1),  # identical date for every row
                bet=Decimal("0.20"),
                win=Decimal("5.00"),
            )
        s.commit()

        seen: list[int] = []
        for offset in (0, 2, 4):
            page = query_log(s, sort=Sort("date", descending=True), limit=2, offset=offset)
            seen.extend(r.bonus.id for r in page.rows)

        assert len(seen) == 6
        assert len(set(seen)) == 6  # no duplicates across pages
