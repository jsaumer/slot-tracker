"""Bonus cost and provenance (migration 0005).

``cost_multiplier`` is a generated column — never written from Python — and
``bought`` is deliberately three-state, so "we never recorded this" stays
distinguishable from "this was a natural trigger".
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.bonuses import (
    LogFilters,
    create_bonus,
    query_log,
    update_bonus,
)
from app.services.sorting import Sort
from tests.support import make_sessionmaker


def _bought(session, win: str, cost: str):
    return create_bonus(
        session,
        game_name="Big Bass",
        played_on=date(2024, 1, 1),
        bet=Decimal("0.20"),
        win=Decimal(win),
        cost=Decimal(cost),
        bought=True,
    )


def test_cost_multiplier_is_generated_from_win_and_cost() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        bonus = _bought(s, "250.00", "20.00")
        s.commit()
        assert bonus.cost_multiplier == Decimal("12.5")  # 250 / 20
        # The spin multiplier is unaffected and still win/bet.
        assert bonus.multiplier == Decimal("1250")


def test_whole_number_cost_divides_exactly() -> None:
    """Regression guard for integer division. SQLite divides whole numbers as
    integers, so a naive ``win / cost`` returned 12 instead of 12.5 here and the
    test database disagreed with PostgreSQL. The expression multiplies by a decimal
    literal to force exact division on both."""
    Session = make_sessionmaker()
    with Session() as s:
        bonus = _bought(s, "250.00", "20.00")
        s.commit()
        assert bonus.cost_multiplier == Decimal("12.5")

        halves = _bought(s, "75.00", "50.00")
        s.commit()
        assert halves.cost_multiplier == Decimal("1.5")


def test_zero_cost_does_not_blow_up() -> None:
    """NULLIF guards the division; a free bonus has no meaningful buy return."""
    Session = make_sessionmaker()
    with Session() as s:
        bonus = _bought(s, "50.00", "0.00")
        s.commit()
        assert bonus.cost_multiplier is None


def test_natural_bonus_records_no_cost() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        bonus = create_bonus(
            session=s,
            game_name="Big Bass",
            played_on=date(2024, 1, 1),
            bet=Decimal("0.20"),
            win=Decimal("40.00"),
            bought=False,
        )
        s.commit()
        assert bonus.bought is False
        assert bonus.cost is None
        assert bonus.cost_multiplier is None


def test_a_cost_without_claiming_bought_is_dropped() -> None:
    """Recording a buy price while leaving provenance unknown is contradictory,
    so the cost is discarded rather than stored against an unknown."""
    Session = make_sessionmaker()
    with Session() as s:
        bonus = create_bonus(
            session=s,
            game_name="Big Bass",
            played_on=date(2024, 1, 1),
            bet=Decimal("0.20"),
            win=Decimal("40.00"),
            cost=Decimal("20.00"),
            bought=None,
        )
        s.commit()
        assert bonus.bought is None
        assert bonus.cost is None


def test_provenance_defaults_to_unknown() -> None:
    """Rows created without an explicit flag — notably every imported row — stay
    honestly unknown rather than being labelled natural."""
    Session = make_sessionmaker()
    with Session() as s:
        bonus = create_bonus(
            session=s,
            game_name="Big Bass",
            played_on=date(2024, 1, 1),
            bet=Decimal("0.20"),
            win=Decimal("10.00"),
        )
        s.commit()
        assert bonus.bought is None


def test_editing_recomputes_and_can_clear_a_buy() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        bonus = _bought(s, "250.00", "20.00")
        s.commit()

        updated = update_bonus(
            s,
            bonus.id,
            game_name="Big Bass",
            played_on=date(2024, 1, 1),
            bet=Decimal("0.20"),
            win=Decimal("250.00"),
            cost=Decimal("50.00"),
            bought=True,
        )
        s.commit()
        assert updated.cost_multiplier == Decimal("5")  # 250 / 50

        # Reclassifying as natural clears the cost and the derived return.
        reverted = update_bonus(
            s,
            bonus.id,
            game_name="Big Bass",
            played_on=date(2024, 1, 1),
            bet=Decimal("0.20"),
            win=Decimal("250.00"),
            cost=Decimal("50.00"),
            bought=False,
        )
        s.commit()
        assert reverted.bought is False
        assert reverted.cost is None
        assert reverted.cost_multiplier is None


def _seed_mixed(session) -> None:
    _bought(session, "250.00", "20.00")
    create_bonus(
        session,
        game_name="Sugar Rush",
        played_on=date(2024, 2, 1),
        bet=Decimal("0.20"),
        win=Decimal("40.00"),
        bought=False,
    )
    create_bonus(
        session,
        game_name="Gates of Olympus",
        played_on=date(2024, 3, 1),
        bet=Decimal("0.20"),
        win=Decimal("15.00"),
    )  # unknown
    session.commit()


def test_provenance_filters_split_all_three_states() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed_mixed(s)

        def games(value: str) -> list[str]:
            return [r.game_name for r in query_log(s, filters=LogFilters(provenance=value)).rows]

        assert games("bought") == ["Big Bass"]
        assert games("natural") == ["Sugar Rush"]
        assert games("unknown") == ["Gates of Olympus"]
        # No filter returns everything.
        assert query_log(s).summary.count == 3


def test_sorting_by_cost_and_buy_return_puts_unknowns_last() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed_mixed(s)

        by_cost = query_log(s, sort=Sort("cost", descending=True)).rows
        assert by_cost[0].bonus.cost == Decimal("20.00")
        assert by_cost[-1].bonus.cost is None  # nulls last

        by_return = query_log(s, sort=Sort("costx", descending=False)).rows
        assert by_return[0].bonus.cost_multiplier == Decimal("12.5")
        assert by_return[-1].bonus.cost_multiplier is None
