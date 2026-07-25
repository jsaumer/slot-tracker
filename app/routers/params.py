"""Small, forgiving parsers for form/query strings -> typed values."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.bonuses import LogFilters


def log_filters(
    *,
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    bet: str = "",
    band: str = "",
    notable: bool = False,
    suspect: bool = False,
    has_replay: bool = False,
) -> LogFilters:
    """Raw query strings -> typed LogFilters. Shared by the log view and the CSV
    export so the two can never drift apart."""
    return LogFilters(
        q=q or None,
        date_from=parse_date(date_from),
        date_to=parse_date(date_to),
        bet=parse_decimal(bet, places=4),
        band=band or None,
        notable=notable,
        suspect=suspect,
        has_replay=has_replay,
    )


def parse_decimal(raw: str | None, places: int | None = None) -> Decimal | None:
    if raw is None:
        return None
    cleaned = raw.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except Exception:
        return None
    if places is not None:
        value = value.quantize(Decimal(10) ** -places)
    return value


def parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def parse_int(raw: str | None) -> int | None:
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None
