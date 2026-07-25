"""Dashboard surface."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.services.dashboard import (
    BET_SORTS,
    DEFAULT_BET_SORT,
    DEFAULT_YEAR_SORT,
    YEAR_SORTS,
    build_dashboard,
)
from app.services.sorting import parse_sort, query_url, sort_rows
from app.templating import render

router = APIRouter()


@router.get("/dashboard")
def dashboard(
    request: Request,
    session: Session = Depends(get_session),
    ysort: str = "",
    ydir: str = "",
    bsort: str = "",
    bdir: str = "",
):
    data = build_dashboard(session)
    max_band = max((b.count for b in data.distribution), default=0)

    # Two independent tables on one page, so each carries its own sort params.
    year_sort = parse_sort(
        ysort,
        ydir,
        allowed=YEAR_SORTS,
        default_key=DEFAULT_YEAR_SORT.key,
        default_descending=DEFAULT_YEAR_SORT.descending,
    )
    bet_sort = parse_sort(
        bsort,
        bdir,
        allowed=BET_SORTS,
        default_key=DEFAULT_BET_SORT.key,
        default_descending=DEFAULT_BET_SORT.descending,
    )
    data.by_year = sort_rows(data.by_year, year_sort, YEAR_SORTS)
    data.by_bet = sort_rows(data.by_bet, bet_sort, BET_SORTS)

    def year_url(key: str) -> str:
        return query_url(
            "/dashboard",
            {
                "ysort": key,
                "ydir": year_sort.next_direction(key),
                "bsort": bet_sort.key,
                "bdir": bet_sort.direction,
            },
        )

    def bet_url(key: str) -> str:
        return query_url(
            "/dashboard",
            {
                "bsort": key,
                "bdir": bet_sort.next_direction(key),
                "ysort": year_sort.key,
                "ydir": year_sort.direction,
            },
        )

    ctx = {
        "d": data,
        "max_band": max_band,
        "year_sort": year_sort,
        "bet_sort": bet_sort,
        "year_sort_url": year_url,
        "bet_sort_url": bet_url,
    }
    return render(request, "dashboard.html", ctx)
