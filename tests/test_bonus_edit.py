"""Edit and delete of bonuses (Phase A).

Correctness that matters here: the generated multiplier recomputes on edit and is
never written by us, and a corrected game name is re-resolved through the alias
table exactly as on entry.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.models import Bonus, Game, GameAlias
from app.services.bonuses import create_bonus, delete_bonus, get_bonus, update_bonus
from tests.support import make_sessionmaker


def _seed_alias(session) -> None:
    # "Sugar RUsh" -> canonical "Sugar Rush", so edits exercise alias resolution.
    game = Game(name="Sugar Rush")
    session.add(game)
    session.flush()
    session.add(GameAlias(alias="Sugar RUsh", game_id=game.id))
    session.flush()


def test_update_recomputes_multiplier_and_resolves_alias() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed_alias(s)
        bonus = create_bonus(
            s,
            game_name="Big Bass",
            played_on=date(2024, 1, 1),
            bet=Decimal("0.20"),
            win=Decimal("10.00"),
        )
        s.commit()
        bonus_id = bonus.id

        updated = update_bonus(
            s,
            bonus_id,
            game_name="Sugar RUsh",  # misspelling -> should land on "Sugar Rush"
            played_on=date(2024, 2, 2),
            bet=Decimal("0.50"),
            win=Decimal("125.00"),
            notable=True,
        )
        s.commit()

        assert updated is not None
        assert updated.multiplier == Decimal("250")  # 125.00 / 0.50, generated
        assert updated.notable is True
        assert s.get(Game, updated.game_id).name == "Sugar Rush"


def test_update_missing_returns_none() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        assert (
            update_bonus(
                s,
                9999,
                game_name="X",
                played_on=None,
                bet=Decimal("0.20"),
                win=Decimal("1.00"),
            )
            is None
        )


def test_delete_removes_row() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        bonus = create_bonus(
            s,
            game_name="Big Bass",
            played_on=date(2024, 1, 1),
            bet=Decimal("0.20"),
            win=Decimal("10.00"),
        )
        s.commit()
        bonus_id = bonus.id

        assert delete_bonus(s, bonus_id) is True
        s.commit()
        assert get_bonus(s, bonus_id) is None
        assert s.scalar(select(func.count()).select_from(Bonus)) == 0

        assert delete_bonus(s, bonus_id) is False  # already gone
