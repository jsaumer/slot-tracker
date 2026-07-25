"""Hunt mode: open, add bonuses, close; show cost / net / ROI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Hunt
from app.routers.params import parse_date, parse_decimal
from app.services import bonuses as bonus_svc
from app.services import hunts as hunt_svc
from app.services.games import all_game_names
from app.services.sorting import parse_sort, query_url
from app.templating import render, today_local

router = APIRouter()


@router.get("/hunts")
def hunts(
    request: Request,
    session: Session = Depends(get_session),
    sort: str = "",
    direction: str = Query("", alias="dir"),
):
    active_sort = parse_sort(
        sort,
        direction,
        allowed=hunt_svc.HUNT_SORTS,
        default_key=hunt_svc.DEFAULT_HUNT_SORT.key,
        default_descending=hunt_svc.DEFAULT_HUNT_SORT.descending,
    )
    ctx = {
        "hunts": hunt_svc.list_hunts(session, active_sort),
        "sort": active_sort,
        "sort_url": lambda key: query_url(
            "/hunts", {"sort": key, "dir": active_sort.next_direction(key)}
        ),
    }
    return render(request, "hunts/list.html", ctx)


@router.post("/hunts")
def open_hunt(
    request: Request,
    session: Session = Depends(get_session),
    label: str = Form(""),
    start_balance: str = Form(""),
    hunt_date: str = Form(""),
):
    hunt = hunt_svc.open_hunt(
        session,
        label=label,
        start_balance=parse_decimal(start_balance, places=2),
        hunt_date=parse_date(hunt_date) or today_local(),
    )
    session.commit()
    return RedirectResponse(f"/hunts/{hunt.id}", status_code=303)


def _convention(raw: str) -> str:
    return raw if raw in ("after_opening", "spin_end") else "after_opening"


def _detail_response(
    request: Request,
    hunt_id: int,
    session: Session,
    *,
    sort: str = "",
    direction: str = "",
    error: str | None = None,
    status_code: int = 200,
):
    """Render the hunt detail page. Shared with the add-bonus error path so a
    rejected entry re-renders in place instead of redirecting silently."""
    view = hunt_svc.get_hunt(session, hunt_id)
    if view is None:
        return render(request, "not_found.html", {"what": "hunt"}, status_code=404)
    active_sort = parse_sort(
        sort,
        direction,
        allowed=bonus_svc.BONUS_ROW_SORTS,
        default_key=bonus_svc.DEFAULT_BONUS_ROW_SORT.key,
        default_descending=bonus_svc.DEFAULT_BONUS_ROW_SORT.descending,
    )
    ctx = {
        "view": view,
        "bonuses": hunt_svc.hunt_bonuses(session, hunt_id, active_sort),
        "games": all_game_names(session),
        "today": today_local().isoformat(),
        "sort": active_sort,
        "sort_url": lambda key: query_url(
            f"/hunts/{hunt_id}", {"sort": key, "dir": active_sort.next_direction(key)}
        ),
        "error": error,
    }
    return render(request, "hunts/detail.html", ctx, status_code=status_code)


@router.get("/hunts/{hunt_id}")
def hunt_detail(
    request: Request,
    hunt_id: int,
    session: Session = Depends(get_session),
    sort: str = "",
    direction: str = Query("", alias="dir"),
):
    return _detail_response(request, hunt_id, session, sort=sort, direction=direction)


@router.post("/hunts/{hunt_id}/bonus")
def add_hunt_bonus(
    request: Request,
    hunt_id: int,
    session: Session = Depends(get_session),
    # Defaulted, not Form(...) — see the note on add_bonus in routers/bonuses.py.
    game: str = Form(""),
    bet: str = Form(""),
    win: str = Form(""),
    played_on: str = Form(""),
    notes: str = Form(""),
    notable: bool = Form(False),
):
    bet_dec = parse_decimal(bet, places=4)
    win_dec = parse_decimal(win, places=2)

    if not game.strip() or bet_dec is None or win_dec is None or bet_dec <= 0 or win_dec < 0:
        # Previously this redirected silently, so a mistyped bet looked like it
        # had been accepted. Re-render the page with the error instead.
        return _detail_response(
            request,
            hunt_id,
            session,
            error="Enter a game, a positive bet, and a win.",
            status_code=422,
        )

    bonus_svc.create_bonus(
        session,
        game_name=game,
        played_on=parse_date(played_on) or today_local(),
        bet=bet_dec,
        win=win_dec,
        notes=notes,
        notable=notable,
        hunt_id=hunt_id,
    )
    session.commit()
    return RedirectResponse(f"/hunts/{hunt_id}", status_code=303)


@router.get("/hunts/{hunt_id}/edit")
def edit_hunt_form(request: Request, hunt_id: int, session: Session = Depends(get_session)):
    hunt = session.get(Hunt, hunt_id)
    if hunt is None:
        return render(request, "not_found.html", {"what": "hunt"}, status_code=404)
    return render(request, "hunts/edit.html", {"hunt": hunt})


@router.post("/hunts/{hunt_id}")
def update_hunt(
    request: Request,
    hunt_id: int,
    session: Session = Depends(get_session),
    label: str = Form(""),
    hunt_date: str = Form(""),
    start_balance: str = Form(""),
    end_balance: str = Form(""),
    end_convention: str = Form("after_opening"),
    status: str = Form("open"),
    notes: str = Form(""),
):
    updated = hunt_svc.update_hunt(
        session,
        hunt_id,
        label=label,
        hunt_date=parse_date(hunt_date),
        start_balance=parse_decimal(start_balance, places=2),
        end_balance=parse_decimal(end_balance, places=2),
        end_convention=_convention(end_convention),
        status=status if status in ("open", "closed") else "open",
        notes=notes,
    )
    if updated is None:
        return render(request, "not_found.html", {"what": "hunt"}, status_code=404)
    session.commit()
    return RedirectResponse(f"/hunts/{hunt_id}", status_code=303)


@router.post("/hunts/{hunt_id}/delete")
def delete_hunt(request: Request, hunt_id: int, session: Session = Depends(get_session)):
    hunt_svc.delete_hunt(session, hunt_id)
    session.commit()
    return RedirectResponse("/hunts", status_code=303)


@router.post("/hunts/{hunt_id}/close")
def close_hunt(
    request: Request,
    hunt_id: int,
    session: Session = Depends(get_session),
    end_balance: str = Form(""),
    end_convention: str = Form("after_opening"),
):
    hunt_svc.close_hunt(
        session,
        hunt_id=hunt_id,
        end_balance=parse_decimal(end_balance, places=2),
        end_convention=_convention(end_convention),
    )
    session.commit()
    return RedirectResponse(f"/hunts/{hunt_id}", status_code=303)
