"""Pure normalization helpers for the importer.

No I/O, no database — every function here is deterministic and unit-tested.
"""

from __future__ import annotations

import re
from datetime import date

from app.importer.aliases import ALIAS_MAP

# Rows dated before this year are almost certainly typos (2002/2011/2012 in the
# source). Flagged, never corrected.
SUSPECT_BEFORE_YEAR = 2021

_WHITESPACE = re.compile(r"\s+")
# odfpy normalizes "https://" to "https:/" (and "http://" to "http:/") when it
# writes hrefs back out; repair the collapsed slash before storing.
_COLLAPSED_SCHEME = re.compile(r"^(https?):/(?!/)", re.IGNORECASE)


def normalize_name(raw: str) -> str:
    """Trim and collapse internal whitespace runs to a single space."""
    return _WHITESPACE.sub(" ", raw).strip()


def build_alias_lookup(alias_map: dict[str, str] = ALIAS_MAP) -> dict[str, str]:
    """Normalized raw spelling -> canonical name.

    Normalizing the keys means the double-spaced source spellings match whatever
    the cell actually contained.
    """
    return {normalize_name(raw): canonical for raw, canonical in alias_map.items()}


def canonical_game_name(raw: str, lookup: dict[str, str]) -> str:
    """Resolve a raw game cell to its canonical name via the alias lookup."""
    name = normalize_name(raw)
    return lookup.get(name, name)


def repair_replay_url(url: str | None) -> str | None:
    """Repair the ``https:/`` scheme odfpy leaves behind. Returns None for
    empty/blank input."""
    if url is None:
        return None
    trimmed = url.strip()
    if not trimmed:
        return None
    return _COLLAPSED_SCHEME.sub(r"\1://", trimmed)


def is_date_suspect(played_on: date) -> bool:
    """True when the year predates the tracked era (see SUSPECT_BEFORE_YEAR)."""
    return played_on.year < SUSPECT_BEFORE_YEAR
