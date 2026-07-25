"""Play sessions: list with running total, and creation.

``net`` is a generated column — read, never written. The running total is a
Python cumulative sum over the chronological order.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import Bonus, Game, Hunt, PlaySession
from app.services.bonuses import BONUS_ROW_SORTS
from app.services.sorting import Sort, sort_rows


@dataclass
class SessionView:
    session: PlaySession
    running_total: Decimal


@dataclass
class SessionPnl:
    """Per-session summary. ``net`` (deposit/cashout) is the real profit or loss;
    the bonus figures are the activity that happened inside the session.

    A precise base-game stake ("what was wagered to reach these bonuses") is not
    derivable without per-bonus buy costs the source never recorded — so this is
    deliberately the honest subset: net, plus attached bonus count and winnings.
    """

    bonus_count: int
    bonus_win_total: Decimal


# Sortable columns on the session list. Python-side, because the running total is
# order-dependent and has no column to ORDER BY.
SESSION_SORTS = {
    "started": lambda v: v.session.started_at,
    "site": lambda v: (v.session.site or "").lower(),
    "deposit": lambda v: v.session.deposit,
    "cashout": lambda v: v.session.cashout,
    "net": lambda v: v.session.net,
    "running": lambda v: v.running_total,
}

DEFAULT_SESSION_SORT = Sort(key="started", descending=True)


def list_sessions(session: Session, sort: Sort | None = None) -> list[SessionView]:
    """The running total always accumulates oldest->newest, then rows are sorted
    for display. Computing it before sorting is deliberate: each row's running
    total means "cumulative through this session", which stays true no matter
    which column the table is sorted by. Recomputing per sort order would make
    the column meaningless.
    """
    rows = list(
        session.execute(
            select(PlaySession).order_by(
                PlaySession.started_at.asc().nullsfirst(), PlaySession.id.asc()
            )
        ).scalars()
    )
    running = Decimal(0)
    views: list[SessionView] = []
    for ps in rows:
        running += ps.net if ps.net is not None else Decimal(0)
        views.append(SessionView(session=ps, running_total=running))
    return sort_rows(views, sort or DEFAULT_SESSION_SORT, SESSION_SORTS)


def create_session(
    session: Session,
    *,
    site: str | None,
    deposit: Decimal | None,
    cashout: Decimal | None,
    started_at: datetime | None,
    ended_at: datetime | None,
    notes: str | None,
) -> PlaySession:
    ps = PlaySession(
        site=site or None,
        deposit=deposit,
        cashout=cashout,
        started_at=started_at,
        ended_at=ended_at,
        notes=notes or None,
    )
    session.add(ps)
    session.flush()
    session.refresh(ps)  # populate generated net
    return ps


def get_session(session: Session, session_id: int) -> PlaySession | None:
    return session.get(PlaySession, session_id)


def update_session(
    session: Session,
    session_id: int,
    *,
    site: str | None,
    deposit: Decimal | None,
    cashout: Decimal | None,
    started_at: datetime | None,
    ended_at: datetime | None,
    notes: str | None,
) -> PlaySession | None:
    ps = session.get(PlaySession, session_id)
    if ps is None:
        return None
    ps.site = site or None
    ps.deposit = deposit
    ps.cashout = cashout
    ps.started_at = started_at
    ps.ended_at = ended_at
    ps.notes = notes or None
    session.flush()
    session.refresh(ps)  # net is generated — reread it
    return ps


def delete_session(session: Session, session_id: int) -> bool:
    """Delete a session. Attached bonuses and hunts are detached first (set NULL)
    explicitly, so behaviour is identical on Postgres (FK ON DELETE SET NULL) and
    on the SQLite test DB (where FK enforcement may be off)."""
    ps = session.get(PlaySession, session_id)
    if ps is None:
        return False
    session.execute(update(Bonus).where(Bonus.session_id == session_id).values(session_id=None))
    session.execute(update(Hunt).where(Hunt.session_id == session_id).values(session_id=None))
    session.execute(delete(PlaySession).where(PlaySession.id == session_id))
    session.flush()
    return True


def session_pnl(session: Session, session_id: int) -> SessionPnl:
    count, total = session.execute(
        select(func.count(Bonus.id), func.coalesce(func.sum(Bonus.win), 0)).where(
            Bonus.session_id == session_id
        )
    ).one()
    return SessionPnl(bonus_count=count, bonus_win_total=Decimal(total))


def _bonus_rows(session: Session, stmt) -> list[tuple[Bonus, str]]:
    return list(session.execute(stmt).all())


def session_bonuses(
    session: Session, session_id: int, sort: Sort | None = None
) -> list[tuple[Bonus, str]]:
    """Bonuses currently attached to this session."""
    stmt = (
        select(Bonus, Game.name)
        .join(Game, Bonus.game_id == Game.id)
        .where(Bonus.session_id == session_id)
        .order_by(Bonus.played_on.asc().nullsfirst(), Bonus.id.asc())
    )
    rows = _bonus_rows(session, stmt)
    if sort is None:
        return rows
    return sort_rows(rows, sort, BONUS_ROW_SORTS)


def suggest_bonuses(session: Session, session_id: int, limit: int = 200) -> list[tuple[Bonus, str]]:
    """Unattached bonuses that fall within the session's date window — the
    reconcile candidates. Empty if the session has no start date to anchor on."""
    ps = session.get(PlaySession, session_id)
    if ps is None or ps.started_at is None:
        return []
    day_from = ps.started_at.date()
    day_to = ps.ended_at.date() if ps.ended_at is not None else day_from
    stmt = (
        select(Bonus, Game.name)
        .join(Game, Bonus.game_id == Game.id)
        .where(
            Bonus.session_id.is_(None),
            Bonus.played_on.is_not(None),
            Bonus.played_on >= day_from,
            Bonus.played_on <= day_to,
        )
        .order_by(Bonus.played_on.asc(), Bonus.id.asc())
        .limit(limit)
    )
    return _bonus_rows(session, stmt)


def attach_bonuses(session: Session, session_id: int, bonus_ids: Sequence[int]) -> int:
    if not bonus_ids:
        return 0
    result = session.execute(
        update(Bonus)
        .where(Bonus.id.in_(list(bonus_ids)), Bonus.session_id.is_(None))
        .values(session_id=session_id)
    )
    session.flush()
    return result.rowcount or 0


def detach_bonus(session: Session, session_id: int, bonus_id: int) -> bool:
    result = session.execute(
        update(Bonus)
        .where(Bonus.id == bonus_id, Bonus.session_id == session_id)
        .values(session_id=None)
    )
    session.flush()
    return bool(result.rowcount)
