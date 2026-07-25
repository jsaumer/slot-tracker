"""Sessions <-> bonuses P&L wiring (Phase C).

The reconcile model: a bonus is attached to a session after the fact, suggested
by the session's date window. ``session.net`` (deposit/cashout) stays the real
P/L; the attached bonuses are the activity inside it.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.models import Bonus
from app.services.bonuses import create_bonus
from app.services.sessions import (
    attach_bonuses,
    create_session,
    delete_session,
    detach_bonus,
    session_pnl,
    suggest_bonuses,
)
from tests.support import make_sessionmaker


def _mk_bonus(session, day: date, win: str) -> int:
    b = create_bonus(
        session,
        game_name="Big Bass",
        played_on=day,
        bet=Decimal("0.20"),
        win=Decimal(win),
    )
    return b.id


def _mk_session(session) -> int:
    ps = create_session(
        session,
        site="Stake",
        deposit=Decimal("100.00"),
        cashout=Decimal("60.00"),
        started_at=datetime(2024, 3, 1),
        ended_at=datetime(2024, 3, 2),
        notes=None,
    )
    return ps.id


def test_suggest_only_returns_unattached_in_window() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        session_id = _mk_session(s)
        in_window = _mk_bonus(s, date(2024, 3, 1), "40.00")
        also_in = _mk_bonus(s, date(2024, 3, 2), "10.00")
        _mk_bonus(s, date(2024, 2, 27), "99.00")  # before window
        _mk_bonus(s, date(2024, 3, 5), "99.00")  # after window
        s.commit()

        ids = {b.id for b, _ in suggest_bonuses(s, session_id)}
        assert ids == {in_window, also_in}


def test_attach_then_pnl_then_detach() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        session_id = _mk_session(s)
        b1 = _mk_bonus(s, date(2024, 3, 1), "40.00")
        b2 = _mk_bonus(s, date(2024, 3, 2), "10.00")
        s.commit()

        assert attach_bonuses(s, session_id, [b1, b2]) == 2
        s.commit()

        pnl = session_pnl(s, session_id)
        assert pnl.bonus_count == 2
        assert pnl.bonus_win_total == Decimal("50.00")
        # net is the generated deposit/cashout figure, independent of bonuses.
        assert s.get(Bonus, b1).session_id == session_id

        # Attaching an already-attached bonus is a no-op (guarded on session_id IS NULL).
        assert attach_bonuses(s, session_id, [b1]) == 0

        assert detach_bonus(s, session_id, b1) is True
        s.commit()
        assert s.get(Bonus, b1).session_id is None
        assert session_pnl(s, session_id).bonus_count == 1


def test_suggest_empty_without_start_date() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        ps = create_session(
            s,
            site=None,
            deposit=Decimal("50.00"),
            cashout=Decimal("70.00"),
            started_at=None,
            ended_at=None,
            notes=None,
        )
        s.commit()
        _mk_bonus(s, date(2024, 3, 1), "40.00")
        s.commit()
        assert suggest_bonuses(s, ps.id) == []


def test_delete_session_detaches_bonuses() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        session_id = _mk_session(s)
        b1 = _mk_bonus(s, date(2024, 3, 1), "40.00")
        s.commit()
        attach_bonuses(s, session_id, [b1])
        s.commit()

        assert delete_session(s, session_id) is True
        s.commit()
        # Bonus survives, just detached.
        bonus = s.get(Bonus, b1)
        assert bonus is not None
        assert bonus.session_id is None
