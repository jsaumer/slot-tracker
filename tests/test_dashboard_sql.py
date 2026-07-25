"""The SQL dashboard must agree with the pure aggregation helpers.

The helpers in ``app.services.aggregate`` are unit-tested directly and define the
intended semantics. Moving the maths into SQL risks the two drifting apart, so this
module recomputes every aggregate both ways over the same data and compares. The
helpers pin the semantics; these tests pin the SQL to them.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services import aggregate
from app.services.bonuses import create_bonus
from app.services.dashboard import build_dashboard
from tests.support import make_sessionmaker

# Deliberately awkward: repeated bets, several years, a couple of very high
# multipliers, and (added in _seed) one undated row that no dated view can include.
# Nine rows here plus the undated one gives an even total, so the even-count median
# path is exercised by default and the odd path by its own test below.
_ROWS = [
    ("Big Bass", date(2023, 1, 5), "0.10", "0.50"),
    ("Big Bass", date(2023, 2, 5), "0.10", "9.00"),
    ("Sugar Rush", date(2023, 3, 5), "0.20", "12.00"),
    ("Sugar Rush", date(2024, 1, 5), "0.20", "48.00"),
    ("Gates of Olympus", date(2024, 2, 5), "0.20", "96.00"),
    ("Gates of Olympus", date(2024, 3, 5), "1.00", "640.00"),
    ("Money Train 2", date(2025, 1, 5), "0.50", "1250.00"),
    ("Money Train 2", date(2025, 2, 5), "0.50", "25.00"),
    ("Fruitz", date(2025, 3, 5), "0.10", "310.00"),
]


def _seed(session) -> None:
    for game, played_on, bet, win in _ROWS:
        create_bonus(
            session,
            game_name=game,
            played_on=played_on,
            bet=Decimal(bet),
            win=Decimal(win),
        )
    # Undated row: contributes to all-time totals, absent from any dated view.
    create_bonus(
        session,
        game_name="Undated Game",
        played_on=None,
        bet=Decimal("0.20"),
        win=Decimal("20.00"),
    )
    session.commit()


def _pure_multipliers() -> list[Decimal]:
    return [
        (Decimal(win) / Decimal(bet)).quantize(Decimal("0.0001"))
        for _game, _played_on, bet, win in _ROWS
    ] + [(Decimal("20.00") / Decimal("0.20")).quantize(Decimal("0.0001"))]


def test_headline_aggregates_match_the_pure_helpers() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        d = build_dashboard(s)
        multipliers = _pure_multipliers()

        assert d.total_bonuses == len(multipliers)
        assert d.total_win == sum(
            (Decimal(win) for *_rest, win in _ROWS), Decimal("20.00")
        )
        assert d.mean_multiplier == aggregate.mean(multipliers)
        assert d.best_multiplier == max(multipliers)

        # Even row count: the median averages the two middle values, so an
        # off-by-one in the SQL offset would silently return one of them instead.
        assert len(multipliers) % 2 == 0
        assert d.median_multiplier == aggregate.median(multipliers)


def test_median_matches_for_an_odd_row_count() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        create_bonus(
            session=s,
            game_name="Extra",
            played_on=date(2025, 4, 1),
            bet=Decimal("0.10"),
            win=Decimal("5.00"),
        )
        s.commit()

        multipliers = [*_pure_multipliers(), Decimal("50")]
        assert len(multipliers) % 2 == 1
        assert build_dashboard(s).median_multiplier == aggregate.median(multipliers)


def test_distribution_bands_match_the_pure_helper() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        sql_bands = build_dashboard(s).distribution
        pure_bands = aggregate.distribution(_pure_multipliers())

        assert [b.key for b in sql_bands] == [b.key for b in pure_bands]
        assert [b.count for b in sql_bands] == [b.count for b in pure_bands]
        assert [b.pct for b in sql_bands] == [b.pct for b in pure_bands]
        assert sum(b.count for b in sql_bands) == len(_pure_multipliers())


def test_by_year_matches_the_pure_helper() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        sql_rows = build_dashboard(s).by_year
        pure_rows = aggregate.by_year(
            [(played_on.year, Decimal(win)) for _game, played_on, _bet, win in _ROWS]
        )
        assert [(r.year, r.count, r.total_win) for r in sql_rows] == [
            (r.year, r.count, r.total_win) for r in pure_rows
        ]


def test_by_bet_matches_the_pure_helper() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        sql_rows = build_dashboard(s).by_bet
        pure_rows = aggregate.by_bet(
            [(Decimal(bet), Decimal(win)) for _game, _played_on, bet, win in _ROWS]
            + [(Decimal("0.20"), Decimal("20.00"))]
        )
        # Same bets with the same figures; ordering is by count in both.
        assert {(r.bet, r.count, r.total_win) for r in sql_rows} == {
            (r.bet, r.count, r.total_win) for r in pure_rows
        }


def test_date_filter_narrows_and_reports_excluded_undated_rows() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)

        scoped = build_dashboard(s, date_from=date(2025, 1, 1), date_to=date(2025, 12, 31))
        assert scoped.total_bonuses == 3  # the three 2025 rows
        assert scoped.is_filtered is True
        # The undated row cannot appear in a dated view, and that is disclosed
        # rather than left to quietly explain a shortfall.
        assert scoped.undated_excluded == 1

        unfiltered = build_dashboard(s)
        assert unfiltered.is_filtered is False
        assert unfiltered.undated_excluded == 0
        assert unfiltered.total_bonuses == 10


def test_monthly_trend_is_oldest_first_and_excludes_undated() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        months = build_dashboard(s).by_month

        labels = [m.label for m in months]
        assert labels == sorted(labels)  # display order is chronological
        assert len(months) == len(_ROWS)  # one per dated row here, undated omitted
        assert sum(m.count for m in months) == len(_ROWS)


def test_empty_database_produces_no_totals_and_no_crash() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        d = build_dashboard(s)
        assert d.total_bonuses == 0
        assert d.total_win == Decimal(0)
        assert d.mean_multiplier is None
        assert d.median_multiplier is None
        assert d.best_multiplier is None
        assert all(b.count == 0 for b in d.distribution)
        assert d.by_year == [] and d.by_bet == [] and d.by_month == []
