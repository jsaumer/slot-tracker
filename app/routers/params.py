"""Small, forgiving parsers for form/query strings -> typed values."""

from __future__ import annotations

from datetime import date
from decimal import Decimal


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
