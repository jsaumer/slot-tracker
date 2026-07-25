"""CSV export of the bonus log, so the data is never trapped in the container."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bonus, Game

_HEADER = [
    "id",
    "game",
    "played_on",
    "bet",
    "win",
    "multiplier",
    "notable",
    "date_suspect",
    "hunt_id",
    "session_id",
    "replay_url",
    "notes",
]


def iter_bonus_csv(session: Session) -> Iterator[str]:
    """Stream the full bonus log as CSV rows, oldest first."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    def flush() -> str:
        value = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return value

    writer.writerow(_HEADER)
    yield flush()

    stmt = (
        select(Bonus, Game.name)
        .join(Game, Bonus.game_id == Game.id)
        .order_by(Bonus.played_on.asc(), Bonus.id.asc())
    )
    for bonus, game_name in session.execute(stmt).yield_per(500):
        writer.writerow(
            [
                bonus.id,
                game_name,
                bonus.played_on.isoformat() if bonus.played_on else "",
                bonus.bet,
                bonus.win,
                bonus.multiplier,
                bonus.notable,
                bonus.date_suspect,
                bonus.hunt_id or "",
                bonus.session_id or "",
                bonus.replay_url or "",
                (bonus.notes or "").replace("\n", " "),
            ]
        )
        yield flush()
