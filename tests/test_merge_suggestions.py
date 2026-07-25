"""Duplicate-game detection.

The sequel guard carries the most weight here. "Money Train 2" and "Money Train 3"
score ~0.95 similarity, and merging them would silently destroy real data — the
build brief is explicit that sequels stay distinct.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.bonuses import create_bonus
from app.services.games import are_distinct_sequels, suggest_merges
from tests.support import make_sessionmaker


def _add(session, name: str, times: int = 1) -> None:
    for _ in range(times):
        create_bonus(
            session,
            game_name=name,
            played_on=date(2024, 1, 1),
            bet=Decimal("0.20"),
            win=Decimal("10.00"),
        )


def _pairs(suggestions) -> set[frozenset[str]]:
    return {frozenset((s.source.name, s.target.name)) for s in suggestions}


# --------------------------------------------------------------------------- #
# the sequel guard
# --------------------------------------------------------------------------- #
def test_numbered_sequels_are_distinct() -> None:
    assert are_distinct_sequels("Money Train 2", "Money Train 3") is True
    assert are_distinct_sequels("Punk Rocker 2", "Punk Rocker 3") is True


def test_base_game_and_its_sequel_are_distinct() -> None:
    assert are_distinct_sequels("Big Bass", "Big Bass 2") is True
    assert are_distinct_sequels("Chaos Crew 2", "Chaos Crew") is True


def test_roman_and_arabic_forms_of_the_same_sequel_are_not_distinct() -> None:
    """Roman and arabic spellings of one sequel are the same game (Chaos Crew II
    == Chaos Crew 2), so they must remain eligible as a duplicate suggestion."""
    assert are_distinct_sequels("Chaos Crew II", "Chaos Crew 2") is False
    assert are_distinct_sequels("xWays Hoarder II", "xWays Hoarder 2") is False


def test_unrelated_names_are_not_treated_as_sequels() -> None:
    assert are_distinct_sequels("Sugar Rush", "Sugar RUsh") is False
    assert are_distinct_sequels("Fruitz", "Frutz") is False


# --------------------------------------------------------------------------- #
# suggestions
# --------------------------------------------------------------------------- #
def test_certain_tier_catches_case_space_and_punctuation_variants() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _add(s, "Stack'Em", 3)
        _add(s, "Stack'em", 1)
        _add(s, "Hop'n'Pop", 2)
        _add(s, "Hop 'n' Pop", 1)
        s.commit()

        certain = [x for x in suggest_merges(s) if x.certain]
        assert _pairs(certain) == {
            frozenset(("Stack'Em", "Stack'em")),
            frozenset(("Hop'n'Pop", "Hop 'n' Pop")),
        }
        assert all(x.similarity == Decimal("1.0") for x in certain)


def test_survivor_defaults_to_the_more_used_spelling() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _add(s, "Sugar Rush", 9)
        _add(s, "Sugar RUsh", 2)
        s.commit()

        suggestion = next(x for x in suggest_merges(s) if "Sugar" in x.target.name)
        assert suggestion.target.name == "Sugar Rush"
        assert suggestion.target.count == 9
        assert suggestion.source.name == "Sugar RUsh"
        assert suggestion.source.count == 2


def test_likely_tier_finds_typos_including_a_bad_first_character() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _add(s, "Legacy of Dead", 5)
        _add(s, ":egacy of Dead", 1)  # real spelling from the source data
        s.commit()

        assert frozenset(("Legacy of Dead", ":egacy of Dead")) in _pairs(suggest_merges(s))


def test_sequels_are_never_suggested() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _add(s, "Money Train 2", 5)
        _add(s, "Money Train 3", 4)
        _add(s, "Money Train 4", 3)
        s.commit()

        assert suggest_merges(s) == []


def test_distinct_games_produce_no_suggestions() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _add(s, "Big Bass")
        _add(s, "Gates of Olympus")
        _add(s, "Wanted Dead or Wild")
        s.commit()

        assert suggest_merges(s) == []


def test_limit_is_respected() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        for i in range(8):
            _add(s, f"Game Alpha {chr(97 + i)}")
            _add(s, f"Game Alpha {chr(97 + i).upper()}")
        s.commit()

        assert len(suggest_merges(s, limit=3)) <= 3
