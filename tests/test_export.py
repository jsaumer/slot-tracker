"""CSV exports: the bonus export must honour the log's filters, and hunts and
sessions must export at all."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.models import PlaySession
from app.services.bonuses import LogFilters, create_bonus
from app.services.export import iter_bonus_csv, iter_hunt_csv, iter_session_csv
from app.services.hunts import close_hunt, open_hunt
from tests.support import make_sessionmaker


def _seed(session) -> None:
    create_bonus(
        session,
        game_name="Big Bass",
        played_on=date(2024, 1, 1),
        bet=Decimal("0.20"),
        win=Decimal("10.00"),
        notes="line one\nline two",
    )
    create_bonus(
        session,
        game_name="Sugar Rush",
        played_on=date(2024, 2, 1),
        bet=Decimal("0.20"),
        win=Decimal("100.00"),
        notable=True,
    )
    hunt = open_hunt(
        session, label="Hunt A", start_balance=Decimal("500.00"), hunt_date=date(2024, 3, 1)
    )
    session.flush()
    close_hunt(
        session, hunt_id=hunt.id, end_balance=Decimal("560.00"), end_convention="after_opening"
    )
    session.add(
        PlaySession(
            site="Test Site",
            deposit=Decimal("200.00"),
            cashout=Decimal("150.00"),
            started_at=datetime(2024, 3, 1),
        )
    )
    session.commit()


def _csv(rows) -> list[str]:
    return "".join(rows).splitlines()


def test_bonus_export_is_unfiltered_by_default() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        lines = _csv(iter_bonus_csv(s))
        assert lines[0].startswith("id,game,played_on")
        assert len(lines) == 3  # header + 2 bonuses


def test_bonus_export_honours_filters() -> None:
    """The export button sits in the log's filter bar; exporting the whole table
    regardless of what is on screen would contradict it."""
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)

        notable_only = _csv(iter_bonus_csv(s, LogFilters(notable=True)))
        assert len(notable_only) == 2
        assert "Sugar Rush" in notable_only[1]

        by_game = _csv(iter_bonus_csv(s, LogFilters(q="bass")))
        assert len(by_game) == 2
        assert "Big Bass" in by_game[1]

        by_date = _csv(iter_bonus_csv(s, LogFilters(date_from=date(2024, 2, 1))))
        assert len(by_date) == 2

        empty = _csv(iter_bonus_csv(s, LogFilters(q="nothing-matches")))
        assert len(empty) == 1  # header only


def test_bonus_export_flattens_multiline_notes() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        lines = _csv(iter_bonus_csv(s, LogFilters(q="bass")))
        assert len(lines) == 2  # the embedded newline did not split the row
        assert "line one line two" in lines[1]


def test_bonus_export_includes_cost_and_leaves_unknown_provenance_blank() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        create_bonus(
            session=s,
            game_name="Bought Game",
            played_on=date(2024, 4, 1),
            bet=Decimal("0.20"),
            win=Decimal("250.00"),
            cost=Decimal("20.00"),
            bought=True,
        )
        create_bonus(
            session=s,
            game_name="Unknown Game",
            played_on=date(2024, 4, 2),
            bet=Decimal("0.20"),
            win=Decimal("10.00"),
        )
        s.commit()

        lines = _csv(iter_bonus_csv(s))
        header = lines[0].split(",")
        assert "cost" in header and "bought" in header and "cost_multiplier" in header

        bought_row = next(line for line in lines if line.startswith("1,"))
        assert "20.00" in bought_row
        assert "12.5" in bought_row  # 250 / 20

        unknown_row = next(line for line in lines if "Unknown Game" in line)
        cells = unknown_row.split(",")
        # Blank, not "False": provenance was never recorded.
        assert cells[header.index("bought")] == ""
        assert cells[header.index("cost")] == ""


def test_hunt_export_includes_derived_result() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        lines = _csv(iter_hunt_csv(s))
        assert lines[0].startswith("id,label,hunt_date,status")
        assert len(lines) == 2
        # after_opening: cost = start (500), net = end - start = 60
        assert "500.00" in lines[1]
        assert "60.00" in lines[1]


def test_session_export_includes_running_total() -> None:
    Session = make_sessionmaker()
    with Session() as s:
        _seed(s)
        lines = _csv(iter_session_csv(s))
        assert lines[0].startswith("id,site,started_at")
        assert len(lines) == 2
        assert "Test Site" in lines[1]
        assert "-50.00" in lines[1]  # net = 150 - 200
