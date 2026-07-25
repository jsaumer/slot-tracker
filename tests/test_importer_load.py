"""Loader behaviour: game/alias seeding, union semantics, and idempotency."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.importer.loader import load
from app.importer.records import BonusRecord, HuntRecord
from app.models import Bonus, Game, GameAlias, Hunt
from tests.support import make_sessionmaker


def _records() -> tuple[list[HuntRecord], list[BonusRecord]]:
    hunts = [
        HuntRecord(
            import_ref="hunt:1",
            label="Bonus Hunt 1",
            hunt_date=date(2023, 5, 1),
            start_balance=Decimal("500.00"),
            end_balance=Decimal("450.00"),
        ),
    ]
    bonuses = [
        # Raw alias spelling -> should resolve to canonical "Sugar Rush".
        BonusRecord("main:2", "Sugar RUsh", date(2023, 1, 2), Decimal("0.20"), Decimal("40.00")),
        # Two records with identical content but distinct import_refs: a
        # coincidental collision that must be kept as a union, not deduped.
        BonusRecord(
            "main:3", "Gates of Olympus", date(2023, 1, 3), Decimal("0.20"), Decimal("10.00")
        ),
        BonusRecord(
            "main:4", "Gates of Olympus", date(2023, 1, 3), Decimal("0.20"), Decimal("10.00")
        ),
        # A pre-2021 suspect row.
        BonusRecord(
            "main:5",
            "Book of Dead",
            date(2012, 7, 1),
            Decimal("0.10"),
            Decimal("5.00"),
            date_suspect=True,
        ),
        # A notable standalone.
        BonusRecord(
            "main:6",
            "Wanted Dead or Wild",
            date(2024, 2, 2),
            Decimal("1.00"),
            Decimal("2500.00"),
            notable=True,
        ),
        # A hunt bonus tied to hunt:1.
        BonusRecord(
            "hunt:1:2",
            "Money train 2",
            date(2023, 5, 1),
            Decimal("0.50"),
            Decimal("75.00"),
            hunt_ref="hunt:1",
        ),
    ]
    return hunts, bonuses


def test_first_load_seeds_games_aliases_and_flags() -> None:
    Session = make_sessionmaker()
    hunts, bonuses = _records()
    with Session() as s:
        summary = load(s, hunts, bonuses)
        s.commit()

        assert summary.bonuses_inserted == 6
        assert summary.hunts_created == 1
        assert summary.suspects_flagged == 1
        assert summary.notable_flagged == 1

        # Alias resolved to the canonical game, and the alias row was seeded.
        names = set(s.execute(select(Game.name)).scalars())
        assert "Sugar Rush" in names
        assert "Money Train 2" in names
        alias = s.get(GameAlias, "Sugar RUsh")
        assert alias is not None
        assert s.get(Game, alias.game_id).name == "Sugar Rush"

        # Union kept both coincidental duplicates.
        dupes = s.scalar(
            select(func.count())
            .select_from(Bonus)
            .where(Bonus.game_id == names_lookup(s, "Gates of Olympus"))
        )
        assert dupes == 2

        # Generated multiplier materialized (win/bet), never written by us.
        sugar = s.scalar(select(Bonus).where(Bonus.import_ref == "main:2"))
        assert sugar.multiplier == Decimal("200")  # 40.00 / 0.20

        # Hunt bonus is linked.
        hunt = s.scalar(select(Hunt).where(Hunt.import_ref == "hunt:1"))
        assert hunt.label == "Bonus Hunt 1"
        linked = s.scalar(select(func.count()).select_from(Bonus).where(Bonus.hunt_id == hunt.id))
        assert linked == 1


def test_rerun_is_idempotent() -> None:
    Session = make_sessionmaker()
    hunts, bonuses = _records()

    with Session() as s:
        first = load(s, hunts, bonuses)
        s.commit()
        aliases_after_first = s.scalar(select(func.count()).select_from(GameAlias))

    with Session() as s:
        second = load(s, hunts, bonuses)
        s.commit()
        aliases_after_second = s.scalar(select(func.count()).select_from(GameAlias))

        assert second.bonuses_inserted == 0
        assert second.bonuses_updated == 6
        assert second.games_created == 0
        assert second.hunts_created == 0
        # Totals stable across runs.
        assert second.total_bonuses == first.total_bonuses == 6
        assert second.total_hunts == first.total_hunts == 1
        assert aliases_after_second == aliases_after_first


def names_lookup(session, name: str) -> int:
    return session.scalar(select(Game.id).where(Game.name == name))
