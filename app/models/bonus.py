"""The bonus record — one table for everything.

``hunt_id IS NULL`` means an ordinary logged bonus; a non-null ``hunt_id`` ties
it to a hunt. ``multiplier`` is a generated column so X can never drift from
win/bet the way it did in the later hunt tabs of the source workbook.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    column,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.game import Game
    from app.models.hunt import Hunt
    from app.models.session import PlaySession


class Bonus(Base):
    __tablename__ = "bonus"
    __table_args__ = (
        CheckConstraint("bet > 0", name="bet_positive"),
        CheckConstraint("win >= 0", name="win_nonneg"),
        # The four indexes from the brief, with their exact names.
        Index("bonus_game_idx", "game_id"),
        Index("bonus_played_on_idx", column("played_on").desc()),
        Index(
            "bonus_hunt_idx",
            "hunt_id",
            postgresql_where=text("hunt_id IS NOT NULL"),
        ),
        # Added in migration 0004 for the per-session P&L query.
        Index(
            "bonus_session_idx",
            "session_id",
            postgresql_where=text("session_id IS NOT NULL"),
        ),
        Index("bonus_multiplier_idx", column("multiplier").desc()),
    )

    # BIGSERIAL on Postgres; INTEGER on SQLite so the test DB's rowid
    # autoincrement kicks in (SQLite only auto-assigns INTEGER PRIMARY KEY).
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("game.id"), nullable=False)
    # Nullable: hunt and notable source rows carry no per-bonus date. App-entered
    # bonuses always set it. See migration 0003 and DEPLOY.md.
    played_on: Mapped[date | None] = mapped_column(Date)
    bet: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    win: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Generated column — never written from Python, never recomputed here.
    multiplier: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), Computed("win / bet", persisted=True)
    )
    notes: Mapped[str | None] = mapped_column(Text)
    replay_url: Mapped[str | None] = mapped_column(Text)
    notable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    hunt_id: Mapped[int | None] = mapped_column(ForeignKey("hunt.id", ondelete="SET NULL"))
    session_id: Mapped[int | None] = mapped_column(ForeignKey("session.id", ondelete="SET NULL"))
    date_suspect: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # Stable source-row identity for idempotent import (sheet + row coordinate).
    # NULL for rows entered through the app. See docs/build-brief.md import notes
    # and DEPLOY.md — added in migration 0002, not part of the original brief
    # schema. Content-based keys can't be used: the source has documented
    # coincidental (game, date, bet, win) collisions that must NOT be deduped.
    import_ref: Mapped[str | None] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    game: Mapped[Game] = relationship()
    hunt: Mapped[Hunt | None] = relationship(back_populates="bonuses")
    session: Mapped[PlaySession | None] = relationship()
