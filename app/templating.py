"""Jinja templating, formatting filters, and the single HX-Request branch.

Every surface template does ``{% extends layout %}``. ``render`` picks the layout
— the full shell for a normal request, a bare pass-through for an HTMX request —
so the partial-vs-page decision lives in exactly one place (CLAUDE.md style).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse

from app.config import settings

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_LOCAL_TZ = ZoneInfo(settings.tz)

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def is_hx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def today_local() -> date:
    """Today in the app timezone — for defaulting the entry-form date."""
    return datetime.now(_LOCAL_TZ).date()


def render(
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    ctx = dict(context or {})
    ctx["layout"] = "_partial.html" if is_hx(request) else "base.html"
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


# --------------------------------------------------------------------------- #
# formatting filters
# --------------------------------------------------------------------------- #
def money(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


def signed_money(value: Decimal | None) -> str:
    """Signed currency for net/profit figures: -$26.00, $0.00, $1,200.00."""
    if value is None:
        return "—"
    if value < 0:
        return f"-${-value:,.2f}"
    return f"${value:,.2f}"


def multiplier(value: Decimal | float | None) -> str:
    if value is None:
        return "—"
    dec = Decimal(str(value)).quantize(Decimal("0.01"))
    text = format(dec, "f").rstrip("0").rstrip(".")
    return f"{text}x"


def local_date(value: date | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%b %d, %Y")


def local_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is not None:
        value = value.astimezone(_LOCAL_TZ)
    return value.strftime("%b %d, %Y %I:%M %p")


templates.env.filters["money"] = money
templates.env.filters["signed_money"] = signed_money
templates.env.filters["multiplier"] = multiplier
templates.env.filters["local_date"] = local_date
templates.env.filters["local_datetime"] = local_datetime
