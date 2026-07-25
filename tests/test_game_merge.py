"""Game merge and alias management (Phase B).

Merging must reparent every bonus onto the target, fold the source's name into the
alias table so future entry auto-corrects, and delete the source game — closing
the kind of spelling drift that produced 624 games where 572 were expected.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.models import Bonus, Game, GameAlias
from app.services.bonuses import create_bonus
from app.services.games import add_alias, game_by_name, merge_games
from tests.support import make_sessionmaker


def _two_games_with_bonuses(session) -> tuple[int, int]:
    # "Wanted Dead of Wild" (typo) and the canonical "Wanted Dead or Wild".
    a = create_bonus(
        session,
        game_name="Wanted Dead of Wild",
        played_on=date(2024, 1, 1),
        bet=Decimal("0.20"),
        win=Decimal("40.00"),
    )
    b = create_bonus(
        session,
        game_name="Wanted Dead or Wild",
        played_on=date(2024, 1, 2),
        bet=Decimal("0.20"),
        win=Decimal("60.00"),
    )
    session.commit()
    return a.game_id, b.game_id


def test_merge_reparents_bonuses_adds_alias_and_deletes_source() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        source_id, target_id = _two_games_with_bonuses(s)

        survivor = merge_games(s, source_id, target_id)
        s.commit()

        assert survivor is not None and survivor.id == target_id
        # Source game gone.
        assert s.get(Game, source_id) is None
        # Both bonuses now point at the target.
        assert (
            s.scalar(select(func.count()).select_from(Bonus).where(Bonus.game_id == target_id)) == 2
        )
        # Source spelling is now an alias of the target -> future entry corrects it.
        alias = s.get(GameAlias, "Wanted Dead of Wild")
        assert alias is not None and alias.game_id == target_id
        # And resolving that spelling through a new entry lands on the target.
        again = create_bonus(
            s,
            game_name="Wanted Dead of Wild",
            played_on=date(2024, 1, 3),
            bet=Decimal("0.20"),
            win=Decimal("5.00"),
        )
        s.commit()
        assert again.game_id == target_id


def test_merge_into_self_is_noop() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        source_id, _ = _two_games_with_bonuses(s)
        assert merge_games(s, source_id, source_id) is None


def test_existing_alias_is_repointed_on_merge() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        source_id, target_id = _two_games_with_bonuses(s)
        # An alias already pointing at the source should follow it to the target.
        s.add(GameAlias(alias="wdw", game_id=source_id))
        s.flush()

        merge_games(s, source_id, target_id)
        s.commit()

        assert s.get(GameAlias, "wdw").game_id == target_id


def test_add_alias_is_idempotent_and_guards() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _, target_id = _two_games_with_bonuses(s)

        assert add_alias(s, "WDoW", target_id) is True
        assert s.get(GameAlias, "WDoW").game_id == target_id
        # Repointing an existing alias is allowed (idempotent upsert).
        assert add_alias(s, "WDoW", target_id) is True
        # Aliasing a game to its own canonical name is rejected.
        target = game_by_name(s, "Wanted Dead or Wild")
        assert add_alias(s, "Wanted Dead or Wild", target.id) is False
        # Unknown game rejected.
        assert add_alias(s, "whatever", 9999) is False
