"""Game stats surface: searchable/sortable list, per-game detail, merge/alias."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.services import games as game_svc
from app.services.sorting import parse_sort, query_url
from app.templating import render

router = APIRouter()


@router.get("/games")
def games(
    request: Request,
    session: Session = Depends(get_session),
    q: str = "",
    sort: str = "",
    direction: str = Query("", alias="dir"),
    offset: int = 0,
):
    active_sort = parse_sort(
        sort,
        direction,
        allowed=game_svc.GAME_SORTS,
        default_key=game_svc.DEFAULT_GAME_SORT.key,
        default_descending=game_svc.DEFAULT_GAME_SORT.descending,
    )
    page = game_svc.game_stats(
        session, q=q or None, sort=active_sort, limit=50, offset=max(offset, 0)
    )
    filters = {"q": q}
    ctx = {
        "page": page,
        "names": game_svc.all_game_names(session),
        "filters": filters,
        "sort": active_sort,
        # A header click resets to page 1; paging preserves the active sort.
        "sort_url": lambda key: _games_url(filters, 0, key, active_sort.next_direction(key)),
        "prev_url": _games_url(
            filters, max(page.offset - page.limit, 0), active_sort.key, active_sort.direction
        )
        if page.offset > 0
        else None,
        "next_url": _games_url(filters, page.next_offset, active_sort.key, active_sort.direction)
        if page.has_next
        else None,
    }
    return render(request, "games.html", ctx)


# Registered before /games/{game_id}: that route parses its path segment as an
# int, so "merges" would be rejected as invalid rather than falling through.
@router.get("/games/merges")
def merge_suggestions(request: Request, session: Session = Depends(get_session)):
    suggestions = game_svc.suggest_merges(session)
    ctx = {
        "certain": [s for s in suggestions if s.certain],
        "likely": [s for s in suggestions if not s.certain],
    }
    return render(request, "games/merges.html", ctx)


@router.post("/games/merges")
def apply_merge_suggestion(
    request: Request,
    session: Session = Depends(get_session),
    source: str = Form(""),
    target: str = Form(""),
):
    src = game_svc.game_by_name(session, source)
    dst = game_svc.game_by_name(session, target)
    if src is not None and dst is not None:
        game_svc.merge_games(session, src.id, dst.id)
        session.commit()
    # Back to the suggestions list so several merges can be worked through.
    return RedirectResponse("/games/merges", status_code=303)


@router.get("/games/{game_id}")
def game_detail(request: Request, game_id: int, session: Session = Depends(get_session)):
    detail = game_svc.game_detail(session, game_id)
    if detail is None:
        return render(request, "not_found.html", {"what": "game"}, status_code=404)
    return render(request, "games/detail.html", {"d": detail})


@router.post("/games/merge")
def merge_games(
    request: Request,
    session: Session = Depends(get_session),
    source: str = Form(...),
    target: str = Form(...),
):
    src = game_svc.game_by_name(session, source)
    dst = game_svc.game_by_name(session, target)
    if src is not None and dst is not None:
        game_svc.merge_games(session, src.id, dst.id)
        session.commit()
    return RedirectResponse("/games", status_code=303)


@router.post("/games/alias")
def add_alias(
    request: Request,
    session: Session = Depends(get_session),
    alias: str = Form(...),
    game: str = Form(...),
):
    target = game_svc.game_by_name(session, game)
    if target is not None:
        game_svc.add_alias(session, alias, target.id)
        session.commit()
    return RedirectResponse("/games", status_code=303)


def _games_url(filters: dict[str, str], offset: int, sort_key: str, direction: str) -> str:
    params: dict[str, Any] = dict(filters)
    params["sort"] = sort_key
    params["dir"] = direction
    if offset:
        params["offset"] = offset
    return query_url("/games", params)
