"""Pure sort-helper behaviour: whitelisting, toggling, null placement, URLs.

The whitelist is the security-relevant part — a sort key is interpolated into
ORDER BY, so an unrecognized key must never reach SQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.sorting import Sort, parse_sort, query_url, sort_rows

ALLOWED = ("date", "win", "x")


def test_unknown_sort_key_falls_back_to_default() -> None:
    # A hand-edited or injected key must not survive into ORDER BY.
    for hostile in ("win; DROP TABLE bonus", "../../etc", "", None, "nope"):
        resolved = parse_sort(hostile, "desc", allowed=ALLOWED, default_key="date")
        assert resolved.key == "date"


def test_known_key_and_direction_are_honoured() -> None:
    assert parse_sort("win", "asc", allowed=ALLOWED, default_key="date") == Sort("win", False)
    assert parse_sort("win", "desc", allowed=ALLOWED, default_key="date") == Sort("win", True)


def test_bad_direction_uses_surface_default() -> None:
    ascending = parse_sort(
        "win", "sideways", allowed=ALLOWED, default_key="date", default_descending=False
    )
    assert ascending.descending is False
    descending = parse_sort(
        "win", None, allowed=ALLOWED, default_key="date", default_descending=True
    )
    assert descending.descending is True


def test_new_column_starts_descending_active_column_toggles() -> None:
    active = Sort(key="win", descending=True)
    assert active.next_direction("x") == "desc"  # first click on another column
    assert active.next_direction("win") == "asc"  # active column flips
    assert Sort("win", False).next_direction("win") == "desc"


def test_indicator_only_marks_the_active_column() -> None:
    active = Sort(key="win", descending=True)
    assert active.indicator("win") == "▾"
    assert Sort("win", False).indicator("win") == "▴"
    assert active.indicator("date") == ""


@dataclass
class Row:
    value: Decimal | None


def test_sort_rows_keeps_nulls_last_in_both_directions() -> None:
    rows = [Row(Decimal(2)), Row(None), Row(Decimal(9)), Row(None), Row(Decimal(5))]
    keys = {"value": lambda r: r.value}

    descending = sort_rows(rows, Sort("value", True), keys)
    assert [r.value for r in descending] == [Decimal(9), Decimal(5), Decimal(2), None, None]

    ascending = sort_rows(rows, Sort("value", False), keys)
    assert [r.value for r in ascending] == [Decimal(2), Decimal(5), Decimal(9), None, None]


def test_sort_rows_never_compares_none_to_decimal() -> None:
    # Would raise TypeError if None reached the comparison.
    rows = [Row(None), Row(Decimal(1))]
    assert len(sort_rows(rows, Sort("value", True), {"value": lambda r: r.value})) == 2


def test_query_url_drops_empty_params() -> None:
    url = query_url("/log", {"q": "bass", "bet": "", "band": None, "sort": "win"})
    assert url == "/log?q=bass&sort=win"
    assert query_url("/log", {"q": ""}) == "/log"
