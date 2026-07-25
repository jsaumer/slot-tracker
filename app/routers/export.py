"""CSV export surfaces."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.routers.params import log_filters
from app.services.export import iter_bonus_csv, iter_hunt_csv, iter_session_csv

router = APIRouter()


def _csv(rows: Iterator[str], filename: str) -> StreamingResponse:
    return StreamingResponse(
        rows,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export")
def export_bonuses(
    session: Session = Depends(get_session),
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    bet: str = "",
    band: str = "",
    notable: bool = False,
    suspect: bool = False,
    has_replay: bool = False,
) -> StreamingResponse:
    """Accepts the same filters as /log, so the button in the log's filter bar
    exports what is on screen rather than the whole table."""
    filters = log_filters(
        q=q,
        date_from=date_from,
        date_to=date_to,
        bet=bet,
        band=band,
        notable=notable,
        suspect=suspect,
        has_replay=has_replay,
    )
    return _csv(iter_bonus_csv(session, filters), "bonus_log.csv")


@router.get("/export/hunts")
def export_hunts(session: Session = Depends(get_session)) -> StreamingResponse:
    return _csv(iter_hunt_csv(session), "hunts.csv")


@router.get("/export/sessions")
def export_sessions(session: Session = Depends(get_session)) -> StreamingResponse:
    return _csv(iter_session_csv(session), "sessions.csv")
