"""Add-bonus (hot path) and the log view."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.routers.params import log_filters, parse_date, parse_decimal
from app.services import bonuses as bonus_svc
from app.services.bands import BANDS
from app.services.games import all_game_names
from app.services.sorting import parse_sort, query_url
from app.templating import is_hx, money, multiplier, render, today_local

router = APIRouter()


def _add_context(
    session: Session, flash: str | None = None, error: str | None = None
) -> dict[str, Any]:
    return {
        "games": all_game_names(session),
        "last_bet": bonus_svc.last_bet(session),
        "today": today_local().isoformat(),
        "flash": flash,
        "error": error,
    }


@router.get("/")
def add_form(request: Request, session: Session = Depends(get_session)):
    return render(request, "bonuses/add.html", _add_context(session))


@router.post("/bonus")
def add_bonus(
    request: Request,
    session: Session = Depends(get_session),
    # Defaulted rather than Form(...) on purpose: an empty value for a required
    # field never reaches the handler, so FastAPI answers with raw JSON instead of
    # the rendered error below. The handler validates everything itself.
    game: str = Form(""),
    bet: str = Form(""),
    win: str = Form(""),
    played_on: str = Form(""),
    cost: str = Form(""),
    bought: bool = Form(False),
    notes: str = Form(""),
    notable: bool = Form(False),
):
    bet_dec = parse_decimal(bet, places=4)
    win_dec = parse_decimal(win, places=2)
    day = parse_date(played_on) or today_local()

    if not game.strip() or bet_dec is None or win_dec is None or bet_dec <= 0 or win_dec < 0:
        ctx = _add_context(session, error="Enter a game, a positive bet, and a win.")
        return render(request, "bonuses/add.html", ctx, status_code=422)

    bonus = bonus_svc.create_bonus(
        session,
        game_name=game,
        played_on=day,
        bet=bet_dec,
        win=win_dec,
        cost=parse_decimal(cost, places=2),
        # App-entered rows are always explicit about provenance; only imported rows
        # stay NULL/unknown.
        bought=bought,
        notes=notes,
        notable=notable,
    )
    session.commit()

    flash = (
        f"Added {game.strip()} — {money(win_dec)} on {money(bet_dec)} "
        f"({multiplier(bonus.multiplier)})"
    )
    if is_hx(request):
        return render(request, "bonuses/add.html", _add_context(session, flash=flash))
    return RedirectResponse("/", status_code=303)


@router.get("/bonus/{bonus_id}/edit")
def edit_form(request: Request, bonus_id: int, session: Session = Depends(get_session)):
    bonus = bonus_svc.get_bonus(session, bonus_id)
    if bonus is None:
        return render(request, "not_found.html", {"what": "bonus"}, status_code=404)
    ctx = {
        "bonus": bonus,
        "game_name": bonus.game.name,
        "games": all_game_names(session),
    }
    return render(request, "bonuses/edit.html", ctx)


@router.post("/bonus/{bonus_id}")
def update_bonus(
    request: Request,
    bonus_id: int,
    session: Session = Depends(get_session),
    game: str = Form(""),
    bet: str = Form(""),
    win: str = Form(""),
    played_on: str = Form(""),
    cost: str = Form(""),
    bought: bool = Form(False),
    notes: str = Form(""),
    replay_url: str = Form(""),
    notable: bool = Form(False),
):
    bonus = bonus_svc.get_bonus(session, bonus_id)
    if bonus is None:
        return render(request, "not_found.html", {"what": "bonus"}, status_code=404)

    bet_dec = parse_decimal(bet, places=4)
    win_dec = parse_decimal(win, places=2)
    if not game.strip() or bet_dec is None or win_dec is None or bet_dec <= 0 or win_dec < 0:
        ctx = {
            "bonus": bonus,
            "game_name": game,
            "games": all_game_names(session),
            "error": "Enter a game, a positive bet, and a win.",
        }
        return render(request, "bonuses/edit.html", ctx, status_code=422)

    bonus_svc.update_bonus(
        session,
        bonus_id,
        game_name=game,
        played_on=parse_date(played_on),
        bet=bet_dec,
        win=win_dec,
        cost=parse_decimal(cost, places=2),
        bought=bought,
        notes=notes,
        replay_url=replay_url,
        notable=notable,
    )
    session.commit()
    return RedirectResponse("/log", status_code=303)


@router.post("/bonus/{bonus_id}/delete")
def delete_bonus(
    request: Request,
    bonus_id: int,
    session: Session = Depends(get_session),
):
    bonus_svc.delete_bonus(session, bonus_id)
    session.commit()
    return RedirectResponse("/log", status_code=303)


@router.get("/log")
def log(
    request: Request,
    session: Session = Depends(get_session),
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    bet: str = "",
    band: str = "",
    notable: bool = False,
    suspect: bool = False,
    has_replay: bool = False,
    provenance: str = "",
    sort: str = "",
    direction: str = Query("", alias="dir"),
    offset: int = 0,
):
    active_sort = parse_sort(
        sort,
        direction,
        allowed=bonus_svc.LOG_SORTS,
        default_key=bonus_svc.DEFAULT_LOG_SORT.key,
        default_descending=bonus_svc.DEFAULT_LOG_SORT.descending,
    )
    page = bonus_svc.query_log(
        session,
        filters=log_filters(
            q=q,
            date_from=date_from,
            date_to=date_to,
            bet=bet,
            band=band,
            notable=notable,
            suspect=suspect,
            has_replay=has_replay,
            provenance=provenance,
        ),
        sort=active_sort,
        limit=50,
        offset=max(offset, 0),
    )
    filters = {
        "q": q,
        "date_from": date_from,
        "date_to": date_to,
        "bet": bet,
        "band": band,
        "notable": "1" if notable else "",
        "suspect": "1" if suspect else "",
        "has_replay": "1" if has_replay else "",
        "provenance": provenance if provenance in bonus_svc.PROVENANCE else "",
    }
    ctx = {
        "page": page,
        "bands": BANDS,
        "filters": filters,
        "sort": active_sort,
        # Export what is on screen, not the whole table.
        "export_url": query_url("/export", filters),
        # A header click resets to page 1; paging preserves the active sort.
        "sort_url": lambda key: _log_url(filters, 0, key, active_sort.next_direction(key)),
        "prev_url": _log_url(
            filters, max(page.offset - page.limit, 0), active_sort.key, active_sort.direction
        )
        if page.offset > 0
        else None,
        "next_url": _log_url(filters, page.next_offset, active_sort.key, active_sort.direction)
        if page.has_next
        else None,
    }
    return render(request, "bonuses/log.html", ctx)


def _log_url(filters: dict[str, str], offset: int, sort_key: str, direction: str) -> str:
    params: dict[str, Any] = dict(filters)
    params["sort"] = sort_key
    params["dir"] = direction
    if offset:
        params["offset"] = offset
    return query_url("/log", params)
