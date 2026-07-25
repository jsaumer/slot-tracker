"""Hunt editing, reopening, and deletion.

Before this existed, closing a hunt was effectively irreversible: the close form
only renders while a hunt is open, so a mistyped end balance was permanent.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models import Bonus, Hunt
from app.services.bonuses import create_bonus
from app.services.hunts import close_hunt, delete_hunt, get_hunt, open_hunt, update_hunt
from tests.support import make_sessionmaker


def _hunt_with_bonus(session) -> tuple[int, int]:
    hunt = open_hunt(
        session, label="Hunt A", start_balance=Decimal("500.00"), hunt_date=date(2024, 6, 1)
    )
    session.flush()
    bonus = create_bonus(
        session,
        game_name="Big Bass",
        played_on=date(2024, 6, 1),
        bet=Decimal("0.20"),
        win=Decimal("60.00"),
        hunt_id=hunt.id,
    )
    session.commit()
    return hunt.id, bonus.id


def test_reopen_and_correct_a_mistyped_end_balance() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        hunt_id, _ = _hunt_with_bonus(s)

        # Closed with the wrong end balance.
        close_hunt(s, hunt_id=hunt_id, end_balance=Decimal("50.00"), end_convention="after_opening")
        s.commit()
        assert get_hunt(s, hunt_id).result.net == Decimal("-450.00")

        # Reopen and fix it.
        updated = update_hunt(
            s,
            hunt_id,
            label="Hunt A",
            hunt_date=date(2024, 6, 1),
            start_balance=Decimal("500.00"),
            end_balance=Decimal("620.00"),
            end_convention="after_opening",
            status="open",
        )
        s.commit()

        assert updated is not None
        assert updated.status == "open"
        assert get_hunt(s, hunt_id).result.net == Decimal("120.00")


def test_update_can_switch_convention_and_recompute() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        hunt_id, _ = _hunt_with_bonus(s)
        update_hunt(
            s,
            hunt_id,
            label=None,
            hunt_date=date(2024, 6, 1),
            start_balance=Decimal("500.00"),
            end_balance=Decimal("440.00"),
            end_convention="spin_end",
            status="closed",
        )
        s.commit()

        view = get_hunt(s, hunt_id)
        # spin_end: cost = start - end = 60; net = total_win - cost = 60 - 60 = 0
        assert view.result.cost == Decimal("60.00")
        assert view.result.net == Decimal("0.00")


def test_update_missing_hunt_returns_none() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        assert (
            update_hunt(
                s,
                9999,
                label=None,
                hunt_date=None,
                start_balance=None,
                end_balance=None,
                end_convention="after_opening",
                status="open",
            )
            is None
        )


def test_delete_hunt_keeps_its_bonuses() -> None:
    """Deleting a hunt is a statement about the grouping, not the play."""
    Session = make_sessionmaker()
    with Session() as s:
        hunt_id, bonus_id = _hunt_with_bonus(s)

        assert delete_hunt(s, hunt_id) is True
        s.commit()

        assert s.get(Hunt, hunt_id) is None
        bonus = s.get(Bonus, bonus_id)
        assert bonus is not None  # survived
        assert bonus.hunt_id is None  # detached

        assert delete_hunt(s, hunt_id) is False  # already gone
