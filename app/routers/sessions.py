"""Play sessions surface."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.routers.params import parse_date, parse_decimal
from app.services import bonuses as bonus_svc
from app.services import sessions as session_svc
from app.services.sorting import parse_sort, query_url
from app.templating import render

router = APIRouter()


def _to_dt(raw: str) -> datetime | None:
    day = parse_date(raw)
    return datetime(day.year, day.month, day.day) if day else None


@router.get("/sessions")
def sessions(
    request: Request,
    session: Session = Depends(get_session),
    sort: str = "",
    direction: str = Query("", alias="dir"),
):
    active_sort = parse_sort(
        sort,
        direction,
        allowed=session_svc.SESSION_SORTS,
        default_key=session_svc.DEFAULT_SESSION_SORT.key,
        default_descending=session_svc.DEFAULT_SESSION_SORT.descending,
    )
    ctx = {
        "sessions": session_svc.list_sessions(session, active_sort),
        "sort": active_sort,
        "sort_url": lambda key: query_url(
            "/sessions", {"sort": key, "dir": active_sort.next_direction(key)}
        ),
    }
    return render(request, "sessions.html", ctx)


@router.post("/sessions")
def create_session(
    request: Request,
    session: Session = Depends(get_session),
    site: str = Form(""),
    deposit: str = Form(""),
    cashout: str = Form(""),
    started_at: str = Form(""),
    ended_at: str = Form(""),
    notes: str = Form(""),
):
    session_svc.create_session(
        session,
        site=site,
        deposit=parse_decimal(deposit, places=2),
        cashout=parse_decimal(cashout, places=2),
        started_at=_to_dt(started_at),
        ended_at=_to_dt(ended_at),
        notes=notes,
    )
    session.commit()
    return RedirectResponse("/sessions", status_code=303)


@router.get("/sessions/{session_id}")
def session_detail(
    request: Request,
    session_id: int,
    session: Session = Depends(get_session),
    sort: str = "",
    direction: str = Query("", alias="dir"),
):
    ps = session_svc.get_session(session, session_id)
    if ps is None:
        return render(request, "not_found.html", {"what": "session"}, status_code=404)
    active_sort = parse_sort(
        sort,
        direction,
        allowed=bonus_svc.BONUS_ROW_SORTS,
        default_key=bonus_svc.DEFAULT_BONUS_ROW_SORT.key,
        default_descending=bonus_svc.DEFAULT_BONUS_ROW_SORT.descending,
    )
    ctx = {
        "ps": ps,
        "pnl": session_svc.session_pnl(session, session_id),
        "bonuses": session_svc.session_bonuses(session, session_id, active_sort),
        "suggestions": session_svc.suggest_bonuses(session, session_id),
        "sort": active_sort,
        "sort_url": lambda key: query_url(
            f"/sessions/{session_id}", {"sort": key, "dir": active_sort.next_direction(key)}
        ),
    }
    return render(request, "session_detail.html", ctx)


@router.post("/sessions/{session_id}")
def update_session(
    request: Request,
    session_id: int,
    session: Session = Depends(get_session),
    site: str = Form(""),
    deposit: str = Form(""),
    cashout: str = Form(""),
    started_at: str = Form(""),
    ended_at: str = Form(""),
    notes: str = Form(""),
):
    session_svc.update_session(
        session,
        session_id,
        site=site,
        deposit=parse_decimal(deposit, places=2),
        cashout=parse_decimal(cashout, places=2),
        started_at=_to_dt(started_at),
        ended_at=_to_dt(ended_at),
        notes=notes,
    )
    session.commit()
    return RedirectResponse(f"/sessions/{session_id}", status_code=303)


@router.post("/sessions/{session_id}/delete")
def delete_session(
    request: Request,
    session_id: int,
    session: Session = Depends(get_session),
):
    session_svc.delete_session(session, session_id)
    session.commit()
    return RedirectResponse("/sessions", status_code=303)


@router.post("/sessions/{session_id}/attach")
def attach_bonuses(
    request: Request,
    session_id: int,
    session: Session = Depends(get_session),
    bonus_ids: list[int] = Form(default=[]),
):
    session_svc.attach_bonuses(session, session_id, bonus_ids)
    session.commit()
    return RedirectResponse(f"/sessions/{session_id}", status_code=303)


@router.post("/sessions/{session_id}/detach")
def detach_bonus(
    request: Request,
    session_id: int,
    session: Session = Depends(get_session),
    bonus_id: int = Form(...),
):
    session_svc.detach_bonus(session, session_id, bonus_id)
    session.commit()
    return RedirectResponse(f"/sessions/{session_id}", status_code=303)
