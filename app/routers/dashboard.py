"""Dashboard surface."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.routers.params import parse_date
from app.services.dashboard import (
    BET_SORTS,
    DEFAULT_BET_SORT,
    DEFAULT_YEAR_SORT,
    YEAR_SORTS,
    build_dashboard,
)
from app.services.sorting import parse_sort, query_url, sort_rows
from app.templating import render, today_local

router = APIRouter()


def _periods(today: date) -> list[tuple[str, date | None, date | None]]:
    """Quick date ranges, resolved to real dates so the filter has a single
    representation rather than a mix of presets and explicit bounds."""
    return [
        ("All time", None, None),
        ("This month", date(today.year, today.month, 1), today),
        ("This year", date(today.year, 1, 1), today),
        ("Last 30 days", today - timedelta(days=30), today),
    ]


@router.get("/dashboard")
def dashboard(
    request: Request,
    session: Session = Depends(get_session),
    date_from: str = "",
    date_to: str = "",
    ysort: str = "",
    ydir: str = "",
    bsort: str = "",
    bdir: str = "",
):
    parsed_from = parse_date(date_from)
    parsed_to = parse_date(date_to)
    data = build_dashboard(session, date_from=parsed_from, date_to=parsed_to)
    max_band = max((b.count for b in data.distribution), default=0)
    max_month = max((m.total_win for m in data.by_month), default=0)

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

    span = {
        "date_from": date_from,
        "date_to": date_to,
    }

    def _url(**overrides: str) -> str:
        params = {
            **span,
            "ysort": year_sort.key,
            "ydir": year_sort.direction,
            "bsort": bet_sort.key,
            "bdir": bet_sort.direction,
            **overrides,
        }
        return query_url("/dashboard", params)

    periods = [
        {
            "label": label,
            "url": _url(
                date_from=start.isoformat() if start else "",
                date_to=end.isoformat() if end else "",
            ),
            "active": parsed_from == start and parsed_to == end,
        }
        for label, start, end in _periods(today_local())
    ]

    ctx = {
        "d": data,
        "max_band": max_band,
        "max_month": max_month,
        "periods": periods,
        "filters": span,
        "year_sort": year_sort,
        "bet_sort": bet_sort,
        "year_sort_url": lambda key: _url(ysort=key, ydir=year_sort.next_direction(key)),
        "bet_sort_url": lambda key: _url(bsort=key, bdir=bet_sort.next_direction(key)),
    }
    return render(request, "dashboard.html", ctx)
