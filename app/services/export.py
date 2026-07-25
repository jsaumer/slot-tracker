"""CSV exports, so the data is never trapped in the container.

The bonus export honours the same filters as the log view — it reuses
``log_conditions`` rather than reimplementing them, because an export that
silently ignored the active filters would contradict the UI it is launched from.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bonus, Game
from app.services.bonuses import LogFilters, log_conditions
from app.services.hunts import list_hunts
from app.services.sessions import list_sessions, session_pnl

_BONUS_HEADER = [
    "id",
    "game",
    "played_on",
    "bet",
    "win",
    "multiplier",
    "cost",
    "bought",
    "cost_multiplier",
    "notable",
    "date_suspect",
    "hunt_id",
    "session_id",
    "replay_url",
    "notes",
]

_HUNT_HEADER = [
    "id",
    "label",
    "hunt_date",
    "status",
    "end_convention",
    "start_balance",
    "end_balance",
    "bonuses",
    "total_win",
    "cost",
    "net",
    "roi",
    "notes",
]

_SESSION_HEADER = [
    "id",
    "site",
    "started_at",
    "ended_at",
    "deposit",
    "cashout",
    "net",
    "running_total",
    "attached_bonuses",
    "attached_bonus_win",
    "notes",
]


class _Rows:
    """Incremental CSV writer — yields each row as it is written so large
    exports stream instead of buffering in memory."""

    def __init__(self, header: Sequence[str]) -> None:
        self._buffer = io.StringIO()
        self._writer = csv.writer(self._buffer)
        self._header = header

    def write(self, values: Sequence[Any]) -> str:
        self._writer.writerow(values)
        value = self._buffer.getvalue()
        self._buffer.seek(0)
        self._buffer.truncate(0)
        return value

    def header(self) -> str:
        return self.write(self._header)


def _text(value: Any) -> str:
    """Flatten free text to one CSV line."""
    return (value or "").replace("\n", " ").replace("\r", " ")


def _iso(value: Any) -> str:
    return value.isoformat() if value is not None else ""


def iter_bonus_csv(session: Session, filters: LogFilters | None = None) -> Iterator[str]:
    """Stream the bonus log as CSV, oldest first, narrowed by ``filters``."""
    filters = filters or LogFilters()
    rows = _Rows(_BONUS_HEADER)
    yield rows.header()

    stmt = (
        select(Bonus, Game.name)
        .join(Game, Bonus.game_id == Game.id)
        .where(*log_conditions(filters))
        .order_by(Bonus.played_on.asc().nullsfirst(), Bonus.id.asc())
    )
    for bonus, game_name in session.execute(stmt).yield_per(500):
        yield rows.write(
            [
                bonus.id,
                game_name,
                _iso(bonus.played_on),
                bonus.bet,
                bonus.win,
                bonus.multiplier,
                bonus.cost if bonus.cost is not None else "",
                # Empty rather than "None": provenance is genuinely unknown for
                # imported rows, and "False" would misrepresent that.
                "" if bonus.bought is None else bonus.bought,
                bonus.cost_multiplier if bonus.cost_multiplier is not None else "",
                bonus.notable,
                bonus.date_suspect,
                bonus.hunt_id or "",
                bonus.session_id or "",
                bonus.replay_url or "",
                _text(bonus.notes),
            ]
        )


def iter_hunt_csv(session: Session) -> Iterator[str]:
    """Stream hunts with their derived cost/net/ROI — the same figures the UI
    shows, via the same ``hunt_result`` formulas."""
    rows = _Rows(_HUNT_HEADER)
    yield rows.header()

    for view in list_hunts(session):
        hunt = view.hunt
        yield rows.write(
            [
                hunt.id,
                _text(hunt.label),
                _iso(hunt.hunt_date),
                hunt.status,
                hunt.end_convention,
                hunt.start_balance if hunt.start_balance is not None else "",
                hunt.end_balance if hunt.end_balance is not None else "",
                view.bonus_count,
                view.total_win,
                view.result.cost if view.result.cost is not None else "",
                view.result.net if view.result.net is not None else "",
                view.result.roi if view.result.roi is not None else "",
                _text(hunt.notes),
            ]
        )


def iter_session_csv(session: Session) -> Iterator[str]:
    """Stream play sessions with their running total and attached-bonus figures."""
    rows = _Rows(_SESSION_HEADER)
    yield rows.header()

    for view in list_sessions(session):
        ps = view.session
        pnl = session_pnl(session, ps.id)
        yield rows.write(
            [
                ps.id,
                _text(ps.site),
                _iso(ps.started_at),
                _iso(ps.ended_at),
                ps.deposit if ps.deposit is not None else "",
                ps.cashout if ps.cashout is not None else "",
                ps.net if ps.net is not None else "",
                view.running_total,
                pnl.bonus_count,
                pnl.bonus_win_total,
                _text(ps.notes),
            ]
        )
