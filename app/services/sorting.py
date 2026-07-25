"""Shared, whitelisted table sorting.

Every sortable surface declares a mapping from a public sort key to either a SQL
column/expression (``order_by``) or a Python accessor (``sort_rows``). Keys are
whitelisted: an unknown or hand-edited ``?sort=`` falls back to the surface
default, so user input never reaches ``ORDER BY`` as text.

Conventions, applied everywhere so every table behaves the same:

* First click on a new column sorts high -> low; clicking the active column
  toggles direction.
* NULLs sort last in both directions. ``played_on`` and ``multiplier`` are
  nullable, and letting nulls flip position between asc/desc is disorienting.
* Every SQL sort appends a stable tiebreaker. Without one, offset pagination over
  tied values can repeat or skip rows between pages.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode


@dataclass(frozen=True)
class Sort:
    """The resolved sort state for one table."""

    key: str
    descending: bool

    @property
    def direction(self) -> str:
        return "desc" if self.descending else "asc"

    def next_direction(self, key: str) -> str:
        """Direction a header link for ``key`` should request.

        A new column starts high -> low (the interesting end for money and
        multipliers); the active column flips.
        """
        if key != self.key:
            return "desc"
        return "asc" if self.descending else "desc"

    def indicator(self, key: str) -> str:
        """Arrow shown in the header, empty for inactive columns."""
        if key != self.key:
            return ""
        return "▾" if self.descending else "▴"


def parse_sort(
    raw_key: str | None,
    raw_direction: str | None,
    *,
    allowed: Iterable[str],
    default_key: str,
    default_descending: bool = True,
) -> Sort:
    """Resolve query params into a Sort, falling back to the surface default."""
    key = raw_key if raw_key in set(allowed) else default_key
    if raw_direction in ("asc", "desc"):
        descending = raw_direction == "desc"
    else:
        descending = default_descending
    return Sort(key=key, descending=descending)


def order_by(sort: Sort, columns: Mapping[str, Any], *, tiebreaker: Any) -> list[Any]:
    """SQL ORDER BY terms: the chosen column (nulls last) then a stable tiebreaker."""
    column = columns[sort.key]
    primary = column.desc() if sort.descending else column.asc()
    return [primary.nullslast(), tiebreaker]


def sort_rows(
    rows: Sequence[Any],
    sort: Sort,
    keys: Mapping[str, Callable[[Any], Any]],
) -> list[Any]:
    """Sort already-materialized rows — for columns computed in Python (hunt
    cost/net/ROI, session running totals) that no SQL column corresponds to.

    Rows whose value is None are partitioned out and appended, so nulls stay last
    in both directions and None never has to compare against a Decimal.
    """
    accessor = keys[sort.key]
    present = [row for row in rows if accessor(row) is not None]
    missing = [row for row in rows if accessor(row) is None]
    present.sort(key=accessor, reverse=sort.descending)
    return present + missing


def query_url(path: str, params: Mapping[str, Any]) -> str:
    """Build a URL, dropping empty params so links stay readable."""
    clean = {key: value for key, value in params.items() if value not in (None, "")}
    return f"{path}?{urlencode(clean)}" if clean else path
