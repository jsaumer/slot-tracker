"""Hunt mode: open/add/close, and the cost/net/ROI formulas from the brief.

The formula is pure and unit-tested. Per docs/build-brief.md:

    cost = start_balance                      (after_opening)
         = start_balance - end_balance        (spin_end)

    net  = end_balance - start_balance        (after_opening)
         = total_bonus_win - cost             (spin_end)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Bonus, Hunt
from app.services.bonuses import BONUS_ROW_SORTS
from app.services.sorting import Sort, sort_rows


@dataclass
class HuntResult:
    cost: Decimal | None
    net: Decimal | None
    roi: Decimal | None  # net / cost, as a fraction (0.10 == +10%)


def hunt_result(
    *,
    start_balance: Decimal | None,
    end_balance: Decimal | None,
    end_convention: str,
    total_bonus_win: Decimal,
) -> HuntResult:
    if end_convention == "spin_end":
        cost = (
            start_balance - end_balance
            if start_balance is not None and end_balance is not None
            else None
        )
        net = total_bonus_win - cost if cost is not None else None
    else:  # after_opening
        cost = start_balance
        net = (
            end_balance - start_balance
            if start_balance is not None and end_balance is not None
            else None
        )
    roi = None
    if net is not None and cost not in (None, Decimal(0)):
        roi = (net / cost).quantize(Decimal("0.0001"))
    return HuntResult(cost=cost, net=net, roi=roi)


# --------------------------------------------------------------------------- #
# persistence / views
# --------------------------------------------------------------------------- #
@dataclass
class HuntView:
    hunt: Hunt
    bonus_count: int
    total_win: Decimal
    result: HuntResult


# Sortable columns on the hunt list. These sort in Python, not SQL: cost, net and
# ROI are derived by hunt_result() and have no column to ORDER BY. Cheap — there
# are 27 hunts.
HUNT_SORTS = {
    "hunt": lambda v: (v.hunt.label or f"Hunt {v.hunt.id}").lower(),
    "date": lambda v: v.hunt.hunt_date,
    "status": lambda v: v.hunt.status,
    "bonuses": lambda v: v.bonus_count,
    "won": lambda v: v.total_win,
    "cost": lambda v: v.result.cost,
    "net": lambda v: v.result.net,
    "roi": lambda v: v.result.roi,
}

DEFAULT_HUNT_SORT = Sort(key="date", descending=True)


def list_hunts(session: Session, sort: Sort | None = None) -> list[HuntView]:
    hunts = session.execute(
        select(Hunt).order_by(Hunt.hunt_date.desc().nullslast(), Hunt.id.desc())
    ).scalars()
    views = [_view(session, h) for h in hunts]
    return sort_rows(views, sort or DEFAULT_HUNT_SORT, HUNT_SORTS)


def get_hunt(session: Session, hunt_id: int) -> HuntView | None:
    hunt = session.get(Hunt, hunt_id)
    if hunt is None:
        return None
    return _view(session, hunt)


def hunt_bonuses(
    session: Session, hunt_id: int, sort: Sort | None = None
) -> list[tuple[Bonus, str]]:
    from app.models import Game

    stmt = (
        select(Bonus, Game.name)
        .join(Game, Bonus.game_id == Game.id)
        .where(Bonus.hunt_id == hunt_id)
        .order_by(Bonus.id.asc())
    )
    rows = list(session.execute(stmt).all())
    if sort is None:
        return rows
    return sort_rows(rows, sort, BONUS_ROW_SORTS)


def _view(session: Session, hunt: Hunt) -> HuntView:
    count, total = session.execute(
        select(func.count(Bonus.id), func.coalesce(func.sum(Bonus.win), 0)).where(
            Bonus.hunt_id == hunt.id
        )
    ).one()
    total_win = Decimal(total)
    return HuntView(
        hunt=hunt,
        bonus_count=count,
        total_win=total_win,
        result=hunt_result(
            start_balance=hunt.start_balance,
            end_balance=hunt.end_balance,
            end_convention=hunt.end_convention,
            total_bonus_win=total_win,
        ),
    )


def open_hunt(
    session: Session,
    *,
    label: str | None,
    start_balance: Decimal | None,
    hunt_date: date | None,
) -> Hunt:
    hunt = Hunt(
        label=label or None,
        start_balance=start_balance,
        hunt_date=hunt_date,
        status="open",
    )
    session.add(hunt)
    session.flush()
    return hunt


def close_hunt(
    session: Session,
    *,
    hunt_id: int,
    end_balance: Decimal | None,
    end_convention: str,
) -> Hunt | None:
    hunt = session.get(Hunt, hunt_id)
    if hunt is None:
        return None
    hunt.end_balance = end_balance
    hunt.end_convention = end_convention
    hunt.status = "closed"
    session.flush()
    return hunt
