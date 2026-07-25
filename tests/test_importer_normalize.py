"""Pure importer helpers: alias folding, URL repair, suspect dates."""

from __future__ import annotations

from datetime import date

import pytest

from app.importer.normalize import (
    build_alias_lookup,
    canonical_game_name,
    is_date_suspect,
    normalize_name,
    repair_replay_url,
)

LOOKUP = build_alias_lookup()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Sugar RUsh", "Sugar Rush"),
        ("Choas Crew", "Chaos Crew"),
        ("Chaos Crew II", "Chaos Crew 2"),
        (":egacy of Dead", "Legacy of Dead"),
        ("Money train 2", "Money Train 2"),
        ("Hop'n'Pop", "Hop 'n' Pop"),
        # Double internal space in the source spelling still resolves.
        ("Hand of  Anubus", "Hand of Anubus"),
        ("Hand of Anubis", "Hand of Anubus"),
        ("Hanf of Anubus", "Hand of Anubus"),
        # Surrounding whitespace is trimmed before lookup.
        ("  Denscho  ", "Densho"),
        # Unknown names pass through, only normalized.
        ("Gates of Olympus", "Gates of Olympus"),
        ("  Big   Bass  ", "Big Bass"),
    ],
)
def test_canonical_game_name(raw: str, expected: str) -> None:
    assert canonical_game_name(raw, LOOKUP) == expected


def test_sequels_stay_distinct() -> None:
    assert canonical_game_name("Money Train 3", LOOKUP) == "Money Train 3"
    assert canonical_game_name("Big Bass", LOOKUP) != canonical_game_name("Bigger Bass", LOOKUP)


def test_normalize_collapses_whitespace() -> None:
    assert normalize_name("  a   b\tc ") == "a b c"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https:/rec.example.com/abc", "https://rec.example.com/abc"),
        ("http:/rec.example.com/abc", "http://rec.example.com/abc"),
        ("https://already.good/x", "https://already.good/x"),
        ("  https:/trim.me/x  ", "https://trim.me/x"),
        ("", None),
        (None, None),
    ],
)
def test_repair_replay_url(raw: str | None, expected: str | None) -> None:
    assert repair_replay_url(raw) == expected


@pytest.mark.parametrize(
    ("year", "suspect"),
    [(2002, True), (2011, True), (2012, True), (2020, True), (2021, False), (2026, False)],
)
def test_is_date_suspect(year: int, suspect: bool) -> None:
    assert is_date_suspect(date(year, 6, 1)) is suspect
