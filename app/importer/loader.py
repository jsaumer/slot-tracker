"""Idempotent load of parsed records into the database.

Idempotency hinges on ``import_ref``: every source row carries a stable identity,
so a re-run updates in place rather than inserting duplicates. Games are keyed by
canonical name, hunts and bonuses by import_ref.

Dialect-agnostic — uses plain ORM get-or-create (no ON CONFLICT), so the same
code path runs against PostgreSQL in production and SQLite in tests.

The generated columns (``bonus.multiplier``, ``session.net``) are never written.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.importer.aliases import ALIAS_MAP
from app.importer.normalize import (
    build_alias_lookup,
    canonical_game_name,
    normalize_name,
)
from app.importer.records import BonusRecord, HuntRecord, ImportSummary
from app.models import Bonus, Game, GameAlias, Hunt


def load(
    session: Session,
    hunts: list[HuntRecord],
    bonuses: list[BonusRecord],
    alias_map: dict[str, str] = ALIAS_MAP,
) -> ImportSummary:
    summary = ImportSummary()
    lookup = build_alias_lookup(alias_map)

    _seed_games(session, bonuses, alias_map, lookup, summary)
    game_id_by_name = {g.name: g.id for g in session.execute(select(Game)).scalars()}

    _seed_aliases(session, alias_map, game_id_by_name)
    hunt_id_by_ref = _load_hunts(session, hunts, summary)
    _load_bonuses(session, bonuses, lookup, game_id_by_name, hunt_id_by_ref, summary)

    summary.total_bonuses = session.scalar(select(func.count()).select_from(Bonus)) or 0
    summary.total_games = session.scalar(select(func.count()).select_from(Game)) or 0
    summary.total_hunts = session.scalar(select(func.count()).select_from(Hunt)) or 0
    return summary


def _seed_games(
    session: Session,
    bonuses: list[BonusRecord],
    alias_map: dict[str, str],
    lookup: dict[str, str],
    summary: ImportSummary,
) -> None:
    canonical_names: set[str] = {canonical_game_name(b.game_name, lookup) for b in bonuses}
    # Alias targets must exist as games even if no bonus references them directly.
    canonical_names.update(alias_map.values())

    existing = set(session.execute(select(Game.name)).scalars())
    for name in sorted(canonical_names):
        if name and name not in existing:
            session.add(Game(name=name))
            existing.add(name)
            summary.games_created += 1
    session.flush()


def _seed_aliases(
    session: Session,
    alias_map: dict[str, str],
    game_id_by_name: dict[str, int],
) -> None:
    existing = {a for a in session.execute(select(GameAlias.alias)).scalars()}
    for raw, canonical in alias_map.items():
        alias = normalize_name(raw)
        # Skip a self-alias (double-space spelling that normalizes to the
        # canonical name) — it would just point a game at itself.
        if alias == canonical or alias in existing:
            continue
        session.add(GameAlias(alias=alias, game_id=game_id_by_name[canonical]))
        existing.add(alias)
    session.flush()


def _load_hunts(
    session: Session,
    hunts: list[HuntRecord],
    summary: ImportSummary,
) -> dict[str, int]:
    existing = {
        h.import_ref: h
        for h in session.execute(select(Hunt).where(Hunt.import_ref.is_not(None))).scalars()
    }
    for hr in hunts:
        hunt = existing.get(hr.import_ref)
        if hunt is None:
            hunt = Hunt(import_ref=hr.import_ref)
            session.add(hunt)
            existing[hr.import_ref] = hunt
            summary.hunts_created += 1
        else:
            summary.hunts_updated += 1
        hunt.label = hr.label
        hunt.hunt_date = hr.hunt_date
        hunt.start_balance = hr.start_balance
        hunt.end_balance = hr.end_balance
        hunt.end_convention = hr.end_convention
        hunt.notes = hr.notes
    session.flush()
    return {ref: hunt.id for ref, hunt in existing.items()}


def _load_bonuses(
    session: Session,
    bonuses: list[BonusRecord],
    lookup: dict[str, str],
    game_id_by_name: dict[str, int],
    hunt_id_by_ref: dict[str, int],
    summary: ImportSummary,
) -> None:
    existing = {
        b.import_ref: b
        for b in session.execute(select(Bonus).where(Bonus.import_ref.is_not(None))).scalars()
    }
    for br in bonuses:
        canonical = canonical_game_name(br.game_name, lookup)
        game_id = game_id_by_name[canonical]
        hunt_id = hunt_id_by_ref.get(br.hunt_ref) if br.hunt_ref else None

        bonus = existing.get(br.import_ref)
        if bonus is None:
            bonus = Bonus(import_ref=br.import_ref)
            session.add(bonus)
            existing[br.import_ref] = bonus
            summary.bonuses_inserted += 1
        else:
            summary.bonuses_updated += 1

        bonus.game_id = game_id
        bonus.played_on = br.played_on
        bonus.bet = br.bet
        bonus.win = br.win
        bonus.notes = br.notes
        bonus.replay_url = br.replay_url
        bonus.notable = br.notable
        bonus.date_suspect = br.date_suspect
        bonus.hunt_id = hunt_id

        if br.date_suspect:
            summary.suspects_flagged += 1
        if br.notable:
            summary.notable_flagged += 1
    session.flush()
