"""Reader interpretation logic, exercised with synthetic cell grids.

The real Slots.ods is gitignored and absent in CI, so these tests drive the
column-mapping, date handling, and notable-matching directly with hand-built
grids — no workbook needed. Layouts mirror the real file.
"""

from __future__ import annotations

from decimal import Decimal

from app.importer.normalize import build_alias_lookup
from app.importer.reader import (
    Cell,
    ReadResult,
    _map_columns,
    _read_bonus_rows,
    _read_notable,
)


def row(*values: object) -> list[Cell]:
    """Build a row of text cells; a (text, href) tuple attaches a hyperlink."""
    cells: list[Cell] = []
    for v in values:
        if isinstance(v, tuple):
            cells.append(Cell(text=v[0], href=v[1]))
        else:
            cells.append(Cell(text=str(v)))
    return cells


def test_map_columns_main_layout() -> None:
    # Game column has no header word (stray value); found as left-of-Date.
    header = row("0.1", "Date", "Bet", "Bonus Total", "X", "Notes:", "Average X")
    cols = _map_columns(header)
    assert (cols.game, cols.date, cols.bet, cols.win, cols.notes) == (0, 1, 2, 3, 5)


def test_map_columns_hunt_layout() -> None:
    header = row("Slot", "Bet", "Win", "X win", "Notes")
    cols = _map_columns(header)
    assert cols.game == 0
    assert cols.bet == 1
    assert cols.win == 2  # exact "Win", not the "X win" column
    assert cols.date is None  # hunts have no date column


def test_read_main_rows_have_dates_and_suspect_flag() -> None:
    grid = [
        row("0.1", "Date", "Bet", "Bonus Total", "X", "Notes:"),
        row("Sugar Rush", "12/3/2021", "0.20", "40.00", "200", "nice"),
        row("Old Game", "6/1/2012", "0.10", "5.00", "50", ""),  # pre-2021 -> suspect
    ]
    result = ReadResult()
    recs = _read_bonus_rows(grid, "main", result, "Slot Bonuses")
    assert len(recs) == 2
    assert recs[0].played_on is not None and recs[0].bet == Decimal("0.2000")
    assert recs[0].date_suspect is False
    assert recs[1].date_suspect is True


def test_read_hunt_rows_have_no_date() -> None:
    grid = [
        row("Slot", "Bet", "Win", "X win", "Notes"),
        row("Densho", "0.40", "160.00", "400", "big"),
        row("", "84.35", "67.1"),  # summary row, no game -> skipped
    ]
    result = ReadResult()
    recs = _read_bonus_rows(grid, "hunt:1", result, "Bonus Hunt 1", hunt_ref="hunt:1")
    assert len(recs) == 1
    assert recs[0].played_on is None
    assert recs[0].hunt_ref == "hunt:1"
    assert recs[0].win == Decimal("160.00")


def test_notable_matches_main_else_standalone() -> None:
    from app.importer.records import BonusRecord

    lookup = build_alias_lookup()
    main = [
        BonusRecord("main:1", "Bloodthirst", None, Decimal("0.1000"), Decimal("100.00")),
    ]
    grid = [
        # matches main on (game, bet, win) -> flags it, attaches replay url
        row(("Replay", "https:/rec/x"), "Boodthirst", "$0.10", "100"),
        # no match -> standalone notable, no date
        row(("Replay", "https:/rec/y"), "Folsom Prison", "$0.20", "483.84"),
    ]
    result = ReadResult()
    _read_notable(grid, "Notable hits", main, result, lookup)

    assert main[0].notable is True
    assert main[0].replay_url == "https://rec/x"  # repaired scheme
    standalone = [b for b in result.bonuses if b.import_ref.startswith("notable:")]
    assert len(standalone) == 1
    assert standalone[0].game_name == "Folsom Prison"
    assert standalone[0].played_on is None
    assert standalone[0].notable is True
