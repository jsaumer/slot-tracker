"""CSV export surface."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.services.export import iter_bonus_csv

router = APIRouter()


@router.get("/export")
def export_csv(session: Session = Depends(get_session)) -> StreamingResponse:
    return StreamingResponse(
        iter_bonus_csv(session),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="bonus_log.csv"'},
    )
