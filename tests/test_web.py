"""Route + template smoke tests over a SQLite-backed session.

Overrides the get_session dependency so the real app (routers, templates,
services) runs against an in-memory database — no Postgres needed. This is the
CI safety net for the web layer, which otherwise is only exercised by hand.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.importer.loader import load
from app.importer.records import BonusRecord, HuntRecord
from app.main import app
from app.models import Bonus, PlaySession
from tests.support import make_sessionmaker

SessionLocal = make_sessionmaker()


def _seed() -> None:
    with SessionLocal() as s:
        load(
            s,
            [
                HuntRecord(
                    "hunt:1", "Bonus Hunt 1", date(2024, 3, 1), Decimal("500.00"), Decimal("620.00")
                )
            ],
            [
                BonusRecord(
                    "main:1", "Sugar RUsh", date(2023, 1, 2), Decimal("0.20"), Decimal("40.00")
                ),
                BonusRecord(
                    "main:2",
                    "Gates of Olympus",
                    date(2024, 2, 2),
                    Decimal("0.20"),
                    Decimal("18.00"),
                ),
                BonusRecord(
                    "hunt:1:1",
                    "Fruitz",
                    date(2024, 3, 1),
                    Decimal("0.40"),
                    Decimal("160.00"),
                    hunt_ref="hunt:1",
                ),
            ],
        )
        s.commit()


@pytest.fixture
def client() -> Iterator[TestClient]:
    _seed()

    def _override() -> Iterator[Session]:
        with SessionLocal() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "path",
    ["/", "/log", "/dashboard", "/games", "/hunts", "/hunts/1", "/sessions"],
)
def test_pages_render(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_export_is_csv(client: TestClient) -> None:
    resp = client.get("/export")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert resp.text.splitlines()[0].startswith("id,game,played_on")


def test_add_bonus_inserts_and_flashes(client: TestClient) -> None:
    with SessionLocal() as s:
        before = s.scalar(select(func.count()).select_from(Bonus))

    resp = client.post(
        "/bonus",
        data={"game": "Big Bass", "bet": "0.20", "win": "50", "played_on": "2024-05-01"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "Added Big Bass" in resp.text
    assert "250x" in resp.text  # 50 / 0.20, multiplier filter output

    with SessionLocal() as s:
        after = s.scalar(select(func.count()).select_from(Bonus))
    assert after == before + 1


def test_add_bonus_rejects_bad_input(client: TestClient) -> None:
    """Asserts the *rendered* error, not just the status. Checking only the code
    passed even when FastAPI rejected the request itself and the handler never
    ran, which hid the raw-JSON response the user would have seen."""
    resp = client.post(
        "/bonus",
        data={"game": "", "bet": "0", "win": "-5"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 422
    assert "Enter a game" in resp.text
    assert "text/html" in resp.headers["content-type"]


def test_log_filters_by_game(client: TestClient) -> None:
    resp = client.get("/log", params={"q": "Fruitz"})
    assert resp.status_code == 200
    assert "Fruitz" in resp.text
    assert "Sugar Rush" not in resp.text


def test_hunt_detail_shows_result(client: TestClient) -> None:
    resp = client.get("/hunts/1")
    assert resp.status_code == 200
    assert "Bonus Hunt 1" in resp.text


def test_unknown_hunt_404(client: TestClient) -> None:
    resp = client.get("/hunts/9999")
    assert resp.status_code == 404


def test_edit_page_renders_and_updates(client: TestClient) -> None:
    resp = client.get("/bonus/1/edit")
    assert resp.status_code == 200
    assert "Edit bonus" in resp.text

    resp = client.post(
        "/bonus/1",
        data={"game": "Sugar Rush", "bet": "0.20", "win": "80", "played_on": "2024-06-01"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    with SessionLocal() as s:
        bonus = s.get(Bonus, 1)
        assert bonus.win == Decimal("80.00")
        assert bonus.multiplier == Decimal("400")  # 80 / 0.20, generated


def test_edit_unknown_bonus_404(client: TestClient) -> None:
    assert client.get("/bonus/9999/edit").status_code == 404


def test_delete_bonus_removes_it(client: TestClient) -> None:
    with SessionLocal() as s:
        before = s.scalar(select(func.count()).select_from(Bonus))
    resp = client.post("/bonus/2/delete", follow_redirects=False)
    assert resp.status_code == 303
    with SessionLocal() as s:
        after = s.scalar(select(func.count()).select_from(Bonus))
    assert after == before - 1


def test_session_detail_renders(client: TestClient) -> None:
    with SessionLocal() as s:
        ps = PlaySession(site="Stake", deposit=Decimal("100.00"), cashout=Decimal("60.00"))
        s.add(ps)
        s.commit()
        session_id = ps.id
    resp = client.get(f"/sessions/{session_id}")
    assert resp.status_code == 200
    assert "Bonus winnings" in resp.text


def test_unknown_session_404(client: TestClient) -> None:
    assert client.get("/sessions/9999").status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        # Sorted views on every surface — these render the shared sortable macro.
        "/log?sort=win&dir=asc",
        "/log?sort=x&dir=desc",
        "/log?sort=notes&dir=asc",
        "/games?sort=won&dir=asc",
        "/games?q=fruit",
        "/hunts?sort=net&dir=asc",
        "/sessions?sort=net&dir=desc",
        "/dashboard?ysort=won&ydir=asc&bsort=bet&bdir=desc",
        "/hunts/1?sort=win&dir=asc",
        # New log filters.
        "/log?notable=1",
        "/log?has_replay=1",
        "/log?suspect=1",
        "/log?provenance=bought",
        "/log?provenance=natural",
        "/log?provenance=unknown",
        "/log?sort=cost&dir=desc",
        "/log?sort=costx&dir=asc",
        "/log?q=Fruitz&sort=bet&dir=asc&notable=1",
    ],
)
def test_sorted_and_filtered_views_render(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.parametrize(
    "path",
    ["/log?sort=win;DROP+TABLE+bonus&dir=x", "/games?sort=../../etc", "/hunts?sort=nope&dir=nope"],
)
def test_hostile_sort_params_fall_back_instead_of_erroring(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 200


def test_game_detail_renders(client: TestClient) -> None:
    resp = client.get("/games/1")
    assert resp.status_code == 200
    assert "Best hits" in resp.text or "No bonuses recorded" in resp.text


def test_unknown_game_404(client: TestClient) -> None:
    assert client.get("/games/9999").status_code == 404


def test_log_shows_filtered_summary(client: TestClient) -> None:
    resp = client.get("/log")
    assert "bonuses" in resp.text
    assert "won" in resp.text


def test_hunt_edit_page_renders_and_updates(client: TestClient) -> None:
    assert client.get("/hunts/1/edit").status_code == 200
    resp = client.post(
        "/hunts/1",
        data={
            "label": "Renamed Hunt",
            "hunt_date": "2024-03-01",
            "start_balance": "500",
            "end_balance": "700",
            "end_convention": "after_opening",
            "status": "open",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "Renamed Hunt" in client.get("/hunts/1").text


def test_hunt_edit_unknown_404(client: TestClient) -> None:
    assert client.get("/hunts/9999/edit").status_code == 404


def test_hunt_add_bonus_reports_errors_instead_of_redirecting(client: TestClient) -> None:
    resp = client.post(
        "/hunts/1/bonus",
        data={"game": "", "bet": "0", "win": "-1"},
        follow_redirects=False,
    )
    assert resp.status_code == 422
    assert "Enter a game" in resp.text


def test_export_respects_filters(client: TestClient) -> None:
    everything = client.get("/export").text.splitlines()
    filtered = client.get("/export", params={"q": "Fruitz"}).text.splitlines()
    assert len(filtered) < len(everything)
    assert all("Fruitz" in line for line in filtered[1:])


@pytest.mark.parametrize("path", ["/export/hunts", "/export/sessions"])
def test_extra_exports_are_csv(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]


def test_adding_a_bought_bonus_records_cost_and_return(client: TestClient) -> None:
    resp = client.post(
        "/bonus",
        data={
            "game": "Buy Test",
            "bet": "0.20",
            "win": "250",
            "played_on": "2024-07-01",
            "cost": "20",
            "bought": "true",
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    with SessionLocal() as s:
        bonus = s.scalar(select(Bonus).where(Bonus.cost == Decimal("20.00")))
        assert bonus is not None
        assert bonus.bought is True
        assert bonus.cost_multiplier == Decimal("12.5")


def test_adding_without_the_buy_checkbox_stores_no_cost(client: TestClient) -> None:
    resp = client.post(
        "/bonus",
        data={
            "game": "Natural Test",
            "bet": "0.20",
            "win": "33",
            "played_on": "2024-07-02",
            "cost": "20",  # ignored: the checkbox was not ticked
        },
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    with SessionLocal() as s:
        bonus = s.scalar(select(Bonus).where(Bonus.win == Decimal("33.00")))
        assert bonus.bought is False
        assert bonus.cost is None


def test_merge_suggestions_page_renders(client: TestClient) -> None:
    """Also guards route ordering: /games/merges must be registered before
    /games/{game_id}, which parses its segment as an int and would reject it."""
    resp = client.get("/games/merges")
    assert resp.status_code == 200
    assert "Duplicate games" in resp.text


def test_applying_a_suggestion_redirects_back_to_the_list(client: TestClient) -> None:
    resp = client.post(
        "/games/merges",
        data={"source": "Gates of Olympus", "target": "Sugar Rush"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/games/merges"


def test_games_merge_redirects(client: TestClient) -> None:
    resp = client.post(
        "/games/merge",
        data={"source": "Gates of Olympus", "target": "Sugar Rush"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
