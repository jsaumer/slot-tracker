"""Read Slots.ods into plain records.

The workbook is walked with odfpy directly (rather than pandas) so cell values
and embedded replay hyperlinks come out of a single pass. Cell numbers are read
from the ``office:value`` attribute — never displayed text — so money stays exact.

Three real layouts, learned from the actual file:

- **Slot Bonuses** (main log): the game column has *no* header word — its header
  cell holds a stray value — so the header row is found by "Bet" + "Date" and the
  game column is taken as the one immediately left of Date. Money column is
  headed "Bonus Total". Dates present.
- **Bonus Hunt N**: headed Slot / Bet / Win / X win / Notes, **no date column**;
  Start/End balances sit in labelled cells to the right of the first rows. Hunt
  sheet names may carry a suffix ("Bonus Hunt 18 - Hacksaw10c only"), so the
  number is matched as a prefix. spin_end convention for hunt 27 only.
- **Notable hits**: no header; fixed columns replay-link / game / bet / win, no
  date. Each row is matched to a main-log bonus by (game, bet, win); unmatched
  ones are inserted standalone with notable=True.

Anything unparseable is skipped and reported as a warning, never guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from odf.opendocument import load
from odf.table import Table, TableCell, TableRow
from odf.teletype import extractText
from odf.text import A

from app.importer.normalize import (
    build_alias_lookup,
    canonical_game_name,
    is_date_suspect,
    repair_replay_url,
)
from app.importer.records import BonusRecord, HuntRecord

MAIN_SHEET = "Slot Bonuses"
SPIN_END_HUNT = 27
_MAX_COLS = 64
_MAX_BLANK_ROWS = 25

_HUNT_RE = re.compile(r"bonus\s*hunt\s*(\d+)", re.IGNORECASE)
_NOTABLE_RE = re.compile(r"notable", re.IGNORECASE)
_DATE_FORMATS = ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%d/%m/%Y")

# Notable-hits fixed columns.
_NB_GAME, _NB_BET, _NB_WIN = 1, 2, 3


@dataclass
class Cell:
    text: str = ""
    href: str | None = None
    value: str | None = None  # office:value (numeric), as string
    date_value: str | None = None  # office:date-value


@dataclass
class Columns:
    game: int | None = None
    date: int | None = None
    bet: int | None = None
    win: int | None = None
    notes: int | None = None


@dataclass
class ReadResult:
    hunts: list[HuntRecord] = field(default_factory=list)
    bonuses: list[BonusRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def read_workbook(path: str) -> ReadResult:
    doc = load(path)
    grids = {_sheet_name(t): _read_table(t) for t in doc.getElementsByType(Table)}
    result = ReadResult()
    lookup = build_alias_lookup()

    main = grids.get(MAIN_SHEET)
    if main is None:
        result.warnings.append(f"main sheet {MAIN_SHEET!r} not found")
        main_records: list[BonusRecord] = []
    else:
        main_records = _read_bonus_rows(main, "main", result, MAIN_SHEET)
    result.bonuses.extend(main_records)

    for name, grid in grids.items():
        match = _HUNT_RE.match(name.strip())
        if not match:
            continue
        number = int(match.group(1))
        rows = _read_bonus_rows(grid, f"hunt:{number}", result, name, hunt_ref=f"hunt:{number}")
        result.bonuses.extend(rows)
        result.hunts.append(_build_hunt(number, grid, rows))

    for name, grid in grids.items():
        if _NOTABLE_RE.search(name):
            _read_notable(grid, name, main_records, result, lookup)

    return result


# --------------------------------------------------------------------------- #
# odf grid extraction
# --------------------------------------------------------------------------- #
def _sheet_name(table: Table) -> str:
    return table.getAttribute("name") or ""


def _read_table(table: Table) -> list[list[Cell]]:
    grid: list[list[Cell]] = []
    blank_run = 0
    for row in table.getElementsByType(TableRow):
        repeat = _int_attr(row, "numberrowsrepeated", 1)
        cells = _read_row(row)
        is_blank = all(not c.text and c.value is None for c in cells)
        span = 1 if is_blank else min(repeat, 8)
        for _ in range(span):
            grid.append(cells)
        if is_blank:
            blank_run += span
            if blank_run > _MAX_BLANK_ROWS:
                break
        else:
            blank_run = 0
    return grid


def _read_row(row: TableRow) -> list[Cell]:
    cells: list[Cell] = []
    for tc in row.getElementsByType(TableCell):
        repeat = _int_attr(tc, "numbercolumnsrepeated", 1)
        cell = Cell(
            text=extractText(tc).strip(),
            href=_first_href(tc),
            value=tc.getAttribute("value"),
            date_value=tc.getAttribute("datevalue"),
        )
        is_empty = not cell.text and cell.value is None and cell.date_value is None
        span = 1 if (is_empty and repeat > _MAX_COLS) else min(repeat, _MAX_COLS)
        cells.extend(cell for _ in range(span))
        if len(cells) >= _MAX_COLS:
            break
    return cells


def _first_href(tc: TableCell) -> str | None:
    for anchor in tc.getElementsByType(A):
        href = anchor.getAttribute("href")
        if href:
            return href
    return None


def _int_attr(element: object, name: str, default: int) -> int:
    raw = element.getAttribute(name)  # type: ignore[attr-defined]
    if raw is None:
        return default
    try:
        return int(raw)
    except Exception:
        return default


# --------------------------------------------------------------------------- #
# header / column mapping
# --------------------------------------------------------------------------- #
def _find_header(grid: list[list[Cell]]) -> tuple[int | None, Columns]:
    """The header row has a 'Bet' column plus either 'Date' (main) or 'Win' (hunt)."""
    for idx, row in enumerate(grid):
        texts = [c.text.lower() for c in row]
        has_bet = any("bet" in t for t in texts)
        has_date = any("date" in t for t in texts)
        has_win = any(t == "win" or "total" in t for t in texts)
        if has_bet and (has_date or has_win):
            return idx, _map_columns(row)
    return None, Columns()


def _map_columns(header: list[Cell]) -> Columns:
    cols = Columns()
    for i, cell in enumerate(header):
        t = cell.text.lower().strip()
        if "date" in t and cols.date is None:
            cols.date = i
        elif "bet" in t and cols.bet is None:
            cols.bet = i
        elif (t == "win" or "total" in t) and cols.win is None:
            cols.win = i
        elif ("slot" in t or "game" in t) and cols.game is None:
            cols.game = i
        elif ("note" in t or "comment" in t) and cols.notes is None:
            cols.notes = i
    # Main log's game column carries no header word: it's left of Date.
    if cols.game is None and cols.date is not None and cols.date > 0:
        cols.game = cols.date - 1
    if cols.game is None:
        cols.game = 0
    return cols


# --------------------------------------------------------------------------- #
# interpretation
# --------------------------------------------------------------------------- #
def _read_bonus_rows(
    grid: list[list[Cell]],
    ref_prefix: str,
    result: ReadResult,
    sheet: str,
    hunt_ref: str | None = None,
) -> list[BonusRecord]:
    header_idx, cols = _find_header(grid)
    if header_idx is None:
        result.warnings.append(f"{sheet}: no header row found")
        return []

    records: list[BonusRecord] = []
    for i in range(header_idx + 1, len(grid)):
        row = grid[i]
        game = _cell_text(row, cols.game)
        if not game:
            continue  # blank / summary / balance line
        bet = _parse_decimal(row, cols.bet, 4)
        win = _parse_decimal(row, cols.win, 2)
        if bet is None or win is None:
            continue
        if bet <= 0 or win < 0:
            result.warnings.append(f"{sheet} row {i}: bet<=0 or win<0 — skipped")
            continue
        played_on = _parse_date(row, cols.date)  # None for hunts (no date column)
        records.append(
            BonusRecord(
                import_ref=f"{ref_prefix}:{i}",
                game_name=game,
                played_on=played_on,
                bet=bet,
                win=win,
                notes=_cell_text(row, cols.notes) or None,
                replay_url=repair_replay_url(_row_href(row)),
                date_suspect=played_on is not None and is_date_suspect(played_on),
                hunt_ref=hunt_ref,
            )
        )
    return records


def _build_hunt(number: int, grid: list[list[Cell]], rows: list[BonusRecord]) -> HuntRecord:
    dates = [r.played_on for r in rows if r.played_on is not None]
    return HuntRecord(
        import_ref=f"hunt:{number}",
        label=f"Bonus Hunt {number}",
        hunt_date=min(dates) if dates else None,
        start_balance=_scan_labeled_amount(grid, "start"),
        end_balance=_scan_labeled_amount(grid, "end"),
        end_convention="spin_end" if number == SPIN_END_HUNT else "after_opening",
    )


def _read_notable(
    grid: list[list[Cell]],
    sheet: str,
    main_records: list[BonusRecord],
    result: ReadResult,
    lookup: dict[str, str],
) -> None:
    index: dict[tuple[str, Decimal, Decimal], BonusRecord] = {}
    for rec in main_records:
        key = (canonical_game_name(rec.game_name, lookup), rec.bet, rec.win)
        index.setdefault(key, rec)

    for i, row in enumerate(grid):
        game = _cell_text(row, _NB_GAME)
        bet = _parse_decimal(row, _NB_BET, 4)
        win = _parse_decimal(row, _NB_WIN, 2)
        if not game or bet is None or win is None or bet <= 0 or win < 0:
            continue
        href = repair_replay_url(_row_href(row))
        match = index.get((canonical_game_name(game, lookup), bet, win))
        if match is not None:
            match.notable = True
            if not match.replay_url and href:
                match.replay_url = href
        else:
            result.bonuses.append(
                BonusRecord(
                    import_ref=f"notable:{i}",
                    game_name=game,
                    played_on=None,
                    bet=bet,
                    win=win,
                    replay_url=href,
                    notable=True,
                )
            )


# --------------------------------------------------------------------------- #
# cell helpers
# --------------------------------------------------------------------------- #
def _cell_text(row: list[Cell], col: int | None) -> str:
    if col is None or col >= len(row):
        return ""
    return row[col].text


def _row_href(row: list[Cell]) -> str | None:
    for cell in row:
        if cell.href:
            return cell.href
    return None


def _parse_decimal(row: list[Cell], col: int | None, places: int) -> Decimal | None:
    if col is None or col >= len(row):
        return None
    cell = row[col]
    raw = cell.value if cell.value is not None else cell.text
    return _to_decimal(raw, places)


def _to_decimal(raw: object, places: int) -> Decimal | None:
    if raw is None:
        return None
    cleaned = str(raw).replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned).quantize(Decimal(10) ** -places)
    except Exception:
        return None


def _parse_date(row: list[Cell], col: int | None) -> date | None:
    if col is None or col >= len(row):
        return None
    cell = row[col]
    if cell.date_value:
        try:
            return date.fromisoformat(cell.date_value[:10])
        except ValueError:
            pass
    text = cell.text.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _scan_labeled_amount(grid: list[list[Cell]], label: str) -> Decimal | None:
    """Find a cell whose text starts with ``label`` and return the first numeric
    value to its right (how the hunt tabs lay out Start/End balances)."""
    for row in grid:
        for i, cell in enumerate(row):
            if cell.text.lower().startswith(label):
                for other in row[i + 1 :]:
                    amount = _to_decimal(other.value if other.value is not None else other.text, 2)
                    if amount is not None:
                        return amount
    return None
